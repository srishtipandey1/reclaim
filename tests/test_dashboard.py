from src.dashboard import render_dashboard
from src.db import init_db


def test_dashboard_renders_database_rows(tmp_path) -> None:
    db_path = tmp_path / 'dashboard.db'
    connection = init_db(db_path)
    connection.execute(
        "INSERT INTO subscriptions (razorpay_subscription_id, data_source, razorpay_state, case_state) VALUES ('sub_1', 'fixture', 'halted', 'analyzing')"
    )
    connection.commit()
    connection.close()

    page = render_dashboard(db_path)

    assert '<h1>Reclaim dashboard</h1>' in page
    assert 'sub_1' in page
    assert 'halted' in page
