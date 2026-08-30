from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.db import get_connection
from src.policy_config import load_policy
from src.webhooks import get_subscription_entity

UNPAID_INVOICE_STATUSES = ('issued', 'attempt_failed')


@dataclass
class RecoveryContext:
    subscription_id: str
    invoice_id: str
    amount: int
    currency: str
    status: str
    payment_history: list[dict[str, Any]] = field(default_factory=list)
    failure_history: list[dict[str, Any]] = field(default_factory=list)
    prior_recovery_actions: list[dict[str, Any]] = field(default_factory=list)
    policy_limits: dict[str, Any] = field(default_factory=dict)


def _read_event_history(conn, subscription_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_type, raw_payload, event_created_at
        FROM webhook_events
        WHERE subscription_id = ?
        ORDER BY event_created_at ASC
        """,
        (subscription_id,),
    ).fetchall()

    history: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row['raw_payload']) if isinstance(row['raw_payload'], str) else row['raw_payload']
        entity = get_subscription_entity(payload)
        history.append(
            {
                'event_type': row['event_type'],
                'entity_status': entity.get('status'),
                'event_created_at': row['event_created_at'],
            }
        )
    return history


def _read_prior_actions(conn, subscription_id: str) -> list[dict[str, Any]]:
    subscription_row = conn.execute(
        "SELECT id FROM subscriptions WHERE razorpay_subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    if not subscription_row:
        return []

    rows = conn.execute(
        """
        SELECT action_type, attempt_number, status, created_at, response_payload
        FROM recovery_actions
        WHERE subscription_id = ?
        ORDER BY created_at ASC
        """,
        (subscription_row['id'],),
    ).fetchall()
    return [dict(row) for row in rows]


def build_recovery_contexts(db_path: str, razorpay_subscription_id: str) -> list[RecoveryContext]:
    with get_connection(db_path) as conn:
        subscription_row = conn.execute(
            "SELECT id FROM subscriptions WHERE razorpay_subscription_id = ?",
            (razorpay_subscription_id,),
        ).fetchone()
        if subscription_row is None:
            return []

        invoice_rows = conn.execute(
            """
            SELECT id, invoice_id, amount, currency, status
            FROM invoices
            WHERE subscription_id = ? AND status IN ('issued', 'attempt_failed')
            ORDER BY issue_date ASC
            """,
            (subscription_row['id'],),
        ).fetchall()

        failure_history = _read_event_history(conn, razorpay_subscription_id)
        prior_actions = _read_prior_actions(conn, razorpay_subscription_id)
        policy_limits = load_policy()

        contexts: list[RecoveryContext] = []
        for row in invoice_rows:
            contexts.append(
                RecoveryContext(
                    subscription_id=razorpay_subscription_id,
                    invoice_id=row['invoice_id'],
                    amount=row['amount'],
                    currency=row['currency'],
                    status=row['status'],
                    payment_history=[],
                    failure_history=failure_history,
                    prior_recovery_actions=prior_actions,
                    policy_limits=policy_limits,
                )
            )

        return contexts
