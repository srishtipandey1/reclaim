from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import PlainTextResponse, Response

from src.db import get_db_path, init_db
from src.webhooks import process_webhook_event, verify_signature

load_dotenv()

logger = logging.getLogger(__name__)
@asynccontextmanager
async def startup(app: FastAPI):
    db_path = get_db_path()
    app.state.db_path = str(db_path)
    init_db(db_path)
    yield


app = FastAPI(title="Razorpay Recovery Agent", lifespan=startup)
app.state.db_path = str(get_db_path())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    event_id = request.headers.get("x-razorpay-event-id")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    if not secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured")
        return PlainTextResponse("webhook secret not configured", status_code=500)

    try:
        verify_signature(raw_body, signature, secret)
    except ValueError:
        logger.warning(
            "invalid signature for event_id=%s raw_body=%s",
            event_id,
            raw_body.decode("utf-8", errors="replace"),
        )
        return PlainTextResponse("invalid signature", status_code=400)

    payload = {}
    try:
        import json

        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("non-JSON payload received for event_id=%s", event_id)
        return PlainTextResponse("invalid payload", status_code=400)

    background_tasks.add_task(process_webhook_event, payload, event_id, app.state.db_path)
    return Response(status_code=200)
