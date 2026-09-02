from __future__ import annotations

from typing import Final

RAZORPAY_STATES: Final[frozenset[str]] = frozenset({
    'created',
    'authenticated',
    'active',
    'pending',
    'halted',
    'cancelled',
    'paused',
    'expired',
    'completed',
})
CASE_STATES: Final[frozenset[str]] = frozenset({
    'none',
    'analyzing',
    'policy_checked',
    'action_pending',
    'verified',
    'resolved',
    'escalated',
})


def validate_razorpay_state(state: str) -> str:
    if state not in RAZORPAY_STATES:
        raise ValueError(f'invalid Razorpay state: {state}')
    return state


def validate_case_state(state: str) -> str:
    if state not in CASE_STATES:
        raise ValueError(f'invalid case state: {state}')
    return state


def transition_case_state(current: str, target: str) -> str:
    validate_case_state(current)
    validate_case_state(target)
    if current == target:
        return target
    allowed = {
        'none': {'analyzing', 'escalated'},
        'analyzing': {'policy_checked', 'escalated'},
        'policy_checked': {'action_pending', 'escalated'},
        'action_pending': {'verified', 'escalated'},
        'verified': {'resolved', 'escalated'},
        'resolved': set(),
        'escalated': set(),
    }
    if target not in allowed[current]:
        raise ValueError(f'invalid case transition: {current} -> {target}')
    return target
