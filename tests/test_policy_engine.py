from __future__ import annotations

from datetime import datetime, timezone

from src.analyst import FixedAnalyst, InvalidSchemaAnalyst, RuleBasedAnalyst
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


def test_policy_converts_aware_time_to_ist_before_contact_check() -> None:
    engine = PolicyEngine()
    decision = engine.decide(
        recommended_action='send_update_payment_nudge',
        classification='dead_or_expired_card',
        confidence=0.92,
        current_case_state='analyzing',
        prior_actions_on_invoice=[],
        now=datetime(2026, 1, 15, 4, 0, tzinfo=timezone.utc),
    )
    assert decision.status == 'allowed'


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


def test_validate_raw_rejects_ambiguous_with_non_escalate_action() -> None:
    analyst = RuleBasedAnalyst()
    raw_response = {
        'classification': 'ambiguous_or_low_confidence',
        'confidence': 0.45,
        'evidence': ['signals are mixed'],
        'recommended_action': 'send_update_payment_nudge',
    }

    assert analyst.validate_raw(raw_response) is None


def test_stub_analyst_returns_fixed_classification() -> None:
    analyst = FixedAnalyst()
    result = analyst.classify(None)
    assert isinstance(result, AnalystClassification)
    assert result.classification == 'dead_or_expired_card'
    assert result.recommended_action == 'send_update_payment_nudge'


def test_rules_based_analyst_uses_case_evidence() -> None:
    analyst = RuleBasedAnalyst()

    dead_case = analyst.classify({'archetype': 'dead_card', 'reason': 'expired card on active subscription'})
    assert isinstance(dead_case, AnalystClassification)
    assert dead_case.classification == 'dead_or_expired_card'
    assert dead_case.recommended_action == 'send_update_payment_nudge'

    shortfall_case = analyst.classify({'archetype': 'insufficient_funds', 'reason': 'customer underfunded after salary cycle'})
    assert shortfall_case.classification == 'insufficient_funds_pattern'
    assert shortfall_case.recommended_action == 'schedule_delayed_manual_charge'

    ambiguous_case = analyst.classify({'archetype': 'ambiguous', 'reason': 'mixed card and funds signals'})
    assert ambiguous_case.classification == 'ambiguous_or_low_confidence'
    assert ambiguous_case.recommended_action == 'escalate_to_human'
