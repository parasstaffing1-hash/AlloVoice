# VoiceField — AI-powered field service management (UK)

Quotes from voice, 24/7 AI voice agent, dispatch, certificates (Gas Safety CP12, F-Gas, EICR),
invoicing with Stripe + GoCardless, Xero/QuickBooks sync, and full UK compliance (GDPR, CIS).

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 15 (App Router) + Tailwind + shadcn-style UI, deployed on **Cloudflare Workers** via OpenNext |
| Backend | FastAPI + SQLAlchemy (async) + PostgreSQL (Aiven) |
| Storage | Cloudflare R2 (photos, signatures, certificates) |
| Voice | faster-whisper (local STT) + edge-tts UK voices · Sarvam optional |
| AI | OpenRouter gateway (DeepSeek → Qwen → Ling fallback chain) |
| Email / SMS | Resend / Twilio |

## Local development

```bash
# Backend
cd backend
cp .env.example .env        # fill in keys (see table below)
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# Frontend
cd frontend
npm install
npm run dev -p 3002
```

App: http://localhost:3002 · API: http://localhost:8000/api/docs

## Environment variables

Copy `backend/.env.example` → `backend/.env`. Key groups:

| Group | Vars | Required? |
|-------|------|-----------|
| Database | `DATABASE_URL` (Aiven Postgres, TLS) | yes |
| Auth | `JWT_SECRET` (rotate before first user!) | yes |
| AI | `LLM_PROVIDER/LLM_API_KEY/LLM_MODEL…` (OpenRouter, free `:free` models work key-only) | for AI features |
| Voice | `SARVAM_API_KEY` (optional; local whisper/edge-tts are default) | no |
| Storage | `R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET_NAME` | for uploads |
| Email | `RESEND_API_KEY`, `EMAIL_FROM` | for emails |
| SMS | `TWILIO_ACCOUNT_SID/AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` or sender ID | for SMS |
| Payments | `STRIPE_*` (test keys fine until launch) | for cards/billing |
| Accounting | `XERO_*`, `QB_*`, `GOCARDLESS_*` | per integration |
| Comms | `BREVO_API_KEY`, `WHATSAPP_*`, `GOOGLE_*/MS_*` | per integration |

Frontend needs one var wherever it runs: `NEXT_PUBLIC_API_URL` (local default `http://localhost:8000`).

## Deploy the frontend to Cloudflare

Prerequisites: Cloudflare account + `npx wrangler login`.

```bash
cd frontend
npm run deploy      # build + deploy to Workers (worker name: voicefield)
npm run preview     # same, but preview locally in workerd first
```

Or connect the repo in Cloudflare dashboard → Workers → **Create from Git**:
- Build command: `npx opennextjs-cloudflare build && npx opennextjs-cloudflare deploy`
- Root directory: `frontend`
- Env vars: set `NEXT_PUBLIC_API_URL` to your backend URL (+ any other `NEXT_PUBLIC_*`)

## Deploy the backend (VPS)

FastAPI needs a real server (Hetzner VPS / Railway / Render). Rough path:

1. Provision Ubuntu VPS, install Docker.
2. Copy `backend/`, set `.env` from `.env.example` with production values.
3. Run with gunicorn+uvicorn workers behind Caddy/Nginx (TLS).
4. Run `alembic upgrade head` (baseline `0001` already stamped on the cloud DB).
5. Point Cloudflare DNS at the server (proxied), update frontend `NEXT_PUBLIC_API_URL`, OAuth redirect URIs, Stripe/Xero webhook URLs, Resend domain DNS.

## Tests

```bash
cd backend
python -m pytest tests/ -q   # smoke + stripe + xero + gocardless (TESTING=1, NullPool)
```

## Project layout

```
backend/   FastAPI app (app/routes = 55+ endpoint modules, app/services, alembic/)
frontend/  Next.js 15 app (38 pages, PWA, OpenNext Cloudflare adapter)
```

## Security notes

- `.env` files, `ca.pem`, `*-creds*.json` and local probe scripts are gitignored — **never commit keys**.
- Rotate `JWT_SECRET`, Meilisearch/Centrifugo keys before launch.
- `backend/ca.pem` (Aiven project CA, optional) upgrades DB TLS to verify-ca automatically.
