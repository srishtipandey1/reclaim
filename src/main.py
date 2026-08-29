from __future__ import annotations

from fastapi import FastAPI

from src.db import init_db

app = FastAPI(title="Razorpay Recovery Agent")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
