"""Runtime startup profiles for the local Vergilius stack.

ShadowBroker is the bootstrap surface: its backend/frontend are started first,
then the operator selects which additional services should join the session.
The module is deliberately Windows-local and only launches fixed, repository-
owned commands.  It never accepts executable paths or arguments from clients.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import urlopen


PROFILE_SHADOWBROKER = "shadowbroker"
PROFILE_LITE = "vergilius-lite"
PROFILE_FULL = "full"
VALID_PROFILES = {PROFILE_SHADOWBROKER, PROFILE_LITE, PROFILE_FULL}

_WORKSPACE = Path(__file__).resolve().parents[3]
_LOG_DIR = _WORKSPACE / "logs"
_LOCK = threading.RLock()
_BOOT_ID = uuid.uuid4().hex
_SELECTED_PROFILE: str | None = None
_SELECTED_AT: float | None = None
_ACTIVATION_THREAD: threading.Thread | None = None
_PROCESS_ERRORS: dict[str, str] = {}


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _wait_port(port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(port):
            return True
        time.sleep(0.25)
    return _port_open(port)


def _spawn_fixed(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    port: int,
    env: dict[str, str] | None = None,
) -> None:
    if _port_open(port):
        return
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _LOG_DIR / f"startup-{name}.log"
    flags = 0
    if os.name == "nt":
        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP. The parent backend stays
        # alive, so a detached console is unnecessary and less predictable.
        flags = 0x08000000 | 0x00000200
    try:
        with log_path.open("ab", buffering=0) as log_handle:
            subprocess.Popen(
                command,
                cwd=str(cwd),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=env,
                creationflags=flags,
                close_fds=True,
            )
    except Exception as exc:
        with _LOCK:
            _PROCESS_ERRORS[name] = f"{type(exc).__name__}: {str(exc)[:180]}"


def _activate_profile(profile: str) -> None:
    if profile == PROFILE_SHADOWBROKER:
        return

    llama_dir = _WORKSPACE / "llama-swap"
    _spawn_fixed(
        "llama-swap",
        [str(llama_dir / "llama-swap.exe"), "--config", str(llama_dir / "config.yaml"),
         "--listen", "127.0.0.1:8012", "--watch-config"],
        cwd=llama_dir,
        port=8012,
    )

    chroma_dir = _WORKSPACE / "chroma-data"
    _spawn_fixed(
        "chromadb",
        [str(_WORKSPACE / "chroma-venv" / "Scripts" / "chroma.exe"), "run",
         "--host", "127.0.0.1", "--port", "8100", "--path", str(chroma_dir)],
        cwd=_WORKSPACE,
        port=8100,
    )

    # Odysseus expects both services during import-time manager setup. Waiting
    # here avoids its fallback/retry path and makes progress deterministic.
    _wait_port(8012, 45)
    _wait_port(8100, 90)

    if profile == PROFILE_FULL:
        voice_scripts = _WORKSPACE / "tts-venv" / "Scripts"
        _spawn_fixed(
            "pockettts",
            [str(voice_scripts / "pocket-tts.exe"), "serve", "--language", "italian",
             "--quantize", "--host", "127.0.0.1", "--port", "8014"],
            cwd=_WORKSPACE,
            port=8014,
        )
        _spawn_fixed(
            "voice-bridge",
            [str(voice_scripts / "python.exe"), str(_WORKSPACE / "voce" / "ponte_voce.py")],
            cwd=_WORKSPACE,
            port=8013,
        )

    odysseus_dir = _WORKSPACE / "odysseus"
    odysseus_env = os.environ.copy()
    odysseus_env["ODYSSEUS_STARTUP_PROFILE"] = profile
    odysseus_env["ODYSSEUS_AVATAR2D_ENABLED"] = "1" if profile == PROFILE_FULL else "0"
    # Lite and Full load their configured RAG/memory/tool/MCP stack during the
    # loader. ShadowBroker never starts Odysseus, so it pays none of this cost.
    odysseus_env["ODYSSEUS_STARTUP_WARMUPS"] = "1"
    _spawn_fixed(
        "odysseus",
        [str(odysseus_dir / "venv" / "Scripts" / "python.exe"), "-m", "uvicorn",
         "app:app", "--host", "127.0.0.1", "--port", "7000"],
        cwd=odysseus_dir,
        port=7000,
        env=odysseus_env,
    )


def select_profile(profile: str) -> dict[str, Any]:
    normalized = str(profile or "").strip().lower()
    # Boot attivo: la scelta va a lui (anche per i profili che questo backend
    # non conosce, come vergilius-chat). Stessa semantica 422/409 del router.
    if _port_open(7001):
        from urllib.request import Request
        req = Request("http://127.0.0.1:7001/api/profile", data=json.dumps({"profile": normalized}).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # HTTPError 409/422 compresi
            codice = getattr(e, "code", None)
            if codice == 422:
                raise ValueError(f"unknown startup profile: {normalized}") from e
            if codice == 409:
                raise RuntimeError("profile already selected for this boot") from e
            raise
    if normalized not in VALID_PROFILES:
        raise ValueError(f"unknown startup profile: {normalized}")

    global _SELECTED_PROFILE, _SELECTED_AT, _ACTIVATION_THREAD
    with _LOCK:
        if _SELECTED_PROFILE and _SELECTED_PROFILE != normalized:
            raise RuntimeError(
                f"profile already selected for this boot: {_SELECTED_PROFILE}"
            )
        if not _SELECTED_PROFILE:
            _SELECTED_PROFILE = normalized
            _SELECTED_AT = time.time()
        if _ACTIVATION_THREAD is None and normalized != PROFILE_SHADOWBROKER:
            _ACTIVATION_THREAD = threading.Thread(
                target=_activate_profile,
                args=(normalized,),
                name=f"startup-profile-{normalized}",
                daemon=True,
            )
            _ACTIVATION_THREAD.start()
    return startup_status()


def _feed_ready(*keys: str) -> bool:
    try:
        from services.fetchers._store import get_source_timestamps_snapshot

        timestamps = get_source_timestamps_snapshot()
        return any(bool(timestamps.get(key)) for key in keys)
    except Exception:
        return False


def _odysseus_profile_ready() -> bool:
    """Check Odysseus' aggregate eager-startup signal without exposing details."""
    if not _port_open(7000):
        return False
    try:
        with urlopen("http://127.0.0.1:7000/api/startup-profile-status", timeout=0.4) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("ready"))
    except Exception:
        return False


