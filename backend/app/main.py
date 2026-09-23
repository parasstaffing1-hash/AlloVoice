from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator
import socketio
from app.core.database import init_db
from app.routes import (
    auth, customers, jobs, quotes, invoices, voice, dashboard, reviews,
    postcodes, photos, realtime, notifications, whatsapp,
    payments, xero, emails, sms, gdpr, audit, rbac, mfa,
    webhooks, search, import_export, portal, calendar,
    contracts, inventory, feedback, knowledge_base, fleet,
    reports, branches, analytics, tracking, memberships,
    pricebook, scheduling, cis, ai_insights,
    compliance_certificates, uk_compliance, ai_quote, voice_notes, duration_prediction,
    quickbooks, review_platforms, marketing, chatbot, performance,
    warehouses, attendance, safety, branding, billing, voice_agent,
    gocardless, outlook, fault_codes, rams, realtime_voice, calls,
    telephony, agents,
)

# Sentry (guarded inside init_sentry — no-op without DSN)
from app.core.sentry import init_sentry
init_sentry()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False
)

app = FastAPI(
    title="VoiceField API",
    description="AI-powered field service management platform for UK businesses",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(GZipMiddleware, minimum_size=1000)
Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Core Routes ──────────────────────────────────────
app.include_router(auth.router)
app.include_router(customers.router)
app.include_router(jobs.router)
app.include_router(quotes.router)
app.include_router(invoices.router)
app.include_router(voice.router)
app.include_router(dashboard.router)
app.include_router(reviews.router)

# ─── UK Services ──────────────────────────────────────
app.include_router(postcodes.router)
app.include_router(photos.router)
app.include_router(realtime.router)
app.include_router(notifications.router)
app.include_router(whatsapp.router)

# ─── Production: Payments & Accounting ────────────────
app.include_router(payments.router)
app.include_router(xero.router)
app.include_router(gocardless.router)

# ─── Production: Communications ───────────────────────
app.include_router(emails.router)
app.include_router(sms.router)

# ─── Production: Security & Compliance ────────────────
app.include_router(gdpr.router)
app.include_router(audit.router)
app.include_router(rbac.router)
app.include_router(mfa.router)
app.include_router(webhooks.router)

# ─── Production: Search & Data ────────────────────────
app.include_router(search.router)
app.include_router(import_export.router)
app.include_router(portal.router)
app.include_router(calendar.router)
app.include_router(outlook.router)

# ─── Production: Business Operations ──────────────────
app.include_router(contracts.router)
app.include_router(inventory.router)
app.include_router(feedback.router)
app.include_router(knowledge_base.router)
app.include_router(memberships.router)

# ─── Production: Fleet & Branches ─────────────────────
app.include_router(fleet.router)
app.include_router(reports.router)
app.include_router(branches.router)
app.include_router(branches.business_router)
app.include_router(analytics.router)

# ─── Customer Tracking ───────────────────────────────────
app.include_router(tracking.router)

# ─── Price Book ──────────────────────────────────────────
app.include_router(pricebook.router)

# ─── Smart Scheduling ─────────────────────────────────────
app.include_router(scheduling.router)

# ─── AI Quote Builder ──────────────────────────────────────
app.include_router(ai_quote.router)

# ─── CIS Tax Management ───────────────────────────────────
app.include_router(cis.router)

# ─── Voice Notes & Predictions ────────────────────────────
app.include_router(voice_notes.router)
app.include_router(duration_prediction.router)

# ─── AI Insights ──────────────────────────────────────────
app.include_router(ai_insights.router)

# ─── UK Compliance Certificates ───────────────────────────
app.include_router(compliance_certificates.router)
app.include_router(uk_compliance.router)

# ─── Tier 4: Integrations ─────────────────────────────────
app.include_router(quickbooks.router)
app.include_router(review_platforms.router)
app.include_router(marketing.router)
app.include_router(chatbot.router)

# ─── Field Tools: Fault Codes + RAMS ────────────────────────
app.include_router(voice_agent.router)
app.include_router(fault_codes.router)
app.include_router(rams.router)
app.include_router(realtime_voice.router)
app.include_router(calls.router)
app.include_router(telephony.router)
app.include_router(agents.router)

# ─── Tier 5: Premium ──────────────────────────────────────
app.include_router(performance.router)
app.include_router(warehouses.router)
app.include_router(attendance.router)
app.include_router(safety.router)
app.include_router(branding.router)
app.include_router(billing.router)

# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(sio, app)


@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "voicefield-api", "version": "2.0.0"}


# ─── Socket.IO Events ───────────────────────────────

@sio.event
async def connect(sid, environ):
    pass


@sio.event
async def disconnect(sid):
    pass


@sio.event
async def join_dispatch(sid, data):
    business_id = data.get("business_id")
    if business_id:
        await sio.enter_room(sid, f"dispatch:{business_id}")
        await sio.emit("room_joined", {"room": "dispatch"}, room=sid)


@sio.event
async def join_job(sid, data):
    job_id = data.get("job_id")
    if job_id:
        await sio.enter_room(sid, f"job:{job_id}")
        await sio.emit("room_joined", {"room": f"job:{job_id}"}, room=sid)


async def emit_job_update(business_id: str, job_data: dict):
    await sio.emit("job_updated", job_data, room=f"dispatch:{business_id}")


async def emit_new_job(business_id: str, job_data: dict):
    await sio.emit("new_job", job_data, room=f"dispatch:{business_id}")


async def emit_job_status(job_id: str, status: str):
    await sio.emit("status_changed", {"job_id": job_id, "status": status}, room=f"job:{job_id}")
