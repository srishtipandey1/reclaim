from __future__ import annotations

import os
from typing import Any

import razorpay


class RazorpayClient:
    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self.client = client
            return
        key_id = os.getenv('RAZORPAY_KEY_ID', '')
        key_secret = os.getenv('RAZORPAY_KEY_SECRET', '')
        if not key_id or not key_secret:
            raise RuntimeError('Razorpay credentials are not configured')
        self.client = razorpay.Client(auth=(key_id, key_secret))

    def fetch_subscription(self, subscription_id: str) -> dict[str, Any]:
        return self.client.subscription.fetch(subscription_id)

    def list_invoices(self, *, subscription_id: str | None = None) -> dict[str, Any]:
        params = {'subscription_id': subscription_id} if subscription_id else None
        return self.client.invoice.all(params) if params else self.client.invoice.all()

    def fetch_invoice(self, invoice_id: str) -> dict[str, Any]:
        return self.client.invoice.fetch(invoice_id)

    def notify_invoice(self, invoice_id: str, medium: str = 'email') -> dict[str, Any]:
        return self.client.invoice.notify_by(invoice_id, medium)
