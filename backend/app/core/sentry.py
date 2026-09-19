"""Guarded Sentry initialisation for VoiceField.

Boot must never fail without a DSN. Call init_sentry() at startup
(e.g. top of app/main.py, replacing the commented-out block):

    from app.core.sentry import init_sentry
    init_sentry()

When SENTRY_DSN is blank, this is a no-op.
"""

from app.core.config import get_settings


def init_sentry() -> bool:
    """Initialise sentry_sdk only when SENTRY_DSN is set. Returns True if enabled."""
    try:
        settings = get_settings()
        dsn = (getattr(settings, "SENTRY_DSN", "") or "").strip()
        if not dsn:
            return False
        environment = (getattr(settings, "SENTRY_ENVIRONMENT", "") or "").strip() or "development"
    except Exception:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=environment,
        )
        return True
    except Exception:
        # Observability must never break boot.
        return False
