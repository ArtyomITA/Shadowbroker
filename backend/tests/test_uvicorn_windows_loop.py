"""Vergilius: il backend su Windows deve girare sul SelectorEventLoop con qualunque uvicorn."""

import asyncio

import pytest
import uvicorn

from services import uvicorn_loop
from services.uvicorn_loop import windows_selector_loop_kwargs


@pytest.fixture(autouse=True)
def _ripristina_policy(monkeypatch):
    impostate = []
    monkeypatch.setattr(uvicorn_loop.asyncio, "set_event_loop_policy", impostate.append)
    monkeypatch.setattr(
        uvicorn_loop.asyncio, "WindowsSelectorEventLoopPolicy", lambda: "selector-policy", raising=False
    )
    return impostate


def test_fuori_da_windows_non_cambia_nulla(_ripristina_policy):
    assert windows_selector_loop_kwargs("0.53.0", os_name="posix") == {}
    assert _ripristina_policy == []


@pytest.mark.parametrize("versione", ["0.34.0", "0.35.1", "0.30.6"])
def test_uvicorn_vecchio_usa_solo_la_policy(versione, _ripristina_policy):
    # Una stringa in `loop` farebbe KeyError su LOOP_SETUPS nelle versioni < 0.36.
    assert windows_selector_loop_kwargs(versione, os_name="nt") == {}
    assert _ripristina_policy == ["selector-policy"]


@pytest.mark.parametrize("versione", ["0.36.0", "0.53.0", "1.0.0", "0.53.0rc1"])
def test_uvicorn_nuovo_riceve_il_loop_esplicito(versione, _ripristina_policy):
    assert windows_selector_loop_kwargs(versione, os_name="nt") == {"loop": "asyncio:SelectorEventLoop"}
    assert _ripristina_policy == ["selector-policy"]


def test_versione_illeggibile_resta_sulla_policy():
    assert windows_selector_loop_kwargs("sconosciuta", os_name="nt") == {}


def test_l_uvicorn_installato_accetta_gli_argomenti():
    """Gli argomenti prodotti per l'uvicorn installato devono dare un SelectorEventLoop."""
    kwargs = windows_selector_loop_kwargs(uvicorn.__version__, os_name="nt")
    config = uvicorn.Config("main:app", **kwargs)
    if hasattr(config, "get_loop_factory"):  # uvicorn >= 0.36
        factory = config.get_loop_factory()
        loop = factory()
        try:
            assert isinstance(loop, asyncio.SelectorEventLoop)
        finally:
            loop.close()
    else:  # uvicorn <= 0.35: la stringa di default resta valida
        assert "loop" not in kwargs
