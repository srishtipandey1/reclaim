PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    razorpay_subscription_id TEXT UNIQUE,
    data_source TEXT NOT NULL CHECK (data_source IN ('fixture', 'live_dashboard')),
    razorpay_state TEXT NOT NULL CHECK (
        razorpay_state IN (
            'created',
            'authenticated',
            'active',
            'pending',
            'halted',
            'cancelled',
            'paused',
            'expired',
            'completed'
        )
    ),
    state_event_at INTEGER NOT NULL DEFAULT 0,
    case_state TEXT NOT NULL CHECK (
        case_state IN (
            'none',
            'analyzing',
            'policy_checked',
            'action_pending',
            'verified',
            'resolved',
            'escalated'
        )
    ),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id TEXT UNIQUE NOT NULL,
    subscription_id INTEGER NOT NULL,
    razorpay_invoice_id TEXT,
    amount INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'paid', 'attempt_failed')),
    issue_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_date TEXT,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    subscription_id TEXT,
    event_type TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    event_created_at INTEGER NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    invoice_id INTEGER,
    case_state TEXT NOT NULL CHECK (
        case_state IN ('none', 'analyzing', 'policy_checked', 'action_pending', 'verified', 'resolved', 'escalated')
    ),
    classification TEXT,
    confidence REAL,
    evidence_json TEXT,
    policy_result TEXT,
    decision_logged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS recovery_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    invoice_id INTEGER,
    action_type TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending',
    request_payload TEXT,
    response_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS escalations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    invoice_id INTEGER,
    reason TEXT NOT NULL,
    escalation_context TEXT,
    escalated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TRIGGER IF NOT EXISTS recovery_actions_invoice_cap
BEFORE INSERT ON recovery_actions
WHEN NEW.invoice_id IS NOT NULL
 AND (SELECT COUNT(*) FROM recovery_actions WHERE invoice_id = NEW.invoice_id) >= 3
BEGIN
    SELECT RAISE(ABORT, 'total action cap reached for invoice');
END;

CREATE TRIGGER IF NOT EXISTS recovery_actions_nudge_cap
BEFORE INSERT ON recovery_actions
WHEN NEW.action_type = 'send_update_payment_nudge'
 AND (SELECT COUNT(*) FROM recovery_actions
      WHERE subscription_id = NEW.subscription_id
        AND action_type = 'send_update_payment_nudge') >= 2
BEGIN
    SELECT RAISE(ABORT, 'nudge cap reached for subscription');
END;
