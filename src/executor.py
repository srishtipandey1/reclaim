from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Callable

from src.db import get_connection
from src.policy_config import load_policy


def _load_policy_rule(classification: str) -> dict[str, Any] | None:
    policy = load_policy()
    for rule in policy.get('action_rules', []):
        if rule.get('cause') == classification:
            return rule
    return None


def _serialize_json(value: Any) -> str:
    return json.dumps(value, default=str)


def execute_policy_action(
    *,
    subscription_id: int,
    invoice_id: int,
    decision: Any,
    classification: str,
    confidence: float,
    evidence: list[str],
    expected_case_state: str,
    now: datetime | None = None,
    api_callback: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Execute only a policy-approved action, with CAS guard and audit logging."""
    if decision is None or getattr(decision, 'status', None) != 'allowed':
        return {
            'status': 'aborted',
            'reason': 'policy decision was not approved',
            'action_type': None,
        }

    action_type = getattr(decision, 'action', None)
    if not action_type:
        return {
            'status': 'aborted',
            'reason': 'approved decision missing action type',
            'action_type': None,
        }

    if api_callback is None:
        def _api_callback(payload: dict[str, Any]) -> dict[str, Any]:
            return {'status': 'success', 'simulated': True, 'payload': payload}

        api_callback = _api_callback

    policy = load_policy()
    rule = _load_policy_rule(classification)
    max_attempts = int(rule.get('max_attempts', 0)) if rule else 0
    max_nudges = int(policy.get('contact_rules', {}).get('max_nudges_per_subscription', 0))

    connection = get_connection(db_path)
    try:
        connection.execute('BEGIN IMMEDIATE')

        current = connection.execute(
            'SELECT case_state FROM subscriptions WHERE id = ?',
            (subscription_id,),
        ).fetchone()
        if current is None:
            raise sqlite3.IntegrityError('subscription not found')
        if current['case_state'] != expected_case_state:
            raise sqlite3.IntegrityError('compare-and-swap failed: case_state changed')

        if action_type == 'send_update_payment_nudge':
            nudge_count = connection.execute(
                "SELECT COUNT(*) AS c FROM recovery_actions WHERE subscription_id = ? AND action_type = 'send_update_payment_nudge'",
                (subscription_id,),
            ).fetchone()['c']
            if nudge_count >= max_nudges:
                raise sqlite3.IntegrityError('nudge cap reached')

        existing_attempts = connection.execute(
            'SELECT COUNT(*) AS c FROM recovery_actions WHERE invoice_id = ? AND action_type = ?',
            (invoice_id, action_type),
        ).fetchone()['c']

        if max_attempts and existing_attempts >= max_attempts:
            raise sqlite3.IntegrityError('max_attempts reached for this invoice/action')

        connection.execute(
            """
            INSERT INTO agent_decisions (
                subscription_id,
                invoice_id,
                case_state,
                classification,
                confidence,
                evidence_json,
                policy_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                invoice_id,
                'action_pending',
                classification,
                float(confidence),
                _serialize_json(evidence),
                'approved',
            ),
        )

        updated = connection.execute(
            "UPDATE subscriptions SET case_state = 'action_pending', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND case_state = ?",
            (subscription_id, expected_case_state),
        )
        if updated.rowcount != 1:
            raise sqlite3.IntegrityError('compare-and-swap failed during action pending update')

        payload = {
            'subscription_id': subscription_id,
            'invoice_id': invoice_id,
            'action_type': action_type,
            'classification': classification,
            'confidence': confidence,
            'evidence': evidence,
        }
        api_response = api_callback(payload)

        attempt_number = connection.execute(
            'SELECT COALESCE(MAX(attempt_number), 0) + 1 AS next_attempt FROM recovery_actions WHERE invoice_id = ?',
            (invoice_id,),
        ).fetchone()['next_attempt']

        connection.execute(
            """
            INSERT INTO recovery_actions (
                subscription_id,
                invoice_id,
                action_type,
                attempt_number,
                status,
                request_payload,
                response_payload
            ) VALUES (?, ?, ?, ?, 'executed', ?, ?)
            """,
            (
                subscription_id,
                invoice_id,
                action_type,
                int(attempt_number),
                _serialize_json(payload),
                _serialize_json(api_response),
            ),
        )

        connection.execute(
            """
            INSERT INTO agent_decisions (
                subscription_id,
                invoice_id,
                case_state,
                classification,
                confidence,
                evidence_json,
                policy_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                invoice_id,
                'verified',
                classification,
                float(confidence),
                _serialize_json(evidence),
                'action_executed',
            ),
        )

        connection.execute(
            "UPDATE subscriptions SET case_state = 'verified', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (subscription_id,),
        )
        connection.commit()

        return {
            'status': 'executed',
            'action_type': action_type,
            'api_response': api_response,
            'policy_result': 'approved',
        }
    except Exception as exc:
        connection.rollback()
        exception_text = str(exc)
        if 'compare-and-swap failed' in exception_text or 'concurrent' in exception_text.lower():
            policy_result = 'blocked by concurrent action'
        else:
            policy_result = f'aborted: {exception_text}'

        connection.execute(
            """
            INSERT INTO agent_decisions (
                subscription_id,
                invoice_id,
                case_state,
                classification,
                confidence,
                evidence_json,
                policy_result
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscription_id,
                invoice_id,
                'escalated',
                classification,
                float(confidence),
                _serialize_json(evidence),
                policy_result,
            ),
        )
        connection.commit()
        return {
            'status': 'aborted',
            'reason': policy_result,
            'action_type': action_type,
        }
    finally:
        connection.close()
