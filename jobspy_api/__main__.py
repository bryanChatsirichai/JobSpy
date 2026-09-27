"""Run the API: ``uv run python -m jobspy_api`` (host/port from ``.env``)."""

from __future__ import annotations

import uvicorn

from jobspy_api import config

if __name__ == "__main__":
    uvicorn.run(
        "jobspy_api.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
    )
