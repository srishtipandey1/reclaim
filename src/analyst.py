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
    def classify(self, context: Any) -> AnalystClassification | None:
        return AnalystClassification(
            classification=ClassificationEnum.DEAD_OR_EXPIRED_CARD,
            confidence=0.94,
            evidence=['card expired', 'subscription halted after four failed attempts'],
            recommended_action=RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE,
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
