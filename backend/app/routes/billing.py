import json
import logging
import os
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.core.config import get_settings
from app.core.database import get_db  # noqa: F401  (no new tables; kept for future use)
from app.routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])
settings = get_settings()

stripe.api_key = settings.STRIPE_SECRET_KEY if hasattr(settings, "STRIPE_SECRET_KEY") else os.getenv("STRIPE_SECRET_KEY", "")

APP_URL = settings.APP_URL if hasattr(settings, "APP_URL") else os.getenv("APP_URL", "http://localhost:3002")

PLACEHOLDER_MARKERS = ("", "placeholder", "changeme", "xxx", "your-", "test-key", "sk_test_placeholder")


def _env_stripe_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key and hasattr(settings, "STRIPE_SECRET_KEY"):
        try:
            key = str(settings.STRIPE_SECRET_KEY or "")
        except Exception:
            key = ""
    return (key or "").strip()


def _env_webhook_secret() -> str:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret and hasattr(settings, "STRIPE_WEBHOOK_SECRET"):
        try:
            secret = str(settings.STRIPE_WEBHOOK_SECRET or "")
        except Exception:
            secret = ""
    return (secret or "").strip()


def _is_placeholder(value: str) -> bool:
    if not value:
        return True
    lowered = value.lower()
    if "placeholder" in lowered or "changeme" in lowered or "xxx" in lowered:
        return True
    if lowered in PLACEHOLDER_MARKERS:
        return True
    if not (lowered.startswith("sk_live_") or lowered.startswith("sk_test_") or lowered.startswith("rk_")):
        # Unknown format — treat short/obviously-fake values as unusable
        if len(value) < 20:
            return True
    return False


def _stripe_usable() -> bool:
    return not _is_placeholder(_env_stripe_key())


def _webhook_secret_usable() -> bool:
    secret = _env_webhook_secret()
    return bool(secret) and not _is_placeholder(secret)


def _price_env(name: str) -> Optional[str]:
    value = os.getenv(name, "") or ""
    value = value.strip()
    if not value or "placeholder" in value.lower():
        return None
    return value


def _plans() -> list[dict]:
    return [
        {
            "id": "starter",
            "name": "Starter",
            "monthly_gbp": 29,
            "yearly_gbp": 29 * 10,
            "seats_included": 1,
            "features": [
                "Up to 1 included seat, then per-seat",
                "Jobs, quotes & invoicing",
                "Customer management",
                "Email support",
            ],
            "stripe_price_id_monthly": _price_env("STRIPE_PRICE_STARTER_MONTHLY"),
            "stripe_price_id_yearly": _price_env("STRIPE_PRICE_STARTER_YEARLY"),
        },
        {
            "id": "growth",
            "name": "Growth",
            "monthly_gbp": 49,
            "yearly_gbp": 49 * 10,
            "seats_included": 3,
            "most_popular": True,
            "features": [
                "Up to 3 included seats, then per-seat",
                "Everything in Starter",
                "Scheduling optimisation & reminders",
                "Reviews & marketing tools",
                "Priority support",
            ],
            "stripe_price_id_monthly": _price_env("STRIPE_PRICE_GROWTH_MONTHLY"),
            "stripe_price_id_yearly": _price_env("STRIPE_PRICE_GROWTH_YEARLY"),
        },
        {
            "id": "trade",
            "name": "Trade",
            "monthly_gbp": 79,
            "yearly_gbp": 79 * 10,
            "seats_included": 10,
            "features": [
                "Up to 10 included seats, then per-seat",
                "Everything in Growth",
                "Multi-branch & fleet tools",
                "Advanced reports & API access",
                "Dedicated support",
            ],
            "stripe_price_id_monthly": _price_env("STRIPE_PRICE_TRADE_MONTHLY"),
            "stripe_price_id_yearly": _price_env("STRIPE_PRICE_TRADE_YEARLY"),
        },
    ]


def _plan_by_id(plan_id: str) -> Optional[dict]:
    for plan in _plans():
        if plan["id"] == plan_id:
            return plan
    return None


