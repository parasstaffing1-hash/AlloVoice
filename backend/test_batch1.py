import time
import httpx

BASE = "http://127.0.0.1:8000"


def call(method, path, **kw):
    """HTTP with retries for the flaky network path; returns response."""
    kw.setdefault("timeout", 45)
    last = None
    for attempt in range(4):
        try:
            r = httpx.request(method, f"{BASE}{path}", **kw)
            if r.status_code < 500:
                return r
            last = r
        except Exception as e:
            last = e
        time.sleep(5 * (attempt + 1))
    if isinstance(last, Exception):
        raise last
    return last


email = f"batch1{int(time.time())}@voicefield.test"
r = call("POST", "/api/auth/register", json={
    "email": email, "password": "Batch1Test123!", "full_name": "Batch One"})
assert r.status_code in (200, 201), r.text[:150]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# 1. Portal
r = call("POST", "/api/customers/", json={
    "full_name": "Portal Customer", "phone": "07911 123456"}, headers=H)
assert r.status_code in (200, 201), r.text[:150]
cid = r.json()["id"]
r = call("POST", "/api/portal/login", json={"access_code": cid[:8]})
print("portal login:", r.status_code, r.text[:100])
assert r.status_code == 200
PH = {"Authorization": f"Bearer {r.json()['token']}"}
r = call("GET", "/api/portal/dashboard", headers=PH)
d = r.json()
print("portal dashboard:", r.status_code, "| customer:", d.get("customer", {}).get("name"))
assert r.status_code == 200 and d.get("customer")

# 2. GDPR
r = call("POST", "/api/gdpr/consent?consent_type=marketing&granted=true", headers=H)
print("consent:", r.status_code, r.text[:100])
assert r.status_code == 200
me = call("GET", "/api/auth/me", headers=H).json()
uid = me.get("id") or me.get("user", {}).get("id")
r = call("POST", f"/api/gdpr/export-data/{uid}", headers=H)
d = r.json()
print("export:", r.status_code, "| keys:", list((d.get("data") or {}).keys())[:6])
assert r.status_code == 200 and (d.get("data") or {}).get("jobs") is not None

# 3. Notifications honest (no Novu key → not_configured, not fake success)
r = call("POST", f"/api/notifications/send?recipient_id={uid}&title=t&message=m",
         headers=H)
print("notify:", r.status_code, r.text[:150])
assert r.status_code == 200 and '"success":false' in r.text.replace(" ", ""), \
    "must be honest failure, never fake success"

# 4. Panic (trial Twilio: rejection recorded, alert kept)
r = call("PUT", "/api/safety/settings", json={
    "emergency_contacts": [{"name": "Test Contact", "phone": "07911 123456",
                             "relation": "test"}]}, headers=H)
print("safety settings:", r.status_code)
r = call("POST", "/api/safety/panic", json={
    "latitude": 53.4808, "longitude": -2.2426,
    "message": "batch1 verification"}, headers=H)
d = r.json()
print("panic:", r.status_code, "| alert:", bool(d.get("alert_id")),
      "| notifications:", d.get("notifications"))
assert r.status_code == 200 and d.get("alert_id")
print("BATCH1 BACKEND OK")
