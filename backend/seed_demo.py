"""Demo seed script for Allo backend (run manually, never imported).

Usage:
    python seed_demo.py

Seeds via HTTP against http://127.0.0.1:8000:
  1. Registers demo@voicefield.demo with a RANDOM password (printed at end;
     never hardcoded). If the user already exists, aborts with a message.
  2. Creates 1 customer, 2 jobs, 1 quote, 1 KB article.

Every step is tolerant: failures print a skip message, never a traceback.
"""

import secrets
import sys

import httpx

BASE_URL = "http://127.0.0.1:8000"
DEMO_EMAIL = "demo@voicefield.demo"
TIMEOUT = 15.0


def _ok(resp: httpx.Response) -> bool:
    return 200 <= resp.status_code < 300


def main() -> int:
    password = secrets.token_urlsafe(12)
    client = httpx.Client(base_url=BASE_URL, timeout=TIMEOUT)
    token = ""
    customer_id = ""
    job_ids: list = []
    quote_id = ""
    article_id = ""

    # 1. Register ---------------------------------------------------------
    try:
        resp = client.post(
            "/api/auth/register",
            json={
                "email": DEMO_EMAIL,
                "password": password,
                "full_name": "Demo User",
            },
        )
        if resp.status_code == 400 and "already registered" in resp.text.lower():
            print(f"User {DEMO_EMAIL} already exists — aborting (nothing created).")
            return 0
        if not _ok(resp):
            print(f"Register failed (HTTP {resp.status_code}) — aborting.")
            return 1
        token = (resp.json().get("access_token") or "").strip()
        if not token:
            print("Register succeeded but no token returned — aborting.")
            return 1
        print(f"Registered {DEMO_EMAIL}")
    except Exception as e:
        print(f"Register failed: {e} — aborting.")
        return 1

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Customer ----------------------------------------------------------
    try:
        resp = client.post(
            "/api/customers/",
            headers=headers,
            json={
                "full_name": "Demo Customer",
                "email": "customer.demo@example.co.uk",
                "phone": "07911 123456",
                "company": "Demo Ltd",
                "notes": "Seeded demo customer",
            },
        )
        if _ok(resp):
            customer_id = str(resp.json().get("id") or "")
            print(f"Customer created: {customer_id}")
        else:
            print(f"Customer create failed (HTTP {resp.status_code}) — skipping.")
    except Exception as e:
        print(f"Customer create failed: {e} — skipping.")

    # 3. Jobs (2) ----------------------------------------------------------
    if customer_id:
        for i, title in enumerate(
            ["Demo boiler service", "Demo radiator repair"], start=1
        ):
            try:
                resp = client.post(
                    "/api/jobs/",
                    headers=headers,
                    json={
                        "customer_id": customer_id,
                        "title": title,
                        "description": f"Seeded demo job {i}",
                        "priority": "normal",
                    },
                )
                if _ok(resp):
                    jid = str(resp.json().get("id") or "")
                    job_ids.append(jid)
                    print(f"Job {i} created: {jid}")
                else:
                    print(f"Job {i} create failed (HTTP {resp.status_code}) — skipping.")
            except Exception as e:
                print(f"Job {i} create failed: {e} — skipping.")
    else:
        print("No customer — skipping jobs.")

    # 4. Quote (via first job) ---------------------------------------------
    if customer_id and job_ids:
        try:
            resp = client.post(
                "/api/quotes/",
                headers=headers,
                json={
                    "job_id": job_ids[0],
                    "customer_id": customer_id,
                    "title": "Demo quote",
                    "items": [
                        {
                            "description": "Labour — boiler service",
                            "quantity": 1,
                            "unit_price": 95.0,
                        },
                        {
                            "description": "Parts allowance",
                            "quantity": 1,
                            "unit_price": 25.0,
                        },
                    ],
                    "tax_rate": 20,
                    "notes": "Seeded demo quote",
                    "valid_days": 30,
                },
            )
            if _ok(resp):
                quote_id = str(resp.json().get("id") or "")
                print(f"Quote created: {quote_id}")
            else:
                print(f"Quote create failed (HTTP {resp.status_code}) — skipping.")
        except Exception as e:
            print(f"Quote create failed: {e} — skipping.")
    else:
        print("No customer/job — skipping quote.")

    # 5. KB article (query params per POST /api/kb/ route shape) ------------
    try:
        resp = client.post(
            "/api/kb/",
            headers=headers,
            params={
                "title": "Demo: how to book a visit",
                "content": (
                    "To book a visit, go to Jobs, choose New Job, pick the "
                    "customer and service, then assign an engineer."
                ),
                "category": "demo",
            },
        )
        if _ok(resp):
            article_id = str(resp.json().get("id") or "")
            print(f"KB article created: {article_id}")
        else:
            print(f"KB create failed (HTTP {resp.status_code}) — skipping.")
    except Exception as e:
        print(f"KB create failed: {e} — skipping.")

    # Summary ---------------------------------------------------------------
    print("---- demo seed summary ----")
    print(f"user: {DEMO_EMAIL}")
    print(f"password: {password}")
    print(f"customer: {customer_id or 'skipped'}")
    print(f"jobs: {', '.join(job_ids) if job_ids else 'skipped'}")
    print(f"quote: {quote_id or 'skipped'}")
    print(f"kb_article: {article_id or 'skipped'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
