"""Technician scorecards + job profitability analysis (VoiceField, UK field service SaaS).

Currency: GBP. Locale: en-GB.

Approximations (documented — schema has no dedicated reopen / SLA tables):
- first_time_fix_rate: no reopen/revisit tracking exists on Job, so it is
  approximated as completed_jobs / total_assigned * 100 (== completion_rate).
  Review counts are NOT mixed into the rate; they feed avg_rating instead.
- revenue (scorecards): sum of Invoice.total for the technician's jobs where
  Invoice.payment_status == 'paid'. Falls back to 0 when Invoice/job_id link
  or totals are missing.
- on_time_rate: completed jobs where completed_at <= scheduled_at + 24h grace.
  Jobs without both timestamps are excluded from the denominator; if none are
  assessable the rate defaults to 100.0 (neutral) so missing scheduling data
  does not punish technicians.
- profitability labour: (completed_at - started_at) hours * hourly_rate
  (Technician.hourly_rate or default GBP 45.0). Falls back to 60 minutes when
  timestamps/duration are missing.
- profitability materials: sum of InventoryUsage.quantity_used * item
  cost_price (fallback unit_price) when those tables/columns exist, else 0.
- profitability revenue per job: linked Invoice.total -> linked Quote.total
  -> Job.final_cost -> Job.estimated_cost -> 0.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import User, Job, Invoice, Review, Business, Customer, Payment
from app.routes.auth import get_current_user

# Technician / Quote / inventory / service models all exist in
# app.models.models (verified) — import defensively so a missing model
# can never crash this module at import time.
try:
    from app.models.models import Technician  # type: ignore
except Exception:  # pragma: no cover
    Technician = None  # type: ignore

try:
    from app.models.models import Quote  # type: ignore
except Exception:  # pragma: no cover
    Quote = None  # type: ignore

try:
    from app.models.models import InventoryUsage  # type: ignore
except Exception:  # pragma: no cover
    InventoryUsage = None  # type: ignore

try:
    from app.models.models import InventoryItem  # type: ignore
except Exception:  # pragma: no cover
    InventoryItem = None  # type: ignore

try:
    from app.models.models import Service  # type: ignore
except Exception:  # pragma: no cover
    Service = None  # type: ignore

router = APIRouter(prefix="/api/performance", tags=["performance"])

CURRENCY = "GBP"
LOCALE = "en-GB"
DEFAULT_HOURLY_RATE = 45.0
COMPLETED_STATUSES = {"completed", "invoiced", "paid"}


# ---------------------------------------------------------------- helpers ---

def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_value(job) -> str:
    raw = getattr(job, "status", None)
    try:
        # SQLAlchemy Enum stores the enum member; .value gives "completed" etc.
        if hasattr(raw, "value"):
            return str(raw.value).lower()
    except Exception:
        pass
    try:
        return str(raw).lower() if raw is not None else ""
    except Exception:
        return ""


def _is_completed(job) -> bool:
    return _status_value(job) in COMPLETED_STATUSES


def _period_start(period: str):
    now = datetime.utcnow()
    if period == "last_90_days":
        return now - timedelta(days=90)
    if period == "all":
        return None
    # default: last_30_days (also covers any unexpected value defensively)
    return now - timedelta(days=30)


async def _resolve_business(current_user: User, db: AsyncSession):
    """Resolve the business for owner/manager/technician callers."""
    # 1) Owner business (primary pattern used across the codebase).
    try:
        result = await db.execute(
            select(Business).where(Business.owner_id == current_user.id)
        )
        business = result.scalar_one_or_none()
        if business is not None:
            return business
    except Exception:
        pass

    # 2) Technician profile -> business.
    if Technician is not None:
        try:
            tech_res = await db.execute(
                select(Technician).where(
                    getattr(Technician, "user_id") == current_user.id
                )
            )
            tech_profile = tech_res.scalars().first()
            if tech_profile is not None:
                bid = getattr(tech_profile, "business_id", None)
                if bid is not None:
                    b_res = await db.execute(
                        select(Business).where(Business.id == bid)
                    )
                    business = b_res.scalar_one_or_none()
                    if business is not None:
                        return business
        except Exception:
            pass

    # 3) BusinessRole membership (manager/dispatcher/technician).
    try:
        from app.models.models import BusinessRole  # type: ignore

        role_res = await db.execute(
            select(BusinessRole).where(
                getattr(BusinessRole, "user_id") == current_user.id
            )
        )
        membership = role_res.scalars().first()
        if membership is not None:
            bid = getattr(membership, "business_id", None)
            if bid is not None:
                b_res = await db.execute(
                    select(Business).where(Business.id == bid)
                )
                business = b_res.scalar_one_or_none()
                if business is not None:
                    return business
    except Exception:
        pass

    return None


async def _list_technicians(business_id, db: AsyncSession):
    """Return Technician rows for the business, with User fallback."""
    techs = []
    if Technician is not None:
        try:
            res = await db.execute(
                select(Technician).where(
                    getattr(Technician, "business_id") == business_id
                )
            )
            techs = list(res.scalars().all())
        except Exception:
            techs = []
    if techs:
        return techs, "technician_model"

    # Fallback: User rows with role technician/engineer linked via BusinessRole.
    try:
        from app.models.models import BusinessRole  # type: ignore

        role_res = await db.execute(
            select(BusinessRole).where(
                getattr(BusinessRole, "business_id") == business_id
            )
        )
        memberships = list(role_res.scalars().all())
        user_ids = [
            getattr(m, "user_id", None)
            for m in memberships
            if str(getattr(m, "role", "")).lower() in ("technician", "engineer")
            or str(getattr(getattr(m, "role", ""), "value", "")).lower()
            in ("technician", "engineer")
        ]
        user_ids = [u for u in user_ids if u is not None]
        if user_ids:
            u_res = await db.execute(select(User).where(User.id.in_(user_ids)))
            return list(u_res.scalars().all()), "user_model"
    except Exception:
        pass
    return [], "none"


async def _tech_display_name(tech, db: AsyncSession) -> str:
    """Resolve a human name for a Technician row or User row."""
    # User-row fallback already has full_name.
    name = getattr(tech, "full_name", None)
    if name:
        return str(name)
    user_id = getattr(tech, "user_id", None)
    if user_id is not None:
        try:
            u_res = await db.execute(select(User).where(User.id == user_id))
            user = u_res.scalar_one_or_none()
            if user is not None and getattr(user, "full_name", None):
                return str(user.full_name)
        except Exception:
            pass
    # Last resort: skills / id fragment.
    skills = getattr(tech, "skills", None)
    if skills:
        return f"Technician ({str(skills)[:40]})"
    try:
        return f"Technician {str(getattr(tech, 'id', ''))[:8]}"
    except Exception:
        return "Technician"


def _tech_key(tech) -> str:
    try:
        return str(getattr(tech, "id"))
    except Exception:
        return ""


def _job_created_at(job):
    return getattr(job, "created_at", None)


def _in_period(job, start) -> bool:
    if start is None:
        return True
    created = _job_created_at(job)
    completed = getattr(job, "completed_at", None)
    try:
        if created is not None and created >= start:
            return True
        if completed is not None and completed >= start:
            return True
    except Exception:
        return True
    return False


def _composite_score(completion_rate, ftfr, avg_rating, review_count, on_time_rate) -> float:
    rating_score = (avg_rating / 5.0 * 100.0) if review_count > 0 else 70.0
    try:
        rating_score = max(0.0, min(100.0, float(rating_score)))
    except Exception:
        rating_score = 70.0
    score = (
        0.30 * float(completion_rate or 0.0)
        + 0.20 * float(ftfr or 0.0)
        + 0.25 * float(rating_score)
        + 0.25 * float(on_time_rate or 0.0)
    )
    return round(max(0.0, min(100.0, score)), 2)


async def _scorecard_for_tech(tech, business_id, start, db: AsyncSession) -> dict:
    tech_id = getattr(tech, "id", None)
    name = await _tech_display_name(tech, db)

    # --- jobs (simple select + python aggregation) ---
    try:
        if Technician is not None and isinstance(tech, Technician):
            jobs_res = await db.execute(
                select(Job).where(
                    Job.business_id == business_id,
                    Job.technician_id == tech_id,
                )
            )
        else:
            # User-row fallback: cannot join directly; no jobs attributable.
            jobs_res = await db.execute(
                select(Job).where(Job.business_id == business_id, Job.id == None)  # noqa: E711 -> empty set
            )
        all_jobs = [j for j in jobs_res.scalars().all() if _in_period(j, start)]
    except Exception:
        all_jobs = []

    jobs_total = len(all_jobs)
    completed_jobs = [j for j in all_jobs if _is_completed(j)]
    jobs_completed = len(completed_jobs)
    completion_rate = round(jobs_completed / jobs_total * 100.0, 2) if jobs_total else 0.0

    # First-time fix: approximated as completion rate (no reopen tracking).
    first_time_fix_rate = completion_rate

    # --- ratings via Review -> Job ---
    ratings: list[float] = []
    try:
        job_ids = [getattr(j, "id", None) for j in all_jobs]
        job_ids = [i for i in job_ids if i is not None]
        if job_ids:
            rev_res = await db.execute(
                select(Review).where(getattr(Review, "job_id").in_(job_ids))
            )
            for rev in rev_res.scalars().all():
                try:
                    r = getattr(rev, "rating", None)
                    if r is not None:
                        ratings.append(float(r))
                except Exception:
                    continue
    except Exception:
        ratings = []
    review_count = len(ratings)
    avg_rating = round(sum(ratings) / review_count, 2) if review_count else 0.0

    # --- revenue: paid invoices linked by job ---
    revenue = 0.0
    try:
        job_ids = [getattr(j, "id", None) for j in all_jobs]
        job_ids = [i for i in job_ids if i is not None]
        has_job_link = hasattr(Invoice, "job_id")
        if job_ids and has_job_link:
            inv_res = await db.execute(
                select(Invoice).where(getattr(Invoice, "job_id").in_(job_ids))
            )
            for inv in inv_res.scalars().all():
                try:
                    status = getattr(inv, "payment_status", None)
                    status_str = (
                        str(status.value).lower()
                        if hasattr(status, "value")
                        else str(status).lower()
                    )
                except Exception:
                    status_str = ""
                if status_str == "paid":
                    revenue += _to_float(getattr(inv, "total", 0.0))
    except Exception:
        revenue = 0.0
    revenue = round(revenue, 2)

    # --- on-time: scheduled_at vs completed_at (+24h grace) ---
    on_time = 0
    assessable = 0
    try:
        for job in completed_jobs:
            scheduled = getattr(job, "scheduled_at", None)
            completed_at = getattr(job, "completed_at", None)
            if scheduled is None or completed_at is None:
                continue
            try:
                assessable += 1
                if completed_at <= scheduled + timedelta(hours=24):
                    on_time += 1
            except Exception:
                assessable -= 1
                continue
    except Exception:
        pass
    on_time_rate = round(on_time / assessable * 100.0, 2) if assessable else 100.0

    score = _composite_score(
        completion_rate, first_time_fix_rate, avg_rating, review_count, on_time_rate
    )

    return {
        "technician_id": _tech_key(tech),
        "name": name,
        "jobs_completed": jobs_completed,
        "jobs_total": jobs_total,
        "completion_rate": completion_rate,
        "first_time_fix_rate": first_time_fix_rate,
        "avg_rating": avg_rating,
        "review_count": review_count,
        "revenue": revenue,
        "on_time_rate": on_time_rate,
        "score": score,
    }


def _labour_cost_for_job(job, hourly_rate: float) -> tuple[float, float]:
    """Return (labour_cost, hours). Defensive around missing timestamps."""
    hours = None
    try:
        started = getattr(job, "started_at", None)
        completed = getattr(job, "completed_at", None)
        if started is not None and completed is not None:
            secs = (completed - started).total_seconds()
            if secs and secs > 0:
                hours = secs / 3600.0
        if hours is None:
            dur = getattr(job, "duration_minutes", None)
            if dur is not None:
                hours = _to_float(dur) / 60.0
    except Exception:
        hours = None
    if not hours or hours <= 0:
        hours = 1.0  # default 60 minutes when duration unknown
    # Clamp absurd values (e.g. clock errors) to a single 8h shift.
    try:
        hours = max(0.0, min(float(hours), 8.0))
    except Exception:
        hours = 1.0
    try:
        rate = float(hourly_rate) if hourly_rate else DEFAULT_HOURLY_RATE
    except Exception:
        rate = DEFAULT_HOURLY_RATE
    return round(hours * rate, 2), round(hours, 2)


def _revenue_for_job(job, invoice_total, quote_total) -> float:
    if invoice_total is not None:
        return round(_to_float(invoice_total), 2)
    if quote_total is not None:
        return round(_to_float(quote_total), 2)
    for attr in ("final_cost", "estimated_cost"):
        try:
            val = getattr(job, attr, None)
            if val is not None:
                return round(_to_float(val), 2)
        except Exception:
            continue
    return 0.0


# ---------------------------------------------------------------- endpoints ---

@router.get("/scorecards")
async def list_scorecards(
    period: str = Query(default="last_30_days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Per-technician scorecards for the caller's business."""
    if period not in ("last_30_days", "last_90_days", "all"):
        period = "last_30_days"
    start = _period_start(period)

    business = await _resolve_business(current_user, db)
    if business is None:
        return {"technicians": [], "period": period, "currency": CURRENCY, "locale": LOCALE}

    techs, _mode = await _list_technicians(business.id, db)
    cards = []
    for tech in techs:
        try:
            cards.append(await _scorecard_for_tech(tech, business.id, start, db))
        except Exception:
            continue
    # Sort by composite score desc for convenience.
    cards.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    return {
        "technicians": cards,
        "period": period,
        "currency": CURRENCY,
        "locale": LOCALE,
    }


