"""Local startup-profile control surface used by the graphical boot gate."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import require_local_operator
from limiter import limiter
from services.startup_profiles import select_profile, startup_status


router = APIRouter()


class StartupProfileSelection(BaseModel):
    profile: str


@router.get("/api/startup/status", dependencies=[Depends(require_local_operator)])
@limiter.limit("180/minute")
async def get_startup_status(request: Request) -> dict[str, Any]:
    return startup_status()


@router.get("/api/startup/feeds", dependencies=[Depends(require_local_operator)])
@limiter.limit("300/minute")
async def get_startup_feeds(request: Request) -> dict[str, Any]:
    """Vergilius: solo la freschezza dei feed, memoria-only, NESSUNA chiamata al
    boot (:7001). Il boot la legge per il suo loader; `/api/startup/status`
    invece inoltra al boot — usarla dal boot creava un ciclo boot↔SB che
    impiccava entrambi."""
    try:
        from services.fetchers._store import get_source_timestamps_snapshot
        ts = get_source_timestamps_snapshot()
    except Exception:
        ts = {}
    return {"ok": True, "fresh": {k: bool(v) for k, v in (ts or {}).items()}}


@router.post("/api/startup/profile", dependencies=[Depends(require_local_operator)])
@limiter.limit("10/minute")
async def choose_startup_profile(
    request: Request,
    body: StartupProfileSelection,
) -> dict[str, Any]:
    try:
        return select_profile(body.profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

