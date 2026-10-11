"""Billing — subscription checkout + webhooks (architecture §4 monetization).

The payment provider is injected behind a tiny protocol, so the app runs and
tests with a stub and switches to a real processor (Stripe, Paddle, …) by
passing a different provider. No key is required to develop.
"""
from __future__ import annotations

import logging
from typing import Protocol

from hashtagger.usage import UsageStore

log = logging.getLogger(__name__)

# plan -> price in cents/month
PLANS = {"free": 0, "pro": 900}


class PaymentError(Exception):
    """Raised when a charge fails; the tier must not change."""


class PaymentProvider(Protocol):
    def charge(self, *, account_id: str, plan: str, amount_cents: int) -> dict: ...


class StubPaymentProvider:
    """Dev/test provider: always succeeds, records what it was asked to charge."""

    def __init__(self) -> None:
        self.charges: list[dict] = []

    def charge(self, *, account_id: str, plan: str, amount_cents: int) -> dict:
        rec = {"account_id": account_id, "plan": plan, "amount_cents": amount_cents,
               "status": "paid"}
        self.charges.append(rec)
        return rec


class BillingService:
    """Creates checkouts and applies subscription webhooks to the usage store."""

    def __init__(self, *, usage: UsageStore, provider: PaymentProvider) -> None:
        self._usage = usage
        self._provider = provider

    def create_checkout(self, *, account_id: str, plan: str) -> dict:
        if plan not in PLANS:
            raise ValueError(f"unknown plan {plan!r}; expected one of {tuple(PLANS)}")
        amount = PLANS[plan]
        # A paid plan must charge successfully before the tier changes.
        result = self._provider.charge(account_id=account_id, plan=plan, amount_cents=amount)
        self._usage.set_tier(account_id, "pro" if plan == "pro" else "free")
        return result

    def handle_webhook(self, event: dict) -> dict:
        """Apply a subscription event. Idempotent for repeated deliveries."""
        etype = event.get("type")
        account_id = event.get("account_id")
        if not account_id:
            raise ValueError("webhook missing account_id")

        if etype in ("subscription.created", "subscription.renewed", "subscription.updated"):
            plan = event.get("plan", "pro")
            self._usage.set_tier(account_id, "pro" if plan == "pro" else "free")
        elif etype == "subscription.cancelled":
            self._usage.set_tier(account_id, "free")
        else:
            log.warning("unhandled webhook type: %s", etype)
            return {"handled": False}
        return {"handled": True, "tier": self._usage.tier(account_id)}
