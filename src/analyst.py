from __future__ import annotations

import json
import os
from typing import Any

from groq import Groq
from pydantic import ValidationError

from src.models import AnalystClassification, ClassificationEnum, RecommendedActionEnum


class BaseAnalyst:
    def classify(self, context: Any) -> AnalystClassification | None:
        raise NotImplementedError

    def validate_raw(self, raw: dict[str, Any]) -> AnalystClassification | None:
        if not isinstance(raw, dict):
            return None

        classification = raw.get('classification')
        recommended_action = raw.get('recommended_action')
        if str(classification) == 'ambiguous_or_low_confidence' and str(recommended_action) != 'escalate_to_human':
            return None

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


class GroqAnalyst(BaseAnalyst):
    def __init__(self, api_key: str | None = None, model: str = 'openai/gpt-oss-120b') -> None:
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        self.model = model

    def classify(self, context: Any) -> AnalystClassification | None:
        if not isinstance(context, dict):
            return None

        reason = str(context.get('reason', '')).strip()
        amount = context.get('amount')
        if not reason or amount is None:
            return None

        prompt = (
            'You are a subscription recovery classifier. classify the reason a payment failed for a halted subscription.\n'
            'Return JSON only with these keys: classification, confidence, evidence, recommended_action.\n'
            'classification must be exactly one of: dead_or_expired_card, insufficient_funds_pattern, ambiguous_or_low_confidence, already_resolved, duplicate_or_replay.\n'
            'recommended_action must be exactly one of: send_update_payment_nudge, schedule_delayed_manual_charge, escalate_to_human.\n'
            'confidence must be a number between 0.0 and 1.0 inclusive.\n'
            'evidence must be a list of strings.\n'
            f'reason: {reason}\namount: {amount}\n'
        )

        try:
            client = Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                messages=[{'role': 'user', 'content': prompt}],
                model=self.model,
                temperature=0.0,
                response_format={'type': 'json_object'},
            )
            raw_text = response.choices[0].message.content
            if raw_text is None:
                return None
            payload = raw_text.strip()
            if payload.startswith('```'):
                payload = payload.strip('`')
                if payload.startswith('json'):
                    payload = payload[4:].lstrip()
            parsed = json.loads(payload)
            return self.validate_raw(parsed)
        except Exception as exc:
            print(repr(exc))
            return None


class InvalidSchemaAnalyst(BaseAnalyst):
    def classify(self, context: Any) -> AnalystClassification | None:
        raw = {
            'classification': ClassificationEnum.DEAD_OR_EXPIRED_CARD,
            'confidence': 1.2,
            'evidence': ['bad confidence'],
            'recommended_action': RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE,
        }
        return self.validate_raw(raw)
