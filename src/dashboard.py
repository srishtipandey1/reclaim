from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from src.db import get_connection


def render_dashboard(db_path: str | Path) -> str:
    with get_connection(db_path) as connection:
        subscriptions = connection.execute(
            'SELECT razorpay_subscription_id, razorpay_state, case_state, updated_at FROM subscriptions ORDER BY id'
        ).fetchall()
        decisions = connection.execute(
            'SELECT subscription_id, invoice_id, policy_result, decision_logged_at FROM agent_decisions ORDER BY id DESC'
        ).fetchall()

    rows = ''.join(
        '<tr>'
        f'<td>{html.escape(str(row[0] or ""))}</td>'
        f'<td>{html.escape(str(row[1]))}</td>'
        f'<td>{html.escape(str(row[2]))}</td>'
        f'<td>{html.escape(str(row[3]))}</td>'
        '</tr>'
        for row in subscriptions
    )
    decision_rows = ''.join(
        '<tr>'
        f'<td>{html.escape(str(row[0]))}</td>'
        f'<td>{html.escape(str(row[1] or ""))}</td>'
        f'<td>{html.escape(str(row[2] or ""))}</td>'
        f'<td>{html.escape(str(row[3]))}</td>'
        '</tr>'
        for row in decisions
    )
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Reclaim dashboard</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem}}table{{border-collapse:collapse;width:100%;margin-bottom:2rem}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}</style>
</head><body><h1>Reclaim dashboard</h1><h2>Subscriptions</h2>
<table><tr><th>Subscription</th><th>Razorpay state</th><th>Case state</th><th>Updated</th></tr>{rows}</table>
<h2>Recent decisions</h2><table><tr><th>Subscription ID</th><th>Invoice ID</th><th>Policy result</th><th>Logged</th></tr>{decision_rows}</table>
</body></html>'''


def write_dashboard(db_path: str | Path, output_path: str | Path) -> None:
    Path(output_path).write_text(render_dashboard(db_path), encoding='utf-8')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Render the Reclaim dashboard from SQLite.')
    parser.add_argument('--db', required=True, help='SQLite database path')
    parser.add_argument('--output', required=True, help='HTML output path')
    arguments = parser.parse_args()
    write_dashboard(arguments.db, arguments.output)
