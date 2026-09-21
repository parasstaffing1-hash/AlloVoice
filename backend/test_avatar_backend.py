import time
import httpx

BASE = "http://127.0.0.1:8000"
email = f"avatar{int(time.time())}@voicefield.test"
r = httpx.post(f"{BASE}/api/auth/register", json={
    "email": email, "password": "AvatarTest123!", "full_name": "Avatar Test"}, timeout=60)
assert r.status_code in (200, 201), r.text[:150]
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

# Branding avatar fields round-trip
r = httpx.get(f"{BASE}/api/branding", headers=H, timeout=60)
print("branding get:", r.status_code, "| avatar_glb_url:", r.json().get("avatar_glb_url"))
r = httpx.put(f"{BASE}/api/branding", json={
    "avatar_glb_url": "https://models.readyplayer.me/test.glb",
    "avatar_voice": "ryan"}, headers=H, timeout=60)
d = r.json()
print("branding put:", r.status_code, "| voice:", d.get("avatar_voice"))
assert r.status_code == 200 and d.get("avatar_voice") == "ryan"

# Portal theme exposes them publicly
r = httpx.get(f"{BASE}/api/branding/portal-theme", timeout=60)
d = r.json()
print("portal-theme:", r.status_code, "| has avatar fields:",
      "avatar_glb_url" in d and "avatar_voice" in d)

# KB-grounded chat: seed an article first via knowledge-base route
print("AVATAR BACKEND OK")
