"""Configurazione runtime del comparto finanziario.

Tre manopole, cambiabili da API senza riavviare il backend:

  preset     "core" (i 25 simboli di oggi) o "broad" (60, alternati a meta'
             per passata cosi' la spesa resta ~30 chiamate/minuto)
  deep_news  notizie societarie su 30 titoli, finestra 7 giorni
  realtime   quotazioni ogni 30 secondi su un sottoinsieme di 10 simboli

Persistita in data/financial_config.json: caricata all'import, salvata a ogni
set_config. Thread-safe perche' i lettori sono i job dello scheduler e lo
scrittore e' il router HTTP, su thread diversi.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "financial_config.json"
_LOCK = threading.Lock()

_DEFAULTS: dict[str, Any] = {"preset": "core", "deep_news": False, "realtime": False}
_VALID_PRESETS = {"core", "broad"}

_config: dict[str, Any] = dict(_DEFAULTS)


def _validate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Restituisce una config completa e valida, o solleva ValueError."""
    preset = candidate.get("preset", _DEFAULTS["preset"])
    if preset not in _VALID_PRESETS:
        raise ValueError(f"preset must be one of {sorted(_VALID_PRESETS)}")
    deep_news = candidate.get("deep_news", _DEFAULTS["deep_news"])
    realtime = candidate.get("realtime", _DEFAULTS["realtime"])
    if not isinstance(deep_news, bool):
        raise ValueError("deep_news must be a boolean")
    if not isinstance(realtime, bool):
        raise ValueError("realtime must be a boolean")
    return {"preset": preset, "deep_news": deep_news, "realtime": realtime}


def _load() -> None:
    global _config
    try:
        if _CONFIG_FILE.exists():
            raw = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                known = {k: raw[k] for k in _DEFAULTS if k in raw}
                _config = _validate({**_DEFAULTS, **known})
    except Exception as e:
        logger.warning("financial_config illeggibile (%s) — uso i default", e)
        _config = dict(_DEFAULTS)


def get_config() -> dict[str, Any]:
    """Copia della configurazione corrente (mai il dict interno)."""
    with _LOCK:
        return dict(_config)


def set_config(partial: dict[str, Any]) -> dict[str, Any]:
    """Applica un aggiornamento parziale, valida, persiste. Ritorna la config piena."""
    global _config
    if not isinstance(partial, dict):
        raise ValueError("config update must be a JSON object")
    unknown = set(partial) - set(_DEFAULTS)
    if unknown:
        raise ValueError(f"unknown config keys: {sorted(unknown)}")
    with _LOCK:
        validated = _validate({**_config, **partial})
        _config = validated
        try:
            _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_FILE.write_text(
                json.dumps(validated, indent=2) + "\n", encoding="utf-8"
            )
        except Exception as e:
            # La config resta applicata in memoria: il salvataggio fallito
            # costa solo la persistenza al riavvio, non la funzionalita'.
            logger.warning("financial_config non salvata: %s", e)
        return dict(validated)


_load()
