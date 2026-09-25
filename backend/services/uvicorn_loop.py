"""Vergilius: tiene il SelectorEventLoop su Windows con qualunque uvicorn.

Senza reload uvicorn su Windows usa il ProactorEventLoop, che su Python 3.12
CHIUDE il socket in ascolto al primo "Accept failed ... WinError 64" (un client
che si stacca prima dell'accept, es. una sonda di porta mentre il ciclo e'
occupato): il processo resta vivo ma la 8000 non risponde piu'. Visto il
20 set 2026.

Fino a uvicorn 0.35 bastava impostare la policy del loop prima di
`uvicorn.run`. Dalla 0.36 uvicorn crea il loop con una sua factory
(`asyncio_loop_factory`: Proactor su win32 senza subprocess) e la policy viene
ignorata: serve dirgli il loop con `loop="asyncio:SelectorEventLoop"`. Quella
stringa pero' fa fallire le versioni vecchie (KeyError su LOOP_SETUPS), e il
venv puo' avere ancora la 0.34 se e' stato installato da uv.lock: per questo si
decide in base alla versione installata.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any

# Prima versione di uvicorn con `loop` che accetta una factory come stringa di import.
_LOOP_FACTORY_SINCE = (0, 36)


def _uvicorn_version_tuple(version: str) -> tuple[int, int]:
    parti = re.findall(r"\d+", version or "")
    if len(parti) < 2:
        return (0, 0)
    return (int(parti[0]), int(parti[1]))


def windows_selector_loop_kwargs(uvicorn_version: str, os_name: str | None = None) -> dict[str, Any]:
    """Argomenti extra per `uvicorn.run` che impongono il Selector su Windows.

    Fuori da Windows non cambia nulla. Su Windows imposta anche la policy, che
    e' quella che conta per uvicorn fino alla 0.35.
    """
    if (os_name or os.name) != "nt":
        return {}
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if _uvicorn_version_tuple(uvicorn_version) >= _LOOP_FACTORY_SINCE:
        return {"loop": "asyncio:SelectorEventLoop"}
    return {}
