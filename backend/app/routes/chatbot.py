"""VoiceField website chatbot — rule-based lead capture (no external AI key).

Public widget endpoint (no auth) + authenticated lead management.
"""

import random
import re
import string
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.rate_limit import limiter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Business, Customer, Job, JobStatus, KnowledgeBaseArticle, User
from app.routes.auth import get_current_user
from app.services import llm
from app.services.phone import is_valid_uk_mobile

router = APIRouter(prefix="/api/chatbot", tags=["chatbot"])


# ---------------------------------------------------------------------------
# In-memory stores (demo; replaced by persistent storage in production)
# ---------------------------------------------------------------------------

# session_id -> {stage, service, postcode, name, phone, escalated, lead_reference, page_url}
_SESSIONS: Dict[str, dict] = {}
# lead_id -> lead dict
_LEADS: Dict[str, dict] = {}
# ticket_id -> ticket dict
_TICKETS: Dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=1, max_length=128)
    page_url: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    quick_replies: List[str]
    stage: str
    lead_reference: Optional[str] = None


class EscalateRequest(BaseModel):
    session_id: str
    reason: str = "Customer requested human follow-up"


# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------

BUSINESS_NAME = "Allo"
WELCOME_MESSAGE = (
    "Hi there! Thanks for visiting Allo. "
    "I can help with services, pricing, availability or booking a visit. "
    "What do you need help with today?"
)
DEFAULT_QUICK_REPLIES = [
    "Get a quote",
    "Book a visit",
    "Our services",
    "Pricing",
    "Emergency help",
]
OPENING_HOURS = "Mon–Fri 8:00–18:00, Sat 9:00–13:00, Sun closed. 24/7 emergency call-out available."
SUPPORT_PHONE = "0161 496 0000"

UK_POSTCODE_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.IGNORECASE
)
# Matches +44... and 0... UK numbers with spaces/dashes/brackets
UK_PHONE_RE = re.compile(
    r"(\+44\s?\(?\d\)?[\d\s\-\(\)]{8,14}|\(?0\d{3,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})"
)
NAME_RE = re.compile(
    r"(?:my name is|i'm|i am|this is|call me)\s+([a-z][a-z'\- ]{1,40})",
    re.IGNORECASE,
)

