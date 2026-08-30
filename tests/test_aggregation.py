from src.aggregation import RecoveryContext, build_recovery_contexts
from src.db import init_db


def test_unpaid_invoices_are_enumerated_for_halted_subscription(tmp_path):
    db_path = tmp_path / 'recovery_aggregation.db'
    conn = init_db(db_path)

    sub_id = conn.execute(
        "INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, state_event_at, case_state) VALUES (?, 'live_dashboard', 'halted', 1700000002, 'none')",
        ('sub_agg',),
    ).lastrowid

    conn.execute(
        "INSERT INTO webhook_events (event_id, subscription_id, event_type, raw_payload, event_created_at) VALUES (?, ?, ?, ?, ?)",
        (
            'evt-agg-1',
            'sub_agg',
            'subscription.pending',
            '{"payload":{"subscription":{"entity":{"id":"sub_agg","status":"pending"}}}}',
            1700000000,
        ),
    )

    conn.executemany(
        "INSERT INTO invoices (invoice_id, subscription_id, amount, currency, status) VALUES (?, ?, ?, 'INR', ?)",
        [
            ('inv-1', sub_id, 1500, 'issued'),
            ('inv-2', sub_id, 1800, 'attempt_failed'),
            ('inv-3', sub_id, 2000, 'paid'),
            ('inv-4', sub_id, 900, 'issued'),
        ],
    )

    conn.commit()
    conn.close()

    contexts = build_recovery_contexts(db_path, 'sub_agg')
    assert [ctx.invoice_id for ctx in contexts] == ['inv-1', 'inv-2', 'inv-4']
    assert len(contexts) == 3
    assert all(ctx.subscription_id == 'sub_agg' for ctx in contexts)
    assert all(isinstance(ctx, RecoveryContext) for ctx in contexts)
    assert all(ctx.status in {'issued', 'attempt_failed'} for ctx in contexts)
    assert 'contact_rules' in contexts[0].policy_limits
    assert 'action_rules' in contexts[0].policy_limits
    assert 'hard_constraints' in contexts[0].policy_limits


def test_failure_history_orders_by_event_time_not_insertion_order(tmp_path):
    db_path = tmp_path / 'recovery_aggregation_time.db'
    conn = init_db(db_path)

    conn.execute(
        "INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, state_event_at, case_state) VALUES (?, 'live_dashboard', 'halted', 1700000003, 'none')",
        ('sub_timeline',),
    )

    conn.execute(
        "INSERT INTO webhook_events (event_id, subscription_id, event_type, raw_payload, event_created_at) VALUES (?, ?, ?, ?, ?)",
        (
            'evt-late-first',
            'sub_timeline',
            'subscription.pending',
            '{"payload":{"subscription":{"entity":{"id":"sub_timeline","status":"pending"}}}}',
            1700000002,
        ),
    )
    conn.execute(
        "INSERT INTO webhook_events (event_id, subscription_id, event_type, raw_payload, event_created_at) VALUES (?, ?, ?, ?, ?)",
        (
            'evt-early-second',
            'sub_timeline',
            'subscription.activated',
            '{"payload":{"subscription":{"entity":{"id":"sub_timeline","status":"active"}}}}',
            1700000001,
        ),
    )

    conn.execute(
        "INSERT INTO invoices (invoice_id, subscription_id, amount, currency, status) VALUES (?, ?, ?, 'INR', 'issued')",
        ('inv_time_1', 1, 4200),
    )

    conn.commit()
    conn.close()

    contexts = build_recovery_contexts(db_path, 'sub_timeline')
    assert contexts
    ordered_statuses = [entry['entity_status'] for entry in contexts[0].failure_history]
    assert ordered_statuses == ['active', 'pending']
