"""Administrative diagnostics protected by two independent secrets."""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from psycopg import Error as DatabaseError
from pydantic import BaseModel, Field

import config
import db
import localization_catalogs
from api.billing import admin_auth

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/admin/i18n/status")
async def api_admin_i18n_status(
    x_veksha_admin_secret: Optional[str] = Header(None),
) -> dict[str, Any]:
    await admin_auth(x_veksha_admin_secret)
    return localization_catalogs.catalogue_statuses()


class DatabaseQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20_000)


class DatabaseQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float


async def database_admin_auth(
    x_veksha_admin_secret: Optional[str] = Header(None),
    x_veksha_database_secret: Optional[str] = Header(None),
) -> None:
    await admin_auth(x_veksha_admin_secret)
    if not config.ADMIN_DATABASE_SECRET:
        raise HTTPException(status_code=503, detail="Database console is not configured.")
    if secrets.compare_digest(config.ADMIN_DATABASE_SECRET, config.ADMIN_API_SECRET):
        raise HTTPException(
            status_code=503,
            detail="ADMIN_DATABASE_SECRET must differ from ADMIN_API_SECRET.",
        )
    if not secrets.compare_digest(
        x_veksha_database_secret or "", config.ADMIN_DATABASE_SECRET,
    ):
        raise HTTPException(status_code=401, detail="Invalid database secret.")


@router.post("/api/admin/database/query", response_model=DatabaseQueryResponse)
async def api_admin_database_query(
    req: DatabaseQueryRequest,
    x_veksha_admin_secret: Optional[str] = Header(None),
    x_veksha_database_secret: Optional[str] = Header(None),
) -> DatabaseQueryResponse:
    await database_admin_auth(x_veksha_admin_secret, x_veksha_database_secret)
    started = time.perf_counter()
    try:
        result = db.admin_readonly_query(req.sql)
    except (ValueError, DatabaseError) as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            db.admin_query_audit_record(req.sql, False, 0, duration_ms, str(exc))
        except Exception:
            log.exception("Failed to audit rejected admin database query")
        raise HTTPException(status_code=400, detail=str(exc)[:1000]) from exc
    try:
        db.admin_query_audit_record(
            req.sql, True, result["row_count"], result["duration_ms"],
        )
    except Exception:
        log.exception("Failed to audit successful admin database query")
    return DatabaseQueryResponse(**result)
