from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
from typing import Any

from src.db import get_connection

logger = logging.getLogger(__name__)

VALID_RAZORPAY_STATES = {
    'created',
    'authenticated',
    'active',
    'pending',
    'halted',
    'cancelled',
    'paused',
    'expired',
    'completed',
}


def verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
    if signature is None:
        raise ValueError('missing signature')
    expected = hmac.new(secret.encode('utf-8'), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError('invalid signature')


def _normalize_razorpay_state(event_type: str | None, payload: dict[str, Any]) -> str | None:
    if not payload:
        return None

    subscription = payload.get('payload', {}).get('subscription') or {}
    entity = subscription.get('entity') or subscription or {}
    state = entity.get('status') or subscription.get('status')
    if state in VALID_RAZORPAY_STATES:
        return state
    if event_type == 'subscription.activated':
        return 'active'
    if event_type == 'subscription.pending':
        return 'pending'
    if event_type == 'subscription.halted':
        return 'halted'
    if event_type == 'subscription.cancelled':
        return 'cancelled'
    return None


def _upsert_subscription(conn: sqlite3.Connection, subscription_id: str, state: str | None, state_event_at: int | None) -> None:
    if not subscription_id or state is None:
        return
    conn.execute(
        """
        INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, state_event_at, case_state)
        VALUES (?, 'live_dashboard', ?, ?, 'none')
        ON CONFLICT(razorpay_subscription_id) DO UPDATE SET
            razorpay_state = excluded.razorpay_state,
            state_event_at = excluded.state_event_at,
            updated_at = CURRENT_TIMESTAMP
        WHERE excluded.state_event_at >= subscriptions.state_event_at
        """,
        (subscription_id, state, state_event_at if state_event_at is not None else 0),
    )
    conn.commit()


def process_webhook_event(payload: dict[str, Any], event_id: str | None, db_path: str) -> None:
    if not event_id:
        logger.warning('webhook missing event id')
        return

    event_type = payload.get('event') or payload.get('type')
    if not event_type:
        logger.warning('webhook missing event type for event_id=%s', event_id)
        return

    conn = get_connection(db_path)
    try:
        try:
            subscription_payload = (payload.get('payload') or {}).get('subscription') or {}
            subscription_entity = subscription_payload.get('entity') or subscription_payload or {}
            subscription_id = subscription_entity.get('id') if isinstance(subscription_entity, dict) else None
            conn.execute(
                "INSERT INTO webhook_events (event_id, subscription_id, event_type, raw_payload) VALUES (?, ?, ?, ?)",
                (event_id, subscription_id, event_type, json.dumps(payload, separators=(',', ':'))),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            logger.info('duplicate webhook event ignored: %s', event_id)
            return

        subscription_payload = (payload.get('payload') or {}).get('subscription') or {}
        subscription_entity = subscription_payload.get('entity') or subscription_payload or {}
        subscription_id = subscription_entity.get('id') if isinstance(subscription_entity, dict) else None
        state = _normalize_razorpay_state(event_type, payload)
        state_event_at = int(payload.get('created_at', 0) or 0)
        if subscription_id:
            _upsert_subscription(conn, subscription_id, state, state_event_at)
    finally:
        conn.close()
