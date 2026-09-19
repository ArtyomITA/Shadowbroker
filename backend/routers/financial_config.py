"""Configurazione runtime del comparto finanziario (preset / deep_news / realtime)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_local_operator
from limiter import limiter
from services.financial_config import get_config, set_config

router = APIRouter()


@router.get("/api/financial/config")
@limiter.limit("30/minute")
async def api_get_financial_config(request: Request) -> dict:  # noqa: ARG001
    return get_config()


@router.post("/api/financial/config", dependencies=[Depends(require_local_operator)])
@limiter.limit("10/minute")
async def api_set_financial_config(request: Request) -> dict:
    """Body = config parziale ({"preset": "broad"} basta); ritorna la config piena."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    try:
        return set_config(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
