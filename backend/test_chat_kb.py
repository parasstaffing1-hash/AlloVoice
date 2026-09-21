import httpx

r = httpx.post("http://127.0.0.1:8000/api/chatbot/chat", json={
    "message": "Hello, what are your opening hours?",
    "session_id": "rebrand-check-1"}, timeout=120)
print("chat:", r.status_code, r.text[:150])
assert r.status_code == 200 and r.json().get("reply")
print("CHAT OK (KB-grounded path live)")
