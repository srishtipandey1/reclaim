import pytest

from src.state_machine import transition_case_state, validate_case_state, validate_razorpay_state


def test_state_validators_accept_schema_states() -> None:
    assert validate_razorpay_state('halted') == 'halted'
    assert validate_case_state('analyzing') == 'analyzing'


def test_state_validators_reject_unknown_states() -> None:
    with pytest.raises(ValueError):
        validate_razorpay_state('unknown')
    with pytest.raises(ValueError):
        validate_case_state('unknown')


def test_case_state_transition_rejects_terminal_reopening() -> None:
    assert transition_case_state('analyzing', 'policy_checked') == 'policy_checked'
    with pytest.raises(ValueError):
        transition_case_state('resolved', 'analyzing')
