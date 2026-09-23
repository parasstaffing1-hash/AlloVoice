import httpx

r = httpx.post("http://127.0.0.1:8000/api/agents/chat", json={
    "template_id": "voice-plumbing-uk",
    "message": "Emergency! A pipe has burst in my kitchen. I'm Dave Miller, postcode M14 4TQ, number 07911 123456 — please send someone out now!",
}, timeout=120)
print("status:", r.status_code)
d = r.json()
print("stage:", d.get("stage"))
print("lead_reference:", d.get("lead_reference"))
print("reply:", d.get("reply"))