# In-memory subscription state keyed by business/owner id. No new tables.
_SUBSCRIPTIONS: dict[str, dict] = {}


def _owner_key(user) -> str:
    try:
        return str(user.id)
    except Exception:
        return str(getattr(user, "id", "unknown"))


def _default_trial() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "status": "trialing",
        "plan_id": None,
        "seats": 1,
        "billing_cycle": "monthly",
        "current_period_end": None,
        "trial_ends": (now + timedelta(days=14)).isoformat(),
    }


def _get_subscription(user) -> dict:
    key = _owner_key(user)
    sub = _SUBSCRIPTIONS.get(key)
    if not sub:
        sub = _default_trial()
        _SUBSCRIPTIONS[key] = sub
    return sub


class CheckoutRequest(BaseModel):
    plan_id: str
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    seats: int = Field(default=1, ge=1, le=1000)


@router.get("/plans")
async def list_plans():
    return {"plans": _plans(), "currency": "GBP"}


@router.post("/checkout")
async def create_checkout(data: CheckoutRequest, current_user=Depends(get_current_user)):
    plan = _plan_by_id(data.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan_id")

    key = _owner_key(current_user)
    existing = _SUBSCRIPTIONS.get(key) or _default_trial()
    pending = {
        **existing,
        "plan_id": data.plan_id,
        "seats": data.seats,
        "billing_cycle": data.billing_cycle,
        "pending": True,
    }
    _SUBSCRIPTIONS[key] = pending

    if not _stripe_usable():
        return {
            "checkout_url": None,
            "mode": "manual",
            "message": "Stripe is not configured (STRIPE_SECRET_KEY missing or placeholder). "
            "An admin will activate your subscription manually.",
        }

    try:
        stripe.api_key = _env_stripe_key()
        amount_gbp = plan["monthly_gbp"] if data.billing_cycle == "monthly" else plan["yearly_gbp"]
        interval = "month" if data.billing_cycle == "monthly" else "year"
        env_price = _price_env(
            f"STRIPE_PRICE_{data.plan_id.upper()}_{data.billing_cycle.upper()}"
        ) or (plan.get("stripe_price_id_monthly") if data.billing_cycle == "monthly" else plan.get("stripe_price_id_yearly"))

        if env_price:
            line_items = [{"price": env_price, "quantity": data.seats}]
        else:
            line_items = [
                {
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": int(amount_gbp * 100),
                        "recurring": {"interval": interval},
                        "product_data": {"name": f"Allo {plan['name']} ({data.billing_cycle})"},
                    },
                    "quantity": data.seats,
                }
            ]

        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=line_items,
            success_url=f"{APP_URL}/billing?success=1",
            cancel_url=f"{APP_URL}/billing?cancelled=1",
            client_reference_id=key,
            metadata={"owner_id": key, "plan_id": data.plan_id, "seats": str(data.seats)},
        )
        pending["stripe_session_id"] = session.get("id")
        _SUBSCRIPTIONS[key] = pending
        return {"checkout_url": session.get("url")}
    except Exception as e:
        logger.warning("Stripe checkout failed, falling back to manual: %s", e)
        return {
            "checkout_url": None,
            "mode": "manual",
            "message": f"Stripe checkout unavailable ({e}). An admin will activate your subscription manually.",
        }