@router.get("/scorecards/{technician_id}")
async def technician_scorecard_detail(
    technician_id: str,
    period: str = Query(default="last_30_days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detail scorecard for one technician + recent jobs + rating breakdown."""
    if period not in ("last_30_days", "last_90_days", "all"):
        period = "last_30_days"
    start = _period_start(period)

    business = await _resolve_business(current_user, db)
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    tech = None
    if Technician is not None:
        try:
            tech_res = await db.execute(
                select(Technician).where(
                    getattr(Technician, "business_id") == business.id,
                    getattr(Technician, "id") == technician_id,
                )
            )
            tech = tech_res.scalar_one_or_none()
        except Exception:
            # technician_id may not parse as UUID — fall through to 404.
            tech = None
    if tech is None:
        raise HTTPException(status_code=404, detail="Technician not found")

    card = await _scorecard_for_tech(tech, business.id, start, db)

    # Recent jobs (last 10).
    recent_jobs = []
    try:
        jobs_res = await db.execute(
            select(Job)
            .where(
                Job.business_id == business.id,
                Job.technician_id == getattr(tech, "id"),
            )
            .order_by(getattr(Job, "created_at").desc())
            .limit(10)
        )
        for job in jobs_res.scalars().all():
            try:
                created = getattr(job, "created_at", None)
                recent_jobs.append(
                    {
                        "job_id": str(getattr(job, "id")),
                        "title": getattr(job, "title", "") or "",
                        "status": _status_value(job),
                        "date": created.isoformat() if created else None,
                    }
                )
            except Exception:
                continue
    except Exception:
        recent_jobs = []

    # Rating breakdown {5:n, 4:n, ...}.
    breakdown = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    try:
        all_res = await db.execute(
            select(Job).where(
                Job.business_id == business.id,
                Job.technician_id == getattr(tech, "id"),
            )
        )
        all_ids = [getattr(j, "id", None) for j in all_res.scalars().all()]
        all_ids = [i for i in all_ids if i is not None]
        if all_ids:
            rev_res = await db.execute(
                select(Review).where(getattr(Review, "job_id").in_(all_ids))
            )
            for rev in rev_res.scalars().all():
                try:
                    r = int(float(getattr(rev, "rating", 0)))
                    if 1 <= r <= 5:
                        breakdown[str(r)] += 1
                except Exception:
                    continue
    except Exception:
        pass

    card["recent_jobs"] = recent_jobs
    card["rating_breakdown"] = breakdown
    card["period"] = period
    card["currency"] = CURRENCY
    card["locale"] = LOCALE
    return card


@router.get("/leaderboard")
async def leaderboard(
    period: str = Query(default="last_30_days"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Technicians ranked by composite score (desc)."""
    if period not in ("last_30_days", "last_90_days", "all"):
        period = "last_30_days"
    start = _period_start(period)

    business = await _resolve_business(current_user, db)
    if business is None:
        return {"leaderboard": [], "period": period, "currency": CURRENCY, "locale": LOCALE}

    techs, _mode = await _list_technicians(business.id, db)
    cards = []
    for tech in techs:
        try:
            cards.append(await _scorecard_for_tech(tech, business.id, start, db))
        except Exception:
            continue
    cards.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    board = [
        {
            "rank": i + 1,
            "technician_id": c.get("technician_id"),
            "name": c.get("name"),
            "score": c.get("score"),
            "revenue": c.get("revenue"),
            "avg_rating": c.get("avg_rating"),
            "jobs_completed": c.get("jobs_completed"),
        }
        for i, c in enumerate(cards)
    ]
    return {
        "leaderboard": board,
        "period": period,
        "currency": CURRENCY,
        "locale": LOCALE,
    }


@router.get("/profitability")
async def profitability(
    group_by: str = Query(default="job_type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Job profitability grouped by job_type | technician | month."""
    if group_by not in ("job_type", "technician", "month"):
        group_by = "job_type"

    business = await _resolve_business(current_user, db)
    if business is None:
        return {
            "groups": [],
            "totals": {"revenue": 0.0, "cost": 0.0, "profit": 0.0, "margin_pct": 0.0},
            "group_by": group_by,
            "currency": CURRENCY,
            "locale": LOCALE,
        }

    # Completed jobs for the business.
    try:
        jobs_res = await db.execute(
            select(Job).where(Job.business_id == business.id)
        )
        jobs = [j for j in jobs_res.scalars().all() if _is_completed(j)]
    except Exception:
        jobs = []

    job_ids = [getattr(j, "id", None) for j in jobs]
    job_ids = [i for i in job_ids if i is not None]

    # Invoice totals by job.
    invoice_by_job: dict = {}
    try:
        if job_ids and hasattr(Invoice, "job_id"):
            inv_res = await db.execute(
                select(Invoice).where(getattr(Invoice, "job_id").in_(job_ids))
            )
            for inv in inv_res.scalars().all():
                try:
                    invoice_by_job[str(getattr(inv, "job_id"))] = _to_float(
                        getattr(inv, "total", 0.0)
                    )
                except Exception:
                    continue
    except Exception:
        invoice_by_job = {}

    # Quote totals by job (fallback revenue).
    quote_by_job: dict = {}
    if Quote is not None:
        try:
            if job_ids and hasattr(Quote, "job_id"):
                q_res = await db.execute(
                    select(Quote).where(getattr(Quote, "job_id").in_(job_ids))
                )
                for q in q_res.scalars().all():
                    try:
                        quote_by_job[str(getattr(q, "job_id"))] = _to_float(
                            getattr(q, "total", 0.0)
                        )
                    except Exception:
                        continue
        except Exception:
            quote_by_job = {}

    # Materials cost by job (defensive — tables/columns may be absent).
    materials_by_job: dict = {}
    if InventoryUsage is not None:
        try:
            if job_ids and hasattr(InventoryUsage, "job_id"):
                u_res = await db.execute(
                    select(InventoryUsage).where(
                        getattr(InventoryUsage, "job_id").in_(job_ids)
                    )
                )
                usages = list(u_res.scalars().all())
                # Item price lookup.
                price_by_item: dict = {}
                if InventoryItem is not None and usages:
                    try:
                        item_ids = list(
                            {
                                getattr(u, "item_id", None)
                                for u in usages
                                if getattr(u, "item_id", None) is not None
                            }
                        )
                        if item_ids:
                            items_res = await db.execute(
                                select(InventoryItem).where(
                                    getattr(InventoryItem, "id").in_(item_ids)
                                )
                            )
                            for item in items_res.scalars().all():
                                try:
                                    cost = getattr(item, "cost_price", None)
                                    if cost is None:
                                        cost = getattr(item, "unit_price", 0.0)
                                    price_by_item[str(getattr(item, "id"))] = _to_float(
                                        cost
                                    )
                                except Exception:
                                    continue
                    except Exception:
                        price_by_item = {}
                for u in usages:
                    try:
                        jid = str(getattr(u, "job_id"))
                        qty = _to_float(getattr(u, "quantity_used", 0))
                        price = price_by_item.get(str(getattr(u, "item_id", "")), 0.0)
                        materials_by_job[jid] = materials_by_job.get(jid, 0.0) + qty * price
                    except Exception:
                        continue
        except Exception:
            materials_by_job = {}

    # Technician hourly rates + names.
    rate_by_tech: dict = {}
    name_by_tech: dict = {}
    if Technician is not None:
        try:
            t_res = await db.execute(
                select(Technician).where(
                    getattr(Technician, "business_id") == business.id
                )
            )
            for t in t_res.scalars().all():
                try:
                    tid = str(getattr(t, "id"))
                    rate_by_tech[tid] = _to_float(
                        getattr(t, "hourly_rate", DEFAULT_HOURLY_RATE)
                        or DEFAULT_HOURLY_RATE,
                        DEFAULT_HOURLY_RATE,
                    )
                    name_by_tech[tid] = await _tech_display_name(t, db)
                except Exception:
                    continue
        except Exception:
            pass

    # Service names for job_type grouping.
    service_name_by_id: dict = {}
    if Service is not None:
        try:
            s_res = await db.execute(
                select(Service).where(
                    getattr(Service, "business_id") == business.id
                )
            )
            for s in s_res.scalars().all():
                try:
                    service_name_by_id[str(getattr(s, "id"))] = str(
                        getattr(s, "name", "general") or "general"
                    )
                except Exception:
                    continue
        except Exception:
            pass

    def _group_key(job) -> str:
        try:
            if group_by == "technician":
                tid = getattr(job, "technician_id", None)
                if tid is None:
                    return "Unassigned"
                return name_by_tech.get(str(tid), f"Technician {str(tid)[:8]}")
            if group_by == "month":
                dt = getattr(job, "completed_at", None) or getattr(
                    job, "created_at", None
                )
                try:
                    return dt.strftime("%Y-%m") if dt else "unknown"
                except Exception:
                    return "unknown"
            # job_type (default): Job has no dedicated job_type column, so
            # resolve via Service name -> priority -> "general".
            for attr in ("job_type", "service_type", "category"):
                try:
                    val = getattr(job, attr, None)
                    if val:
                        return str(val)
                except Exception:
                    continue
            try:
                sid = getattr(job, "service_id", None)
                if sid is not None and str(sid) in service_name_by_id:
                    return service_name_by_id[str(sid)]
            except Exception:
                pass
            try:
                prio = getattr(job, "priority", None)
                if prio:
                    return f"general ({str(prio)})"
            except Exception:
                pass
            title = getattr(job, "title", None)
            # Do not explode cardinality on free-text titles; keep "general".
            _ = title
            return "general"
        except Exception:
            return "general" if group_by == "job_type" else "unknown"

    groups: dict = {}
    total_revenue = 0.0
    total_cost = 0.0

    for job in jobs:
        try:
            jid = str(getattr(job, "id"))
        except Exception:
            continue
        revenue = _revenue_for_job(
            job, invoice_by_job.get(jid), quote_by_job.get(jid)
        )
        tid = getattr(job, "technician_id", None)
        hourly = rate_by_tech.get(str(tid), DEFAULT_HOURLY_RATE) if tid else DEFAULT_HOURLY_RATE
        labour, _hours = _labour_cost_for_job(job, hourly)
        materials = round(materials_by_job.get(jid, 0.0), 2)
        cost = round(labour + materials, 2)

        key = _group_key(job)
        g = groups.setdefault(key, {"key": key, "jobs": 0, "revenue": 0.0, "cost": 0.0})
        g["jobs"] += 1
        g["revenue"] = round(g["revenue"] + revenue, 2)
        g["cost"] = round(g["cost"] + cost, 2)
        total_revenue = round(total_revenue + revenue, 2)
        total_cost = round(total_cost + cost, 2)

    group_list = []
    for g in groups.values():
        profit = round(g["revenue"] - g["cost"], 2)
        margin = round(profit / g["revenue"] * 100.0, 2) if g["revenue"] else 0.0
        group_list.append(
            {
                "key": g["key"],
                "jobs": g["jobs"],
                "revenue": g["revenue"],
                "cost": g["cost"],
                "profit": profit,
                "margin_pct": margin,
            }
        )
    group_list.sort(key=lambda g: g["profit"], reverse=True)

    total_profit = round(total_revenue - total_cost, 2)
    total_margin = round(total_profit / total_revenue * 100.0, 2) if total_revenue else 0.0

    return {
        "groups": group_list,
        "totals": {
            "revenue": total_revenue,
            "cost": total_cost,
            "profit": total_profit,
            "margin_pct": total_margin,
        },
        "group_by": group_by,
        "currency": CURRENCY,
        "locale": LOCALE,
    }


@router.get("/job/{job_id}/profit")
async def job_profit(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Single-job P&L: revenue, labour, materials, profit, margin."""
    business = await _resolve_business(current_user, db)
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")

    try:
        job_res = await db.execute(
            select(Job).where(
                Job.business_id == business.id,
                Job.id == job_id,
            )
        )
        job = job_res.scalar_one_or_none()
    except Exception:
        job = None
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Revenue: invoice -> quote -> final/estimated cost.
    invoice_total = None
    try:
        if hasattr(Invoice, "job_id"):
            inv_res = await db.execute(
                select(Invoice).where(getattr(Invoice, "job_id") == getattr(job, "id"))
            )
            inv = inv_res.scalars().first()
            if inv is not None:
                invoice_total = _to_float(getattr(inv, "total", None))
    except Exception:
        invoice_total = None

    quote_total = None
    if Quote is not None:
        try:
            if hasattr(Quote, "job_id"):
                q_res = await db.execute(
                    select(Quote).where(getattr(Quote, "job_id") == getattr(job, "id"))
                )
                quote = q_res.scalars().first()
                if quote is not None:
                    quote_total = _to_float(getattr(quote, "total", None))
        except Exception:
            quote_total = None

    revenue = _revenue_for_job(job, invoice_total, quote_total)

    # Hourly rate for assigned technician.
    hourly_rate = DEFAULT_HOURLY_RATE
    tech_name = "Unassigned"
    try:
        tid = getattr(job, "technician_id", None)
        if tid is not None and Technician is not None:
            t_res = await db.execute(
                select(Technician).where(getattr(Technician, "id") == tid)
            )
            tech = t_res.scalar_one_or_none()
            if tech is not None:
                hourly_rate = _to_float(
                    getattr(tech, "hourly_rate", DEFAULT_HOURLY_RATE)
                    or DEFAULT_HOURLY_RATE,
                    DEFAULT_HOURLY_RATE,
                )
                tech_name = await _tech_display_name(tech, db)
    except Exception:
        pass

    labour_cost, hours = _labour_cost_for_job(job, hourly_rate)

    # Materials for this job.
    materials_cost = 0.0
    materials_items: list = []
    if InventoryUsage is not None:
        try:
            if hasattr(InventoryUsage, "job_id"):
                u_res = await db.execute(
                    select(InventoryUsage).where(
                        getattr(InventoryUsage, "job_id") == getattr(job, "id")
                    )
                )
                for u in u_res.scalars().all():
                    try:
                        qty = _to_float(getattr(u, "quantity_used", 0))
                        unit_cost = 0.0
                        item_name = str(getattr(u, "item_id", ""))[:8]
                        if InventoryItem is not None:
                            try:
                                i_res = await db.execute(
                                    select(InventoryItem).where(
                                        getattr(InventoryItem, "id")
                                        == getattr(u, "item_id")
                                    )
                                )
                                item = i_res.scalar_one_or_none()
                                if item is not None:
                                    cost = getattr(item, "cost_price", None)
                                    if cost is None:
                                        cost = getattr(item, "unit_price", 0.0)
                                    unit_cost = _to_float(cost)
                                    item_name = str(
                                        getattr(item, "name", item_name) or item_name
                                    )
                            except Exception:
                                pass
                        line = round(qty * unit_cost, 2)
                        materials_cost = round(materials_cost + line, 2)
                        materials_items.append(
                            {
                                "item": item_name,
                                "quantity": qty,
                                "unit_cost": round(unit_cost, 2),
                                "line_total": line,
                            }
                        )
                    except Exception:
                        continue
        except Exception:
            materials_cost = 0.0

    total_cost = round(labour_cost + materials_cost, 2)
    profit = round(revenue - total_cost, 2)
    margin_pct = round(profit / revenue * 100.0, 2) if revenue else 0.0

    try:
        title = getattr(job, "title", "") or ""
    except Exception:
        title = ""

    return {
        "job_id": str(getattr(job, "id")),
        "title": title,
        "status": _status_value(job),
        "technician": tech_name,
        "revenue": revenue,
        "labour_cost": labour_cost,
        "materials_cost": materials_cost,
        "total_cost": total_cost,
        "profit": profit,
        "margin_pct": margin_pct,
        "breakdown": {
            "labour_hours": hours,
            "hourly_rate": round(_to_float(hourly_rate, DEFAULT_HOURLY_RATE), 2),
            "invoice_total": invoice_total,
            "quote_total": quote_total,
            "materials_items": materials_items,
        },
        "currency": CURRENCY,
        "locale": LOCALE,
    }


@router.get("/clv")
async def customer_lifetime_value(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Customer lifetime value, sorted by total_spend desc, top 50."""
    business = await _resolve_business(current_user, db)
    if business is None:
        return {"customers": [], "currency": CURRENCY, "locale": LOCALE}

    try:
        cust_res = await db.execute(
            select(Customer).where(Customer.business_id == business.id)
        )
        customers = list(cust_res.scalars().all())
    except Exception:
        customers = []

    try:
        jobs_res = await db.execute(
            select(Job).where(Job.business_id == business.id)
        )
        jobs = list(jobs_res.scalars().all())
    except Exception:
        jobs = []

    # Paid invoice spend by customer (via Invoice.customer_id where present,
    # else via job -> customer linkage).
    spend_by_customer: dict = {}
    try:
        inv_res = await db.execute(
            select(Invoice).join(Job, getattr(Invoice, "job_id") == Job.id).where(
                Job.business_id == business.id
            )
            if hasattr(Invoice, "job_id")
            else select(Invoice).where(getattr(Invoice, "id") == None)  # noqa: E711 -> empty set
        )
        for inv in inv_res.scalars().all():
            try:
                status = getattr(inv, "payment_status", None)
                status_str = (
                    str(status.value).lower()
                    if hasattr(status, "value")
                    else str(status).lower()
                )
            except Exception:
                status_str = ""
            if status_str != "paid":
                continue
            cid = getattr(inv, "customer_id", None)
            if cid is None and hasattr(inv, "job_id"):
                # Fall back through the linked job's customer.
                try:
                    jid = getattr(inv, "job_id")
                    linked = next(
                        (j for j in jobs if str(getattr(j, "id", "")) == str(jid)),
                        None,
                    )
                    cid = getattr(linked, "customer_id", None) if linked else None
                except Exception:
                    cid = None
            if cid is None:
                continue
            spend_by_customer[str(cid)] = spend_by_customer.get(str(cid), 0.0) + _to_float(
                getattr(inv, "total", 0.0)
            )
    except Exception:
        spend_by_customer = {}

    jobs_by_customer: dict = {}
    for job in jobs:
        try:
            cid = getattr(job, "customer_id", None)
            if cid is None:
                continue
            jobs_by_customer.setdefault(str(cid), []).append(job)
        except Exception:
            continue

    rows = []
    for cust in customers:
        try:
            cid = str(getattr(cust, "id"))
        except Exception:
            continue
        c_jobs = jobs_by_customer.get(cid, [])
        job_count = len(c_jobs)
        total_spend = round(spend_by_customer.get(cid, 0.0), 2)
        avg_job_value = round(total_spend / job_count, 2) if job_count else 0.0

        dates = []
        for j in c_jobs:
            try:
                d = getattr(j, "created_at", None)
                if d is not None:
                    dates.append(d)
            except Exception:
                continue
        first = min(dates) if dates else None
        last = max(dates) if dates else None

        # Predicted annual value: annualise total spend; minimum 1 year window
        # so single-job / new customers conservatively predict == total to date.
        try:
            span_days = (last - first).days if (first and last) else 0
        except Exception:
            span_days = 0
        try:
            years = max(span_days / 365.0, 1.0)
            predicted = round(total_spend / years, 2) if years else total_spend
        except Exception:
            predicted = total_spend

        try:
            cust_name = (
                getattr(cust, "full_name", None)
                or getattr(cust, "company", None)
                or "Customer"
            )
        except Exception:
            cust_name = "Customer"

        rows.append(
            {
                "customer_id": cid,
                "name": str(cust_name),
                "total_spend": total_spend,
                "job_count": job_count,
                "avg_job_value": avg_job_value,
                "first_job": first.isoformat() if first else None,
                "last_job": last.isoformat() if last else None,
                "predicted_annual_value": predicted,
            }
        )

    rows.sort(key=lambda r: r["total_spend"], reverse=True)
    return {"customers": rows[:50], "currency": CURRENCY, "locale": LOCALE}


# Keep linters quiet about the intentionally imported Payment model
# (part of the required safe import set; reserved for paid-invoice checks).
_ = Payment


# UUID path-param coercion note: FastAPI passes technician_id/job_id as str;
# SQLAlchemy UUID columns compare fine against canonical UUID strings, and any
# unparseable value safely yields zero rows -> 404, never a 500.
_ = UUID
