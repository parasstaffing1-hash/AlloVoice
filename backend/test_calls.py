import time
import httpx

BASE = "http://localhost:8000"
email = f"calls{int(time.time())}@voicefield.test"
r = httpx.post(f"{BASE}/api/auth/register", json={
    "email": email, "password": "CallsTest123!", "full_name": "Calls Test"}, timeout=30)
assert r.status_code in (200, 201), r.text[:150]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = httpx.post(f"{BASE}/api/calls/start", json={
    "direction": "inbound", "channel": "realtime"}, headers=H, timeout=30)
print("start:", r.status_code, r.text[:120])
assert r.status_code == 200
cid = r.json()["id"]

for sp, tx in [("caller", "This is ridiculous, I have been waiting ages with no hot water!"),
               ("agent", "I am very sorry about that, let me sort this out right away."),
               ("caller", "Thanks, that is lovely, please book me in.")]:
    r = httpx.post(f"{BASE}/api/calls/{cid}/turn",
                   json={"speaker": sp, "text": tx}, headers=H, timeout=30)
    assert r.status_code == 200, r.text[:120]
print("turns: 200 x3")

r = httpx.post(f"{BASE}/api/calls/{cid}/end", json={"outcome": "booked"}, headers=H, timeout=120)
d = r.json()
print("end:", r.status_code, "| sentiment:", d.get("analysis", {}).get("sentiment"),
      "| actions:", len(d.get("analysis", {}).get("action_items", [])))
assert r.status_code == 200 and d.get("analysis", {}).get("summary")

r = httpx.get(f"{BASE}/api/calls/", headers=H, timeout=30)
body = r.json()
calls = body if isinstance(body, list) else body.get("calls", [])
print("list:", r.status_code, "calls:", len(calls))
print("CALLS E2E OK")
