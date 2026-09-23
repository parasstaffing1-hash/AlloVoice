import httpx

BASE = "http://127.0.0.1:8000/api/agents/chat"
cases = [
    ("voice-electrician-uk", "Help - my socket is sparking and there's a burning smell! What should I do?"),
    ("chat-saas", "Hi, I'd like to start a 14-day free trial. I'm Tom, email tom@example.com, company Acme."),
    ("chat-insurance-uk", "Hi, I'd like to start a motor claim - I'm Emma Stone, policy MTR-77881, email emma@example.com, phone 07123 456789."),
    ("chat-insurance-uk", "Can you give me stock tips to invest in?"),
]
for tid, msg in cases:
    r = httpx.post(BASE, json={"template_id": tid, "message": msg}, timeout=120)
    d = r.json()
    print("=" * 80)
    print("TEMPLATE:", tid, "| stage:", d.get("stage"), "| ref:", d.get("lead_reference"))
    print("REPLY:", d.get("reply"))
