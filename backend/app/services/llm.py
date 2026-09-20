"""General LLM service (default: DeepSeek, OpenAI-compatible API).

All AI reasoning in the app goes through `complete()` / `complete_json()`
so the provider is swappable via env. When no key is set, `is_configured()`
is False and callers must fall back to their heuristic logic — never 500.
"""
import json
import httpx
from app.core.config import get_settings

_DEFAULT_BASES = {
    "deepseek": "https://api.deepseek.com",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}

_TIMEOUT = 60.0


def is_configured() -> bool:
    s = get_settings()
    return bool((s.LLM_API_KEY or "").strip() or (s.GROQ_API_KEY or "").strip())


def _base_url() -> str:
    s = get_settings()
    if (s.LLM_BASE_URL or "").strip():
        return s.LLM_BASE_URL.rstrip("/")
    return _DEFAULT_BASES.get((s.LLM_PROVIDER or "deepseek").lower(),
                              _DEFAULT_BASES["deepseek"])


def _model() -> str:
    s = get_settings()
    return (s.LLM_MODEL or "").strip() or "deepseek-chat"


def _fallback_model() -> str:
    return (get_settings().LLM_FALLBACK_MODEL or "").strip()


def _route(model: str) -> tuple:
    """(base_url, api_key, headers) for a model.

    - `:free` suffix → OpenRouter free tier.
    - `deepseek/*` → OpenRouter (DeepSeek access lives there).
    - everything else → configured provider (Groq hosts qwen/*,
      openai/gpt-oss-*, meta-llama/*, whisper-*, groq/* natively)."""
    s = get_settings()
    if model.endswith(":free") or model.startswith("deepseek/"):
        key = s.LLM_API_KEY
        headers = {"Authorization": f"Bearer {key}"}
        headers["HTTP-Referer"] = getattr(s, "APP_URL", "") or ""
        headers["X-Title"] = "VoiceField"
        return "https://openrouter.ai/api/v1", key, headers
    provider = (s.LLM_PROVIDER or "deepseek").lower()
    # NOTE: a stale LLM_BASE_URL must never hijack another provider —
    # it only applies when the provider actually is OpenRouter/custom.
    if provider == "openrouter":
        base = ((s.LLM_BASE_URL or "").strip()
                or _DEFAULT_BASES["openrouter"])
    else:
        base = _DEFAULT_BASES.get(provider, _DEFAULT_BASES["deepseek"])
    key = ((s.GROQ_API_KEY or "").strip()
           if provider == "groq" else s.LLM_API_KEY)
    return base, key, {"Authorization": f"Bearer {key}"}


def _models() -> list:
    """Ordered model chain. LLM_MODELS (comma list) wins; else primary+fallback."""
    s = get_settings()
    raw = (getattr(s, "LLM_MODELS", "") or "").strip()
    if raw:
        seen = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        seen = [_model()]
        if _fallback_model() and _fallback_model() not in seen:
            seen.append(_fallback_model())
    return seen


def _retryable(exc: Exception, resp_status: int | None) -> bool:
    # Rate limits / upstream blips / timeouts / unpaid model (402) → next model.
    # Auth errors (401/403) and bad requests (400) → fail fast.
    if isinstance(exc, httpx.TimeoutException):
        return True
    return resp_status in (402, 408, 425, 429, 500, 502, 503, 504)


async def _post(payload: dict) -> dict:
    """POST chat/completions across [primary, fallback] models. Returns body."""
    s = get_settings()
    if not is_configured():
        raise RuntimeError("LLM not configured (LLM_API_KEY missing)")
    models = _models()
    has_images = any(isinstance(m.get("content"), list)
                     for m in payload.get("messages", [])
                     if isinstance(m, dict))
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for i, model in enumerate(models):
            body = dict(payload)
            body["model"] = model
            base, _key, headers = _route(model)
            if not (_key or "").strip():
                last_error = RuntimeError(f"No API key for route of {model}")
                if i < len(models) - 1:
                    continue
                raise last_error
            # Only the primary attempt uses strict JSON mode; fallbacks that
            # reject response_format (e.g. via Novita) retry without it below.
            try:
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json=body,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                text = ""
                try:
                    text = e.response.text or ""
                except Exception:
                    pass
                if ("structured" in text.lower()
                        and status == 400 and body.get("response_format")):
                    body.pop("response_format", None)
                    try:
                        resp = await client.post(
                            f"{base}/chat/completions",
                            headers=headers,
                            json=body,
                        )
                        resp.raise_for_status()
                        return resp.json()
                    except Exception as e2:
                        last_error = e2
                        continue
                last_error = e
                if i < len(models) - 1 and (
                        _retryable(e, status)
                        # Vision: model without image support → next model.
                        or (has_images and status == 400)):
                    continue
                raise
            except Exception as e:
                last_error = e
                if i < len(models) - 1 and _retryable(e, None):
                    continue
                raise
    raise RuntimeError(f"LLM call failed: {last_error}")


