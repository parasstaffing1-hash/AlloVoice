"""PostHog product analytics for VoiceField (UK GDPR: EU host default).

Keyless behaviour: when POSTHOG_API_KEY is missing/blank, capture() and
identify() are no-ops that never raise, so requests never break.
"""

from typing import Any, Dict, Optional

from app.core.config import get_settings

DEFAULT_HOST = "https://eu.posthog.com"


def _creds():
    try:
        settings = get_settings()
        api_key = (getattr(settings, "POSTHOG_API_KEY", "") or "").strip()
        host = (getattr(settings, "POSTHOG_HOST", "") or "").strip() or DEFAULT_HOST
    except Exception:
        return "", DEFAULT_HOST
    return api_key, host


def capture(event: str, distinct_id: str, properties: Optional[Dict[str, Any]] = None) -> None:
    """Send a PostHog event. Never raises; no-op when key missing."""
    try:
        api_key, host = _creds()
        if not api_key:
            return
        import posthog

        posthog.api_key = api_key
        # python posthog client uses `host` attribute (older `api_host` also accepted).
        try:
            posthog.host = host
        except Exception:
            pass
        try:
            posthog.api_host = host  # type: ignore[attr-defined]
        except Exception:
            pass
        posthog.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties=dict(properties or {}),
        )
    except Exception:
        # Analytics must never break the request.
        return


def identify(distinct_id: str, traits: Optional[Dict[str, Any]] = None) -> None:
    """Identify a user in PostHog. Never raises; no-op when key missing."""
    try:
        api_key, host = _creds()
        if not api_key:
            return
        import posthog

        posthog.api_key = api_key
        try:
            posthog.host = host
        except Exception:
            pass
        try:
            posthog.api_host = host  # type: ignore[attr-defined]
        except Exception:
            pass
        posthog.identify(
            distinct_id=str(distinct_id),
            properties=dict(traits or {}),
        )
    except Exception:
        return
