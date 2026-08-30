from __future__ import annotations

from datetime import datetime

from src.analyst import FixedAnalyst, InvalidSchemaAnalyst
from src.models import AnalystClassification
from src.policy_engine import PolicyDecision, PolicyEngine


def _now(hours: int, minutes: int = 0) -> datetime:
    return datetime(2026, 1, 15, hours, minutes)


def test_policy_allows_nudge_in_allowed_hours() -> None:
    engine = PolicyEngine()
    decision = engine.decide(
        recommended_action='send_update_payment_nudge',
        classification='dead_or_expired_card',
        confidence=0.92,
        current_case_state='analyzing',
        prior_actions_on_invoice=[],
        now=_now(10, 30),
    )
    assert decision.status == 'allowed'


def test_policy_rejects_nudge_outside_allowed_hours() -> None:
    engine = PolicyEngine()
    decision = engine.decide(
        recommended_action='send_update_payment_nudge',
        classification='dead_or_expired_card',
        confidence=0.92,
        current_case_state='analyzing',
        prior_actions_on_invoice=[],
        now=_now(21, 0),
    )
    assert decision.status == 'rejected'


def test_policy_allows_delayed_manual_charge_when_threshold_met() -> None:
    engine = PolicyEngine()
    decision = engine.decide(
        recommended_action='schedule_delayed_manual_charge',
        classification='insufficient_funds_pattern',
        confidence=0.80,
        current_case_state='policy_checked',
        prior_actions_on_invoice=[],
        now=_now(12, 0),
    )
    assert decision.status == 'allowed'


def test_policy_escalates_on_low_confidence_even_for_valid_action() -> None:
    engine = PolicyEngine()
    decision = engine.decide(
        recommended_action='send_update_payment_nudge',
        classification='dead_or_expired_card',
        confidence=0.60,
        current_case_state='analyzing',
        prior_actions_on_invoice=[],
        now=_now(10, 0),
    )
    assert decision.status == 'escalated'


def test_policy_escalates_for_malformed_response() -> None:
    engine = PolicyEngine()
    raw_response = {
        'classification': 'dead_or_expired_card',
        'confidence': 1.2,
        'evidence': ['bad confidence'],
        'recommended_action': 'send_update_payment_nudge',
    }

    decision = engine.decide_from_raw(
        raw_response,
        InvalidSchemaAnalyst(),
        current_case_state='analyzing',
        prior_actions_on_invoice=[],
        now=_now(10, 30),
    )

    assert decision.status == 'escalated'
    assert decision.reason == 'malformed model output'


def test_stub_analyst_returns_fixed_classification() -> None:
    analyst = FixedAnalyst()
    result = analyst.classify(None)
    assert isinstance(result, AnalystClassification)
    assert result.classification == 'dead_or_expired_card'
    assert result.recommended_action == 'send_update_payment_nudge'
