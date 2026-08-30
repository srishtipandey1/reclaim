from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ClassificationEnum(str, Enum):
    DEAD_OR_EXPIRED_CARD = "dead_or_expired_card"
    INSUFFICIENT_FUNDS_PATTERN = "insufficient_funds_pattern"
    AMBIGUOUS_OR_LOW_CONFIDENCE = "ambiguous_or_low_confidence"
    ALREADY_RESOLVED = "already_resolved"
    DUPLICATE_OR_REPLAY = "duplicate_or_replay"


class RecommendedActionEnum(str, Enum):
    SEND_UPDATE_PAYMENT_NUDGE = "send_update_payment_nudge"
    SCHEDULE_DELAYED_MANUAL_CHARGE = "schedule_delayed_manual_charge"
    ESCALATE_TO_HUMAN = "escalate_to_human"


class AnalystClassification(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    classification: ClassificationEnum
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str]
    recommended_action: RecommendedActionEnum
