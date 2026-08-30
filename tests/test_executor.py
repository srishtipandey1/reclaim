from __future__ import annotations

import threading

from src.db import get_connection, init_db
from src.executor import execute_policy_action
from src.policy_engine import PolicyDecision


def _seed_invoice(conn, suffix: str) -> tuple[int, int]:
    sub_cursor = conn.execute(
        "INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, case_state) VALUES (?, 'live_dashboard', 'halted', 'analyzing')",
        (f'sub_{suffix}',),
    )
    subscription_id = int(sub_cursor.lastrowid)

    invoice_cursor = conn.execute(
        "INSERT INTO invoices (invoice_id, subscription_id, amount, status) VALUES (?, ?, 1000, 'issued')",
        (f'inv_{suffix}', subscription_id),
    )
    invoice_id = int(invoice_cursor.lastrowid)
    conn.commit()
    return subscription_id, invoice_id


def test_executor_rejects_unapproved_decision(tmp_path) -> None:
    db_path = tmp_path / 'recovery_unapproved.db'
    conn = init_db(db_path)
    subscription_id, invoice_id = _seed_invoice(conn, 'rejected')
    conn.close()

    result = execute_policy_action(
        subscription_id=subscription_id,
        invoice_id=invoice_id,
        decision=PolicyDecision('rejected', 'not allowed'),
        classification='dead_or_expired_card',
        confidence=0.9,
        evidence=['expired card'],
        expected_case_state='analyzing',
        db_path=str(db_path),
    )
    assert result['status'] == 'aborted'


def test_executor_concurrency_does_not_double_execute_same_invoice(tmp_path) -> None:
    db_path = tmp_path / 'recovery_concurrent.db'
    conn = init_db(db_path)
    subscription_id, invoice_id = _seed_invoice(conn, 'concurrent')
    conn.close()

    start = threading.Barrier(2)

    def worker() -> None:
        start.wait()
        return execute_policy_action(
            subscription_id=subscription_id,
            invoice_id=invoice_id,
            decision=PolicyDecision('allowed', 'policy approved action', 'send_update_payment_nudge'),
            classification='dead_or_expired_card',
            confidence=0.95,
            evidence=['expired card'],
            expected_case_state='analyzing',
            db_path=str(db_path),
        )

    results = []
    threads = [threading.Thread(target=lambda: results.append(worker())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    db = get_connection(str(db_path))
    rows = db.execute('SELECT COUNT(*) FROM recovery_actions WHERE invoice_id = ?', (invoice_id,)).fetchone()[0]
    decision_rows = db.execute(
        'SELECT classification, case_state, policy_result FROM agent_decisions WHERE invoice_id = ? ORDER BY id',
        (invoice_id,),
    ).fetchall()
    db.close()
    assert rows == 1
    assert any(row[2] == 'blocked by concurrent action' for row in decision_rows)