async def complete(
    prompt: str,
    system: str | None = None,
    json_mode: bool = False,
    max_tokens: int = 1200,
    temperature: float = 0.3,
) -> str:
    """Raw text completion. Raises RuntimeError if no key configured."""
    s = get_settings()
    if not is_configured():
        raise RuntimeError("LLM not configured (LLM_API_KEY missing)")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict = {
        "model": _model(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    data = await _post(payload)
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected LLM response shape: {e}")


async def complete_json(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.3,
) -> dict:
    """JSON-mode completion parsed to dict. Raises RuntimeError on failure."""
    text = await complete(prompt, system=system, json_mode=True,
                          max_tokens=max_tokens, temperature=temperature)
    # Strip markdown fences for models without structured-output support.
    import re as _re
    text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(),
                   flags=_re.MULTILINE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM did not return valid JSON: {e}")
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON was not an object")
    return parsed


async def complete_stream(
    prompt: str,
    system: str | None = None,
    max_tokens: int = 180,
    temperature: float = 0.3,
):
    """Stream a completion as text deltas (async generator).

    PRIMARY model only (first of _models()). No response_format on stream.
    Yields ``choices[0].delta.content`` strings parsed from SSE
    ``data: {...}`` lines (skips ``[DONE]``). Raises RuntimeError on ANY
    error so callers fall back to non-stream complete().
    """
    s = get_settings()
    if not is_configured():
        raise RuntimeError("LLM not configured (LLM_API_KEY missing)")
    models = _models()
    primary = models[0] if models else _model()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload: dict = {
        "model": primary,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    base, _key, headers = _route(primary)
    if not (_key or "").strip():
        raise RuntimeError(f"No API key for route of {primary}")
    try:
        # Per-chunk read timeout: a stalled free-tier stream must fail
        # fast (callers finalize the partial reply) instead of hanging.
        # 45s gaps allowed — first tokens on free queues can take ~25s.
        _timeout = httpx.Timeout(90.0, connect=15.0, read=45.0,
                                 write=15.0, pool=15.0)
        async with httpx.AsyncClient(timeout=_timeout) as client:
            async with client.stream(
                "POST",
                f"{base}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    stripped = line.strip()
                    if not stripped.startswith("data:"):
                        continue
                    data_str = stripped[5:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue
                    try:
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
                    except Exception:
                        continue
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"LLM stream failed: {e}") from e


async def complete_with_tools(
    messages: list,
    tools: list,
    max_tokens: int = 300,
) -> dict:
    """Tool-calling completion on the PRIMARY model only.

    POSTs ``messages`` + ``tools`` (tool_choice=auto) and returns the raw
    chat/completions body dict so callers can inspect
    ``choices[0].message.tool_calls``. Raises RuntimeError on ANY error
    so callers fall back to plain complete()/groq_chat().
    """
    if not is_configured():
        raise RuntimeError("LLM not configured (LLM_API_KEY missing)")
    if not messages:
        raise RuntimeError("complete_with_tools: empty messages")
    if not tools:
        raise RuntimeError("complete_with_tools: empty tools")
    models = _models()
    primary = models[0] if models else _model()
    base, _key, headers = _route(primary)
    if not (_key or "").strip():
        raise RuntimeError(f"No API key for route of {primary}")
    payload: dict = {
        "model": primary,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"LLM tools call failed: {e}") from e
    try:
        _ = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected LLM tools response shape: {e}")
    return data


async def describe_image(
    image_base64: str,
    prompt: str,
    max_tokens: int = 600,
    temperature: float = 0.2,
) -> str:
    """Vision: describe/analyse a base64 JPEG image. Raw text reply.
    Raises RuntimeError if no key configured or call fails. No
    response_format flag (vision models often reject it) — callers
    asking for JSON must strip fences and parse defensively."""
    s = get_settings()
    if not is_configured():
        raise RuntimeError("LLM not configured (LLM_API_KEY missing)")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{image_base64}"}},
        ],
    }]
    data = await _post({"messages": messages,
                        "temperature": temperature, "max_tokens": max_tokens})
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected LLM response shape: {e}")
