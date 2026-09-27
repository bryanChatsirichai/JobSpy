"""JobSpy FastAPI sidecar — run with ``uv run uvicorn jobspy_api.main:app --port 8001``."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobspy_api.routes import jobs

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

app = FastAPI(title="JobSpy API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/v1")
app.include_router(jobs.router)
