import hashlib
import hmac
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / 'recovery.db'
    monkeypatch.setenv('RAZORPAY_WEBHOOK_SECRET', 'test-secret')
    monkeypatch.setenv('RAZORPAY_DB_PATH', str(db_path))
    with TestClient(app) as test_client:
        yield test_client


def _signed_request(payload: dict, event_id: str, secret: str, *, bad_signature: bool = False):
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), raw, hashlib.sha256).hexdigest()
    signature = 'bad-signature' if bad_signature else digest
    return raw, {'X-Razorpay-Signature': signature, 'x-razorpay-event-id': event_id}


def test_duplicate_event_is_deduplicated(client):
    payload = {
        'event': 'subscription.pending',
        'payload': {'subscription': {'entity': {'id': 'sub_dup', 'status': 'pending'}}},
        'created_at': 1700000000,
    }

    raw, headers = _signed_request(payload, 'evt-dup-1', 'test-secret')
    first = client.post('/webhooks/razorpay', content=raw, headers=headers)
    assert first.status_code == 200

    second = client.post('/webhooks/razorpay', content=raw, headers=headers)
    assert second.status_code == 200

    with sqlite3.connect(client.app.state.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM webhook_events WHERE event_id = 'evt-dup-1'"
        ).fetchone()[0]
    assert count == 1


def test_late_event_does_not_override_newer_state(client):
    secret = 'test-secret'
    active_payload = {
        'event': 'subscription.activated',
        'payload': {'subscription': {'entity': {'id': 'sub_reversed', 'status': 'active'}}},
        'created_at': 1700000001,
    }
    pending_payload = {
        'event': 'subscription.pending',
        'payload': {'subscription': {'entity': {'id': 'sub_reversed', 'status': 'pending'}}},
        'created_at': 1700000000,
    }

    active_raw, active_headers = _signed_request(active_payload, 'evt-reversed-active', secret)
    pending_raw, pending_headers = _signed_request(pending_payload, 'evt-reversed-pending', secret)

    response_active = client.post('/webhooks/razorpay', content=active_raw, headers=active_headers)
    response_pending = client.post('/webhooks/razorpay', content=pending_raw, headers=pending_headers)
    assert response_active.status_code == 200
    assert response_pending.status_code == 200

    with sqlite3.connect(client.app.state.db_path) as conn:
        state = conn.execute(
            "SELECT razorpay_state FROM subscriptions WHERE razorpay_subscription_id = 'sub_reversed'"
        ).fetchone()
    assert state is not None
    assert state[0] == 'active'


def test_events_in_natural_order_resolve_correctly(client):
    secret = 'test-secret'
    pending_payload = {
        'event': 'subscription.pending',
        'payload': {'subscription': {'entity': {'id': 'sub_natural', 'status': 'pending'}}},
        'created_at': 1700000000,
    }
    active_payload = {
        'event': 'subscription.activated',
        'payload': {'subscription': {'entity': {'id': 'sub_natural', 'status': 'active'}}},
        'created_at': 1700000001,
    }

    pending_raw, pending_headers = _signed_request(pending_payload, 'evt-natural-pending', secret)
    active_raw, active_headers = _signed_request(active_payload, 'evt-natural-active', secret)

    response_pending = client.post('/webhooks/razorpay', content=pending_raw, headers=pending_headers)
    response_active = client.post('/webhooks/razorpay', content=active_raw, headers=active_headers)
    assert response_pending.status_code == 200
    assert response_active.status_code == 200

    with sqlite3.connect(client.app.state.db_path) as conn:
        state = conn.execute(
            "SELECT razorpay_state FROM subscriptions WHERE razorpay_subscription_id = 'sub_natural'"
        ).fetchone()
    assert state is not None
    assert state[0] == 'active'


def test_invalid_signature_is_rejected_and_raw_body_logged(client, caplog):
    payload = {
        'event': 'subscription.halted',
        'payload': {'subscription': {'entity': {'id': 'sub_bad_sig', 'status': 'halted'}}},
        'created_at': 1700000002,
    }
    raw, headers = _signed_request(payload, 'evt-bad-1', 'test-secret', bad_signature=True)
    response = client.post('/webhooks/razorpay', content=raw, headers=headers)
    assert response.status_code == 400
    assert 'invalid signature' in response.text.lower()
    assert 'sub_bad_sig' in caplog.text
