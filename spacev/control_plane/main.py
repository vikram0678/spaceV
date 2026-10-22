"""
SpaceV Trusted Control Plane HTTP API (Contract #11).
Implements /health, /api/runs (GET, POST), and fleet orchestration endpoints.
Enforces 400 Bad Request on schema/target/state violations.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from spacev.config import settings
from spacev.control_plane.database import db
from spacev.control_plane.models import RunCreateRequest

logger = logging.getLogger("SpaceV.API")

app = FastAPI(
    title="SpaceV Control Plane & Run Ledger API",
    version="5.0.0",
    description="Trusted control plane for managing Celesto sandboxes and audit runs."
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Contract #11 Requirement:
    'A different execution_target, an unknown state, or a bad sandbox_name returns 400.'
    Standard FastAPI returns 422, so we override to return 400.
    """
    safe_errors = []
    for err in exc.errors():
        safe_errors.append({
            "loc": err.get("loc"),
            "msg": str(err.get("msg")),
            "type": err.get("type")
        })
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Bad Request: Invalid schema, state, or execution_target", "errors": safe_errors}
    )


@app.get("/health", status_code=status.HTTP_200_OK)
def get_health() -> dict[str, str]:
    """Healthcheck endpoint (Contract #1 & #11)."""
    return {"status": "ok"}


@app.get("/api/runs", status_code=status.HTTP_200_OK)
def list_runs() -> list[dict[str, Any]]:
    """Returns list of all runs recorded in the ledger."""
    return db.list_runs()


@app.post("/api/runs", status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreateRequest) -> dict[str, Any]:
    """Records a new sandbox run row into the ledger."""
    row = db.insert_run(
        run_id=payload.run_id,
        sandbox_name=payload.sandbox_name,
        problem_id=payload.problem_id,
        state=payload.state,
        execution_target=payload.execution_target
    )
    return row


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.api_port)
