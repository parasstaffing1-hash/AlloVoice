import time
import httpx

BASE = "http://127.0.0.1:8000"
email = f"tel{int(time.time())}@voicefield.test"
r = httpx.post(f"{BASE}/api/auth/register", json={
    "email": email, "password": "TelTest123!", "full_name": "Tel Test"}, timeout=60)
assert r.status_code in (200, 201), r.text[:150]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = httpx.get(f"{BASE}/api/telephony/status", headers=H, timeout=60)
print("telephony status:", r.status_code, r.text[:250])
assert r.status_code == 200
print("TELEPHONY LIVE OK")