SERVICE_KEYWORDS = {
    "plumbing": ["plumb", "leak", "tap", "toilet", "pipe", "shower"],
    "heating": ["heating", "radiator", "central heating"],
    "boiler": ["boiler", "gas safe", "gas certificate", "cp12", "annual service"],
    "electrical": ["electric", "socket", "fuse", "consumer unit", "eicr", "rewire", "light"],
    "drainage": ["drain", "blockage", "blocked"],
    "roofing": ["roof", "gutter", "fascia", "chimney"],
    "carpentry": ["carpenter", "joinery", "door hanging", "skirting"],
    "painting & decorating": ["paint", "decorat", "wallpaper", "plaster"],
    "kitchen & bathroom": ["kitchen", "bathroom", "tiling", "wet room"],
    "locksmith": ["lock", "locked out", "upvc door"],
    "pest control": ["pest", "wasp", "rat", "mice", "wasp nest"],
    "gardening": ["garden", "fence", "decking", "hedge", "landscap"],
    "cleaning": ["clean", "end of tenancy"],
    "air conditioning": ["air con", "air conditioning", "hvac", "heat pump"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_session() -> dict:
    return {
        "stage": "greeting",
        "service": None,
        "postcode": None,
        "name": None,
        "phone": None,
        "escalated": False,
        "lead_reference": None,
        "page_url": None,
    }


def _get_session(session_id: str) -> dict:
    session = _SESSIONS.get(session_id)
    if session is None:
        session = _new_session()
        _SESSIONS[session_id] = session
    return session


def _normalise_postcode(raw: str) -> str:
    cleaned = re.sub(r"\s+", "", raw.strip().upper())
    if len(cleaned) > 3:
        return f"{cleaned[:-3]} {cleaned[-3:]}"
    return cleaned


def _extract_postcode(text: str) -> Optional[str]:
    match = UK_POSTCODE_RE.search(text)
    if match:
        return _normalise_postcode(match.group(1))
    return None


def _extract_phone(text: str) -> Optional[str]:
    match = UK_PHONE_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    # Normalise +44 leading
    if match.group(1).strip().startswith("+"):
        digits = digits  # keep as-is for length check (44...)
        if digits.startswith("44"):
            digits = "0" + digits[2:]
    if 10 <= len(digits) <= 11:
        return match.group(1).strip()
    return None


def _extract_name(text: str) -> Optional[str]:
    match = NAME_RE.search(text.strip())
    if match:
        name = match.group(1).strip().strip(".,!")
        # Keep first 2-3 words, title-case
        parts = name.split()
        return " ".join(parts[:3]).title()
    return None


def _extract_service(text: str) -> Optional[str]:
    lowered = text.lower()
    for service, keywords in SERVICE_KEYWORDS.items():
        for kw in keywords:
            if kw in lowered:
                return service
    return None


def _looks_like_bare_name(text: str) -> bool:
    stripped = text.strip().strip(".,!")
    if len(stripped) > 40 or len(stripped) < 2:
        return False
    if re.search(r"\d|@|http|www|\.co|\.uk", stripped, re.IGNORECASE):
        return False
    words = stripped.split()
    if len(words) > 3 or len(words) < 1:
        return False
    return all(re.fullmatch(r"[A-Za-z'\-]{2,}", w) for w in words)


def _make_reference(prefix: str) -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{suffix}"


def _detect_intent(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in ["emergency", "urgent", "burst", "flooding", "flood", "no heating", "no hot water", "gas leak", "smell gas", "break-in", "asap"]):
        return "emergency"
    if any(k in t for k in ["book", "schedule", "appointment", "visit", "send someone", "send an engineer", "call out", "callout"]):
        return "booking"
    if any(k in t for k in ["quote", "estimate", "how much", "free quote"]):
        return "quote"
    if any(k in t for k in ["price", "pricing", "cost", "charge", "rates", "call-out fee", "callout fee"]):
        return "pricing"
    if any(k in t for k in ["membership", "plan", "cover plan", "care plan", "subscription", "landlord cover"]):
        return "membership"
    if any(k in t for k in ["opening", "open", "hours", "weekend", "saturday", "sunday", "when are you"]):
        return "hours"
    if any(k in t for k in ["human", "person", "someone real", "agent", "call me back", "speak to", "talk to", "phone number", "contact"]):
        return "contact"
    if any(k in t for k in ["area", "areas", "cover", "postcode", "do you cover", "location", "manchester", "stockport", "salford"]):
        return "area"
    if any(k in t for k in ["service", "services", "what do you do", "offer", "repair", "install", "boiler service"]):
        return "services"
    if any(k in t for k in ["hi", "hello", "hey", "good morning", "good afternoon"]):
        return "greeting"
    return None


async def _kb_context(
    query: str,
    db,
    business_id=None,
    limit: int = 3,
) -> List[dict]:
    """RAG-lite keyword retrieval over published KB articles.

    Splits the query into 3+ letter tokens, scores title hits ×3 plus
    content hits ×1, and returns the top `limit` hits as
    [{title, excerpt (~300 chars)}]. Articles carry business_id, so scope
    by it when provided; otherwise search all published articles.
    Never raises — returns [] on any failure (chat must never 500).
    """
    try:
        tokens = re.findall(r"[a-z]{3,}", (query or "").lower())
        if not tokens or db is None:
            return []
        stmt = select(KnowledgeBaseArticle).where(
            KnowledgeBaseArticle.is_published == True  # noqa: E712
        )
        if business_id is not None:
            stmt = stmt.where(KnowledgeBaseArticle.business_id == business_id)
        result = await db.execute(stmt)
        articles = result.scalars().all()
        if not articles:
            return []
        scored: List[tuple] = []
        for article in articles:
            title_lower = (article.title or "").lower()
            content_lower = (article.content or "").lower()
            score = 0
            for token in tokens:
                score += title_lower.count(token) * 3 + content_lower.count(token) * 1
            if score > 0:
                scored.append(
                    (
                        score,
                        {
                            "title": article.title,
                            "excerpt": (article.content or "")[:300],
                        },
                    )
                )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored[:limit]]
    except Exception:
        return []


INTENT_REPLIES: Dict[str, str] = {
    "pricing": (
        "Our standard call-out is £75 + VAT (Mon–Fri, 8–6), which includes the first 30 minutes "
        "on site. Most common fixes land between £95–£250 incl. parts and labour, and every job "
        "gets a fixed written quote before we start — no surprises."
    ),
    "booking": (
        "Great — we can usually offer same-day or next-day slots across Greater Manchester. "
        "I'll just need a few details to get you booked in."
    ),
    "emergency": (
        "I'm sorry you're dealing with that — for anything unsafe (suspected gas leak, major leak, "
        "no heating with vulnerable occupants), call us now on {phone} for priority dispatch. "
        "If there's a gas smell, also call the National Gas Emergency line on 0800 111 999. "
        "I can still take your details here for an emergency call-out — is that OK?"
    ),
    "services": (
        "We cover plumbing, heating & boilers (Gas Safe), electrics (NICEIC), drainage, roofing, "
        "carpentry, painting & decorating, kitchens & bathrooms, locksmiths, pest control and more — "
        "for homes, landlords and letting agents."
    ),
    "hours": (
        "We're open {hours} "
        "For emergencies outside those hours, our on-call engineer line stays open 24/7."
    ),
    "contact": (
        "Of course — you can reach the team on {phone} ({hours}). "
        "Or leave your name and number here and we'll call you straight back during opening hours."
    ),
    "membership": (
        "Our HomeCare plans start at £14.99/month: annual boiler service, priority booking, "
        "10% off labour and no call-out fee. Landlord plans add CP12 gas certificates and EICR reminders. "
        "Want me to check which plan fits your property?"
    ),
    "quote": (
        "Happy to help with that — most quotes are free and fixed in writing after a quick visit or photos. "
        "Tell me briefly what the job is and your postcode, and I'll get the ball rolling."
    ),
    "area": (
        "We cover Greater Manchester and Cheshire — Manchester, Salford, Stockport, Trafford, Bury, "
        "Bolton, Oldham, Rochdale, Wigan and surrounds (roughly M, SK, WA, OL and BL postcodes). "
        "Pop in your postcode and I'll confirm straight away."
    ),
    "greeting": (
        "Hello! How can I help — are you looking for a repair, a quote, or to book a visit?"
    ),
}

INTENT_QUICK_REPLIES: Dict[str, List[str]] = {
    "pricing": ["Get a quote", "Book a visit", "Our services"],
    "booking": ["Get a quote", "Emergency help", "Our services"],
    "emergency": ["Yes, book emergency visit", "Call me back", "Talk to a human"],
    "services": ["Get a quote", "Book a visit", "Pricing"],
    "hours": ["Book a visit", "Talk to a human"],
    "contact": ["Request a callback", "Book a visit"],
    "membership": ["Get a quote", "Talk to a human", "Our services"],
    "quote": ["Book a visit", "Pricing", "Our services"],
    "area": ["Get a quote", "Book a visit"],
    "greeting": DEFAULT_QUICK_REPLIES,
}

CHAT_LLM_SYSTEM = (
    "You are the website chat assistant for a UK trades business. "
    "Use plain UK English. Reply in a natural UK trades tone, max 2 sentences "
    "plus one follow-up question. "
    "Return JSON ONLY with exactly these keys: "
    '{"reply": str, "quick_replies": [str, max 3], '
    '"extract": {"service": str|null, "postcode": str|null, '
    '"name": str|null, "phone": str|null}, "ready_to_book": bool}. '
    "Set ready_to_book true only when service, postcode, name and phone are all known."
)


# ---------------------------------------------------------------------------
# Public: chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(
    request: Request,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    message = payload.message.strip()
    session = _get_session(payload.session_id)
    if payload.page_url:
        session["page_url"] = payload.page_url

    # RAG-lite: never 500 — fall back to no context on any failure.
    try:
        kb_hits = await _kb_context(message, db, limit=3)
    except Exception:
        kb_hits = []
    # pgvector semantic retrieval (additive): RAG hits first, dedupe by title.
    try:
        from app.services import rag as _rag

        rag_hits = await _rag.retrieve(db, message, limit=3)
        if rag_hits:
            _seen = {h.get("title") for h in rag_hits}
            kb_hits = list(rag_hits) + [h for h in kb_hits if h.get("title") not in _seen]
            kb_hits = kb_hits[:3]
    except Exception:
        pass
    kb_block = ""
    if kb_hits:
        kb_lines = "\n".join(f"- {h['title']}: {h['excerpt']}" for h in kb_hits)
        kb_block = f"Relevant company knowledge:\n{kb_lines}\n"

    if session["stage"] == "greeting":
        session["stage"] = "qualifying"

    # --- LLM-first path (falls through to rule-based flow on any failure) ---
    if llm.is_configured() and not (
        session["stage"] == "booked" and session.get("lead_reference")
    ):
        try:
            llm_prompt = (
                f"Business name: {BUSINESS_NAME}\n"
                f"Opening hours: {OPENING_HOURS}\n"
                f"Support phone: {SUPPORT_PHONE}\n"
                f"{kb_block}"
                f"Conversation stage: {session.get('stage')}\n"
                f"Collected so far: service={session.get('service')!r}, "
                f"postcode={session.get('postcode')!r}, "
                f"name={session.get('name')!r}, "
                f"phone={session.get('phone')!r}\n"
                f"Latest customer message: {message}"
            )
            llm_result = await llm.complete_json(
                llm_prompt,
                system=CHAT_LLM_SYSTEM,
                max_tokens=600,
                temperature=0.3,
            )
            llm_reply = llm_result.get("reply")
            if not isinstance(llm_reply, str) or not llm_reply.strip():
                raise ValueError("LLM reply missing")
            llm_reply = llm_reply.strip()

            raw_quick = llm_result.get("quick_replies")
            if isinstance(raw_quick, list):
                llm_quick = [q for q in raw_quick if isinstance(q, str) and q.strip()][:3]
            else:
                llm_quick = list(DEFAULT_QUICK_REPLIES[:3])
            if not llm_quick:
                llm_quick = list(DEFAULT_QUICK_REPLIES[:3])

            extract = llm_result.get("extract") or {}
            if not isinstance(extract, dict):
                extract = {}
            ready_to_book = bool(llm_result.get("ready_to_book"))

            # Merge extracted fields (validate postcode/phone with existing regexes).
            svc_candidate = extract.get("service")
            if svc_candidate and isinstance(svc_candidate, str) and not session.get("service"):
                svc_text = svc_candidate.strip()
                if svc_text:
                    mapped = _extract_service(svc_text)
                    session["service"] = mapped or svc_text.lower()

            pc_candidate = extract.get("postcode")
            if pc_candidate and isinstance(pc_candidate, str):
                validated_pc = _extract_postcode(pc_candidate)
                if validated_pc:
                    session["postcode"] = validated_pc

            name_candidate = extract.get("name")
            if name_candidate and isinstance(name_candidate, str) and not session.get("name"):
                cleaned_name = name_candidate.strip().strip(".,!")
                if 2 <= len(cleaned_name) <= 40:
                    session["name"] = cleaned_name

            phone_candidate = extract.get("phone")
            if phone_candidate and isinstance(phone_candidate, str):
                validated_phone = _extract_phone(phone_candidate)
                if validated_phone:
                    session["phone"] = validated_phone

            # Opportunistic backup: catch entities the LLM missed in the raw message.
            if not session.get("service"):
                backup_service = _extract_service(message)
                if backup_service:
                    session["service"] = backup_service
            if not session.get("postcode"):
                backup_pc = _extract_postcode(message)
                if backup_pc:
                    session["postcode"] = backup_pc
            if not session.get("phone"):
                backup_phone = _extract_phone(message)
                if backup_phone:
                    session["phone"] = backup_phone
            if not session.get("name"):
                backup_name = _extract_name(message)
                if backup_name:
                    session["name"] = backup_name

            if session.get("stage") == "qualifying" and (
                session.get("service")
                or session.get("postcode")
                or session.get("name")
                or session.get("phone")
                or ready_to_book
            ):
                session["stage"] = "collecting"

            all_present = bool(
                session.get("service")
                and session.get("postcode")
                and session.get("name")
                and session.get("phone")
            )
            if ready_to_book and all_present:
                # Create the lead exactly as the rule-based flow does.
                reference = _make_reference("BK")
                lead_id = uuid.uuid4().hex[:12]
                lead = {
                    "id": lead_id,
                    "reference": reference,
                    "service": session["service"],
                    "postcode": session["postcode"],
                    "name": session["name"],
                    "phone": session["phone"],
                    "session_id": payload.session_id,
                    "page_url": session.get("page_url") or payload.page_url,
                    "transcript_snippet": message[:500],
                    "status": "new",
                    "converted": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                _LEADS[lead_id] = lead
                session["stage"] = "booked"
                session["lead_reference"] = reference
                if reference not in llm_reply:
                    llm_reply = (
                        f"{llm_reply} Your booking reference is {reference}."
                    )
                return ChatResponse(
                    reply=llm_reply,
                    quick_replies=llm_quick,
                    stage="booked",
                    lead_reference=reference,
                )

            if ready_to_book and not all_present and session.get("stage") == "qualifying":
                session["stage"] = "collecting"

            return ChatResponse(
                reply=llm_reply,
                quick_replies=llm_quick,
                stage=session["stage"],
                lead_reference=None,
            )
        except Exception:
            pass

    lowered = message.lower()

    # --- Entity extraction (store opportunistically) ---
    postcode = _extract_postcode(message)
    phone = _extract_phone(message)
    service = _extract_service(message)
    name = _extract_name(message)

    entities_confirmed: List[str] = []
    if service and not session["service"]:
        session["service"] = service
        entities_confirmed.append(f"service ({service})")
    if postcode and session["postcode"] != postcode:
        session["postcode"] = postcode
        entities_confirmed.append(f"postcode ({postcode})")
    if phone and session["phone"] != phone:
        if not is_valid_uk_mobile(phone):
            return ChatResponse(
                reply=(
                    "Thanks — that number doesn't look like a valid UK mobile. "
                    "Could you share a valid UK mobile number, "
                    "e.g. 07911 123456 or +447911123456?"
                ),
                quick_replies=[],
                stage=session["stage"],
                lead_reference=None,
            )
        session["phone"] = phone
        entities_confirmed.append("phone number")
    if name and not session["name"]:
        session["name"] = name
        entities_confirmed.append(f"name ({name})")

    # Bare-name fallback: in collecting stage a short alpha-only message is likely a name
    if (
        not session["name"]
        and not name
        and not postcode
        and not phone
        and not service
        and session["stage"] == "collecting"
        and _looks_like_bare_name(message)
        and _detect_intent(message) is None
    ):
        session["name"] = message.strip().title()
        entities_confirmed.append(f"name ({session['name']})")

    intent = _detect_intent(message)

    # Move into collecting once there is buying intent or any entity
    if intent in ("booking", "quote") or entities_confirmed:
        if session["stage"] == "qualifying":
            session["stage"] = "collecting"

    # --- Already booked: handle follow-ups ---
    if session["stage"] == "booked" and session.get("lead_reference"):
        reply = (
            f"You're all booked in — your reference is {session['lead_reference']}. "
            f"An engineer will confirm your slot shortly on {session.get('phone') or 'your number'}. "
            "Is there anything else I can help with?"
        )
        return ChatResponse(
            reply=reply,
            quick_replies=["Talk to a human", "Our services", "Pricing"],
            stage="booked",
            lead_reference=session["lead_reference"],
        )

    # --- Base answer from intent ---
    if intent and intent in INTENT_REPLIES:
        base = INTENT_REPLIES[intent].format(phone=SUPPORT_PHONE, hours=OPENING_HOURS)
        quick_replies = INTENT_QUICK_REPLIES.get(intent, DEFAULT_QUICK_REPLIES)
    elif kb_hits:
        top = kb_hits[0]
        base = (
            f"From our help centre — {top['title']}: {top['excerpt']} "
            "Want me to book you in?"
        )
        quick_replies = list(DEFAULT_QUICK_REPLIES)
    else:
        base = (
            "Thanks — I've noted that. To point you to the right engineer, "
            "could you tell me a little more about the job?"
        )
        quick_replies = list(DEFAULT_QUICK_REPLIES)

    # Emergency always escalates the session for human follow-up
    if intent == "emergency":
        session["escalated"] = True

    # --- Lead-capture progression ---
    missing: List[str] = []
    if not session["service"]:
        missing.append("service")
    if not session["postcode"]:
        missing.append("postcode")
    if not session["name"]:
        missing.append("name")
    if not session["phone"]:
        missing.append("phone")

    # If user showed booking/quote intent, steer into collection explicitly
    wants_booking = intent in ("booking", "quote") or session["stage"] == "collecting"

    if not missing:
        # All details collected → create the lead
        reference = _make_reference("BK")
        lead_id = uuid.uuid4().hex[:12]
        lead = {
            "id": lead_id,
            "reference": reference,
            "service": session["service"],
            "postcode": session["postcode"],
            "name": session["name"],
            "phone": session["phone"],
            "session_id": payload.session_id,
            "page_url": session.get("page_url") or payload.page_url,
            "transcript_snippet": message[:500],
            "status": "new",
            "converted": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _LEADS[lead_id] = lead
        session["stage"] = "booked"
        session["lead_reference"] = reference
        reply = (
            f"Brilliant — I've booked that in for you. Your booking reference is {reference}. "
            f"That's {session['service']} at {session['postcode']} for {session['name']} "
            f"({session['phone']}). We'll confirm your slot by text shortly. "
            "Anything else I can help with?"
        )
        return ChatResponse(
            reply=reply,
            quick_replies=["Talk to a human", "Our services", "Pricing"],
            stage="booked",
            lead_reference=reference,
        )

    # Otherwise append the next collection question
    if wants_booking or entities_confirmed or session["stage"] == "collecting":
        session["stage"] = "collecting"
        if not session["service"]:
            follow_up = "Which service do you need — e.g. plumbing, boiler, electrics or drainage?"
            quick_replies = ["Plumbing", "Boiler / heating", "Electrics", "Drainage"]
        elif not session["postcode"]:
            prefix = "Got it. " if entities_confirmed else ""
            follow_up = f"{prefix}What's the property postcode so I can check coverage and dispatch?"
            quick_replies = quick_replies
        elif not session["name"]:
            follow_up = "Thanks — and what name should I put the booking under?"
            quick_replies = quick_replies
        else:  # phone missing
            follow_up = (
                "Last one — what's the best UK mobile or landline to confirm your slot on?"
            )
            quick_replies = quick_replies
        reply = f"{base} {follow_up}"
    else:
        reply = f"{base} Are you looking to get a quote or book a visit?"
        quick_replies = list(DEFAULT_QUICK_REPLIES)

    _ = lowered  # keep for future keyword extensions
    return ChatResponse(
        reply=reply,
        quick_replies=quick_replies,
        stage=session["stage"],
        lead_reference=None,
    )


# ---------------------------------------------------------------------------
# Public: config
# ---------------------------------------------------------------------------


@router.get("/config")
async def get_config() -> dict:
    return {
        "business_name": BUSINESS_NAME,
        "welcome_message": WELCOME_MESSAGE,
        "quick_replies": DEFAULT_QUICK_REPLIES,
        "opening_hours": OPENING_HOURS,
        "phone": SUPPORT_PHONE,
    }


# ---------------------------------------------------------------------------
# Public: escalate to human
# ---------------------------------------------------------------------------


@router.post("/escalate")
async def escalate(payload: EscalateRequest) -> dict:
    session = _get_session(payload.session_id)
    session["escalated"] = True
    ticket_id = _make_reference("TKT")
    _TICKETS[ticket_id] = {
        "ticket_id": ticket_id,
        "session_id": payload.session_id,
        "reason": payload.reason,
        "page_url": session.get("page_url"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "ticket_id": ticket_id,
        "message": (
            "Thanks — I've flagged this for the team. "
            f"Someone will be in touch shortly (ticket {ticket_id}). "
            f"For anything urgent, call {SUPPORT_PHONE}."
        ),
    }


# ---------------------------------------------------------------------------
# Authenticated: leads
# ---------------------------------------------------------------------------


async def _get_business_id(user: User, db: AsyncSession):
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business.id


@router.get("/leads")
async def list_leads(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List captured chatbot leads (all demo leads; filtered by business when set)."""
    try:
        business_id = await _get_business_id(current_user, db)
        business_id_str = str(business_id)
    except HTTPException:
        business_id_str = None

    leads = list(_LEADS.values())
    if business_id_str:
        # Leads captured on the public widget carry no business_id in demo mode,
        # so return those plus any explicitly belonging to this business.
        leads = [
            lead
            for lead in leads
            if not lead.get("business_id") or lead.get("business_id") == business_id_str
        ]
    leads.sort(key=lambda l: l.get("created_at", ""), reverse=True)
    return {"leads": leads, "total": len(leads)}


@router.post("/leads/{lead_id}/convert")
async def convert_lead(
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Convert a chatbot lead into a Customer + Job."""
    lead = _LEADS.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("converted"):
        raise HTTPException(status_code=400, detail="Lead already converted")

    business_id = await _get_business_id(current_user, db)

    customer = Customer(
        business_id=business_id,
        full_name=lead.get("name") or "Website Lead",
        phone=lead.get("phone") or "00000000000",
        notes=(
            f"Chatbot lead {lead.get('reference')} "
            f"({lead.get('service') or 'general enquiry'}, {lead.get('postcode') or 'no postcode'}). "
            f"Source page: {lead.get('page_url') or 'website widget'}."
        ),
    )
    db.add(customer)
    await db.flush()

    job = Job(
        business_id=business_id,
        customer_id=customer.id,
        title=f"{(lead.get('service') or 'General enquiry').title()} — {lead.get('postcode') or 'TBC'}",
        description=(
            f"Converted from chatbot lead {lead.get('reference')} "
            f"(session {lead.get('session_id')}). "
            f"Contact: {lead.get('name') or 'unknown'} on {lead.get('phone') or 'unknown'}."
        ),
        status=JobStatus.QUOTE_REQUESTED,
        priority="urgent" if lead.get("service") == "emergency" else "normal",
        notes=f"Lead reference {lead.get('reference')}",
    )
    db.add(job)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(job)

    lead["converted"] = True
    lead["status"] = "converted"
    lead["business_id"] = str(business_id)
    lead["customer_id"] = str(customer.id)
    lead["job_id"] = str(job.id)

    return {"customer_id": str(customer.id), "job_id": str(job.id)}