@router.post("/webhook")
async def billing_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "") or request.headers.get("stripe-signature", "")

    event = None
    if _webhook_secret_usable():
        try:
            event = stripe.Webhook.construct_event(payload, sig, _env_webhook_secret())
        except Exception as e:
            logger.warning("Stripe webhook signature verification failed: %s", e)
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
    else:
        logger.warning("STRIPE_WEBHOOK_SECRET missing or placeholder — skipping webhook signature verification")
        try:
            event = json.loads(payload.decode("utf-8") or "{}")
        except Exception as e:
            logger.warning("Could not parse webhook payload: %s", e)
            return {"received": True}

    try:
        event_type = event.get("type", "") if isinstance(event, dict) else getattr(event, "type", "")
        data_obj = {}
        try:
            if isinstance(event, dict):
                data_obj = (event.get("data") or {}).get("object") or {}
            else:
                data_obj = event["data"]["object"]
        except Exception:
            data_obj = {}

        meta = (data_obj.get("metadata") or {}) if isinstance(data_obj, dict) else {}
        owner_id = str(meta.get("owner_id") or meta.get("business_id") or data_obj.get("client_reference_id") or "")

        if event_type == "checkout.session.completed":
            if owner_id:
                sub = _SUBSCRIPTIONS.get(owner_id) or _default_trial()
                sub.update(
                    {
                        "status": "active",
                        "plan_id": meta.get("plan_id") or sub.get("plan_id"),
                        "seats": int(meta.get("seats") or sub.get("seats") or 1),
                        "stripe_customer_id": data_obj.get("customer"),
                        "stripe_subscription_id": data_obj.get("subscription"),
                        "pending": False,
                    }
                )
                _SUBSCRIPTIONS[owner_id] = sub
        elif event_type == "customer.subscription.updated":
            customer_id = str(data_obj.get("customer") or "")
            target_key = owner_id
            if not target_key and customer_id:
                for k, v in _SUBSCRIPTIONS.items():
                    if v.get("stripe_customer_id") == customer_id:
                        target_key = k
                        break
            if target_key:
                sub = _SUBSCRIPTIONS.get(target_key) or _default_trial()
                period_end = data_obj.get("current_period_end")
                if isinstance(period_end, (int, float)):
                    period_end = datetime.fromtimestamp(period_end, tz=timezone.utc).isoformat()
                sub.update(
                    {
                        "status": data_obj.get("status") or sub.get("status"),
                        "seats": int(data_obj.get("quantity") or sub.get("seats") or 1),
                        "current_period_end": period_end or sub.get("current_period_end"),
                        "stripe_subscription_id": data_obj.get("id") or sub.get("stripe_subscription_id"),
                    }
                )
                _SUBSCRIPTIONS[target_key] = sub
        elif event_type == "customer.subscription.deleted":
            customer_id = str(data_obj.get("customer") or "")
            target_key = owner_id
            if not target_key and customer_id:
                for k, v in _SUBSCRIPTIONS.items():
                    if v.get("stripe_customer_id") == customer_id:
                        target_key = k
                        break
            if target_key:
                sub = _SUBSCRIPTIONS.get(target_key) or _default_trial()
                sub["status"] = "cancelled"
                _SUBSCRIPTIONS[target_key] = sub
    except Exception as e:
        logger.warning("Error handling billing webhook event: %s", e)

    return {"received": True}


@router.get("/subscription")
async def get_subscription(current_user=Depends(get_current_user)):
    sub = _get_subscription(current_user)
    return {
        "status": sub.get("status", "trialing"),
        "plan_id": sub.get("plan_id"),
        "seats": sub.get("seats", 1),
        "billing_cycle": sub.get("billing_cycle", "monthly"),
        "current_period_end": sub.get("current_period_end"),
        "trial_ends": sub.get("trial_ends"),
    }


@router.post("/portal")
async def billing_portal(current_user=Depends(get_current_user)):
    sub = _get_subscription(current_user)
    customer_id = sub.get("stripe_customer_id")

    if not _stripe_usable() or not customer_id:
        return {
            "portal_url": None,
            "mode": "manual",
            "message": "Billing portal unavailable (Stripe not configured or no Stripe customer yet). "
            "Contact support to manage your subscription.",
        }

    try:
        stripe.api_key = _env_stripe_key()
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_URL}/billing",
        )
        return {"portal_url": session.get("url")}
    except Exception as e:
        logger.warning("Stripe portal failed, falling back to manual: %s", e)
        return {
            "portal_url": None,
            "mode": "manual",
            "message": f"Billing portal unavailable ({e}). Contact support to manage your subscription.",
        }