def _component(component_id: str, label: str, ready: bool, *, detail: str = "") -> dict[str, Any]:
    error = _PROCESS_ERRORS.get(component_id, "")
    return {
        "id": component_id,
        "label": label,
        "status": "error" if error else ("ready" if ready else "loading"),
        "detail": error or detail,
    }


def _stato_dal_boot() -> dict[str, Any] | None:
    """Vergilius Boot (porta 7001) e' ora la regia dei profili: anche quelli
    senza ShadowBroker (vergilius-chat). Se e' su, il suo stato e' la verita';
    questo backend lo inoltra al gate del frontend senza avviare nulla."""
    if not _port_open(7001):
        return None
    try:
        with urlopen("http://127.0.0.1:7001/api/status", timeout=0.6) as r:
            d = json.loads(r.read().decode("utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def startup_status() -> dict[str, Any]:
    dal_boot = _stato_dal_boot()
    if dal_boot is not None:
        # Nessun profilo scelto nel boot: il gate di :3000 rimanda a :7001.
        if not dal_boot.get("profile"):
            dal_boot["target_url"] = "http://127.0.0.1:7001"
            dal_boot["phase"] = "choose"
        return dal_boot
    with _LOCK:
        profile = _SELECTED_PROFILE
        selected_at = _SELECTED_AT
        process_errors = dict(_PROCESS_ERRORS)

    components: list[dict[str, Any]] = [
        _component("shadowbroker-backend", "ShadowBroker backend", True),
        _component("shadowbroker-frontend", "Interfaccia e mappa", _port_open(3000)),
        _component(
            "fast-intelligence",
            "Voli, navi e SIGINT",
            _feed_ready("commercial_flights", "military_flights", "ships", "sigint"),
        ),
        _component("news-intelligence", "Notizie e intelligence", _feed_ready("news")),
        _component("tinygs", "TinyGS e satelliti radio", _feed_ready("tinygs_satellites")),
        _component("telegram-osint", "Telegram OSINT", _feed_ready("telegram_osint")),
        _component("wastewater", "Biosorveglianza wastewater", _feed_ready("wastewater")),
    ]

    if profile in {PROFILE_LITE, PROFILE_FULL}:
        components.extend(
            [
                _component("llama-swap", "Router modelli", _port_open(8012)),
                _component("chromadb", "Memoria vettoriale e RAG", _port_open(8100)),
                _component("odysseus", "Shell completa Vergilius", _port_open(7000)),
                _component(
                    "odysseus-warmup",
                    "RAG, memoria, modelli e strumenti MCP",
                    _odysseus_profile_ready(),
                ),
            ]
        )
    if profile == PROFILE_FULL:
        components.extend(
            [
                _component("pockettts", "Sintesi vocale", _port_open(8014)),
                _component("voice-bridge", "Voce e trascrizione live", _port_open(8013)),
                _component("avatar2d", "Avatar 2D", _port_open(7000)),
            ]
        )

    ready_count = sum(item["status"] == "ready" for item in components)
    total = len(components)
    ready = bool(profile) and ready_count == total and not process_errors
    progress = round((ready_count / total) * 100) if total else 0
    return {
        "ok": True,
        "boot_id": _BOOT_ID,
        "profile": profile,
        "selected_at": selected_at,
        "phase": "choose" if not profile else ("ready" if ready else "loading"),
        "progress": progress,
        "ready": ready,
        "components": components,
        "target_url": "http://127.0.0.1:3000" if profile == PROFILE_SHADOWBROKER else "http://127.0.0.1:7000",
    }
