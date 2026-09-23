"""Shared slowapi rate limiter for public endpoints.

Mirrors the pattern wired in app/main.py::

    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

Routes import THIS module's ``limiter`` and decorate endpoints::

    @router.post("/chat")
    @limiter.limit("10/minute")
    async def chat(request: Request, ...): ...

NOTE: slowapi requires the decorated endpoint to accept ``request: Request``.
The 429 shape is shared app-wide via main.py's handler and looks like::

    429 {"error": "Rate limit exceeded: 10 per 1 minute"}

Demo endpoints in voice_agent.py (demo-chat/demo-speak) intentionally do NOT
use this — they keep their custom per-IP token bucket (_demo_allow, 10/min).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Shared 429 JSON shape (produced by slowapi's _rate_limit_exceeded_handler
# registered in main.py). Documented here so every new limit matches it.
RATE_LIMIT_429_EXAMPLE = {"error": "Rate limit exceeded: 10 per 1 minute"}
