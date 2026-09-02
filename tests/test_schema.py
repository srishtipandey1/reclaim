import sqlite3

import pytest

from src.db import init_db


def test_required_tables_exist() -> None:
    conn = init_db(':memory:')
    required = {
        'subscriptions',
        'invoices',
        'webhook_events',
        'agent_decisions',
        'recovery_actions',
        'escalations',
    }
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert required.issubset(existing)


def test_schema_enforces_state_constraints() -> None:
    conn = init_db(':memory:')

    expected_tables = {
        'subscriptions',
        'invoices',
        'webhook_events',
        'agent_decisions',
        'recovery_actions',
        'escalations',
    }
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual_tables = {row[0] for row in tables}
    assert expected_tables.issubset(actual_tables)

    insert_invalid = """
        INSERT INTO subscriptions (
            razorpay_subscription_id,
            data_source,
            razorpay_state,
            case_state
        ) VALUES ('sub_invalid', 'fixture', 'bad_state', 'none')
    """

    try:
        conn.execute(insert_invalid)
        conn.commit()
        assert False, "Expected invalid razorpay_state to be rejected"
    except sqlite3.IntegrityError:
        pass

    insert_invalid_case = """
        INSERT INTO subscriptions (
            razorpay_subscription_id,
            data_source,
            razorpay_state,
            case_state
        ) VALUES ('sub_invalid_case', 'fixture', 'active', 'not_a_real_state')
    """

    try:
        conn.execute(insert_invalid_case)
        conn.commit()
        assert False, "Expected invalid case_state to be rejected"
    except sqlite3.IntegrityError:
        pass

    valid = """
        INSERT INTO subscriptions (
            razorpay_subscription_id,
            data_source,
            razorpay_state,
            case_state
        ) VALUES ('sub_valid', 'live_dashboard', 'halted', 'analyzing')
    """
    conn.execute(valid)
    conn.commit()

    row = conn.execute(
        "SELECT razorpay_state, case_state, data_source FROM subscriptions WHERE razorpay_subscription_id = 'sub_valid'"
    ).fetchone()
    assert row is not None
    assert row[0] == 'halted'
    assert row[1] == 'analyzing'
    assert row[2] == 'live_dashboard'


def test_schema_enforces_action_caps() -> None:
    conn = init_db(':memory:')
    subscription = conn.execute(
        "INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, case_state) VALUES ('sub_caps', 'fixture', 'halted', 'analyzing')"
    )
    subscription_id = subscription.lastrowid
    invoice = conn.execute(
        "INSERT INTO invoices (invoice_id, subscription_id, amount) VALUES ('inv_caps', ?, 1000)",
        (subscription_id,),
    )
    invoice_id = invoice.lastrowid
    for action_type in ('first', 'second', 'third'):
        conn.execute(
            'INSERT INTO recovery_actions (subscription_id, invoice_id, action_type) VALUES (?, ?, ?)',
            (subscription_id, invoice_id, action_type),
        )
    with pytest.raises(sqlite3.IntegrityError, match='total action cap'):
        conn.execute(
            "INSERT INTO recovery_actions (subscription_id, invoice_id, action_type) VALUES (?, ?, 'fourth')",
            (subscription_id, invoice_id),
        )
