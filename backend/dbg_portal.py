import time
import httpx

BASE = "http://127.0.0.1:8000"
email = f"dbg{int(time.time())}@voicefield.test"
r = httpx.post(f"{BASE}/api/auth/register", json={
    "email": email, "password": "DbgTest123!", "full_name": "Dbg"}, timeout=60)
H = {"Authorization": f"Bearer {r.json()['access_token']}"}
r = httpx.post(f"{BASE}/api/customers/", json={
    "full_name": "Dbg Cust", "phone": "07911 123456"}, headers=H, timeout=60)
cid = r.json()["id"]
r = httpx.post(f"{BASE}/api/portal/login", json={"access_code": cid[:8]}, timeout=60)
print("login:", r.status_code)
PH = {"Authorization": f"Bearer {r.json()['token']}"}
r = httpx.get(f"{BASE}/api/portal/dashboard", headers=PH, timeout=60)
print("dashboard:", r.status_code, r.text[:400])
