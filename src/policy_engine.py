from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.analyst import BaseAnalyst
from src.policy_config import load_policy


@dataclass
class PolicyDecision:
    status: str
    reason: str
    action: str | None = None


class PolicyEngine:
    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy if policy is not None else load_policy()

    def _allowed_hours(self) -> tuple[str, str]:
        contact_rules = self.policy.get('contact_rules', {})
        allowed = contact_rules.get('allowed_hours_local', ['08:00', '19:00'])
        return tuple(str(v) for v in allowed)

    def _now_in_allowed_window(self, now: datetime) -> bool:
        start_hhmm, end_hhmm = self._allowed_hours()
        current = now.strftime('%H:%M')
        return start_hhmm <= current <= end_hhmm

    def decide_from_raw(
        self,
        raw: dict[str, Any],
        analyst: BaseAnalyst,
        *,
        current_case_state: str,
        prior_actions_on_invoice: list[dict[str, Any]],
        now: datetime,
    ) -> PolicyDecision:
        parsed = analyst.validate_raw(raw)
        if parsed is None:
            return PolicyDecision('escalated', 'malformed model output')

        if str(parsed.classification) == 'ambiguous_or_low_confidence':
            return PolicyDecision('escalated', 'ambiguous classification requires escalation', 'escalate_to_human')

        return self.decide(
            recommended_action=parsed.recommended_action,
            classification=parsed.classification,
            confidence=parsed.confidence,
            current_case_state=current_case_state,
            prior_actions_on_invoice=prior_actions_on_invoice,
            now=now,
        )

    def decide(
        self,
        *,
        recommended_action: str,
        classification: str,
        confidence: float,
        current_case_state: str,
        prior_actions_on_invoice: list[dict[str, Any]],
        now: datetime,
    ) -> PolicyDecision:
        action_rules = self.policy.get('action_rules', [])
        contact_rules = self.policy.get('contact_rules', {})
        threshold = None
        matched_rule = None

        for rule in action_rules:
            if rule.get('cause') == classification:
                matched_rule = rule
                threshold = rule.get('confidence_threshold', 0.0)
                break

        if matched_rule is None:
            return PolicyDecision('escalated', 'no policy rule for this classification')

        if threshold is not None and confidence < float(threshold):
            return PolicyDecision('escalated', 'confidence below policy threshold')

        if recommended_action not in {'send_update_payment_nudge', 'schedule_delayed_manual_charge', 'escalate_to_human'}:
            return PolicyDecision('rejected', 'recommended action not in policy surface')

        if recommended_action == 'escalate_to_human':
            return PolicyDecision('allowed', 'escalation chosen by policy', 'escalate_to_human')

        if recommended_action == 'send_update_payment_nudge' and not self._now_in_allowed_window(now):
            return PolicyDecision('rejected', 'outside allowed contact window')

        max_nudges = int(contact_rules.get('max_nudges_per_subscription', 0))
        if recommended_action == 'send_update_payment_nudge' and prior_actions_on_invoice:
            nudges = sum(1 for action in prior_actions_on_invoice if action.get('action_type') == 'send_update_payment_nudge')
            if nudges >= max_nudges:
                return PolicyDecision('rejected', 'nudge cap reached')

        return PolicyDecision('allowed', 'policy approved action', recommended_action)
