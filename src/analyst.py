from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.models import AnalystClassification, ClassificationEnum, RecommendedActionEnum


class BaseAnalyst:
    def classify(self, context: Any) -> AnalystClassification | None:
        raise NotImplementedError

    def validate_raw(self, raw: dict[str, Any]) -> AnalystClassification | None:
        try:
            return AnalystClassification.model_validate(raw)
        except ValidationError:
            return None


class FixedAnalyst(BaseAnalyst):
    """Prompt 4 stub only: used for plumbing tests and validation, not for eval metrics."""

    def classify(self, context: Any) -> AnalystClassification | None:
        return AnalystClassification(
            classification=ClassificationEnum.DEAD_OR_EXPIRED_CARD,
            confidence=0.94,
            evidence=['card expired', 'subscription halted after four failed attempts'],
            recommended_action=RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE,
        )


class RuleBasedAnalyst(BaseAnalyst):
    """Placeholder model until a live LLM call is wired in. It reads the case evidence fields and
    produces different outputs based on the actual signal in the input, rather than returning the
    same answer for every case.
    """

    def classify(self, context: Any) -> AnalystClassification | None:
        if context is None:
            return None

        normalised = ' '.join(
            str(value)
            for value in [
                context.get('archetype'),
                context.get('failure_pattern'),
                context.get('reason'),
                context.get('case_summary'),
                context.get('notes'),
            ]
            if value is not None
        ).lower()

        archetype = str(context.get('archetype', '')).lower()
        reason = str(context.get('reason', '')).lower()

        if archetype == 'dead_card' or 'expired' in normalised or 'dead card' in normalised or 'card invalid' in normalised:
            evidence = [
                'Card or payment method appears expired or invalid.',
                'The subscription reached halted after failed retries.',
            ]
            return AnalystClassification(
                classification=ClassificationEnum.DEAD_OR_EXPIRED_CARD,
                confidence=0.90,
                evidence=evidence,
                recommended_action=RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE,
            )

        if archetype == 'insufficient_funds' or 'insufficient' in normalised or 'shortfall' in normalised or 'low balance' in normalised:
            evidence = [
                'The failure pattern matches temporary insufficient funds.',
                'Customer appears to have a recoverable balance issue rather than a card failure.',
            ]
            return AnalystClassification(
                classification=ClassificationEnum.INSUFFICIENT_FUNDS_PATTERN,
                confidence=0.78,
                evidence=evidence,
                recommended_action=RecommendedActionEnum.SCHEDULE_DELAYED_MANUAL_CHARGE,
            )

        evidence = [
            'Signals are mixed across card validity and funds availability.',
            'No single clear failure mode is supported by the case evidence.',
        ]
        return AnalystClassification(
            classification=ClassificationEnum.AMBIGUOUS_OR_LOW_CONFIDENCE,
            confidence=0.55,
            evidence=evidence,
            recommended_action=RecommendedActionEnum.ESCALATE_TO_HUMAN,
        )


class InvalidSchemaAnalyst(BaseAnalyst):
    def classify(self, context: Any) -> AnalystClassification | None:
        raw = {
            'classification': ClassificationEnum.DEAD_OR_EXPIRED_CARD,
            'confidence': 1.2,
            'evidence': ['bad confidence'],
            'recommended_action': RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE,
        }
        return self.validate_raw(raw)
