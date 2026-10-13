"""
Webhook RECEIPT skeleton only — not a real handler. Real signature
verification needs each provider's own webhook signing secret, which
doesn't exist until a real Stripe/Flutterwave account does (blocked on
company registration, not on this codebase — see CLAUDE.md). Processing
an unverified webhook body would be a real vulnerability (anyone could
POST a fake "payment succeeded" event straight at this endpoint), so
this deliberately returns 501 rather than pretending to handle
anything — a safe placeholder, not a shortcut. Wire up real
verification + app/models/webhook_event.py's idempotency check once
real keys exist.
"""
import logging

from fastapi import APIRouter

from app.payments.payment_provider import PaymentProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments/webhooks", tags=["payments"])


@router.post("/{provider}", status_code=501)
async def receive_webhook(provider: PaymentProvider):
    logger.warning("Webhook received for %s but no real handler is wired up yet", provider.value)
    return {"detail": f"{provider.value} webhooks are not configured yet"}
