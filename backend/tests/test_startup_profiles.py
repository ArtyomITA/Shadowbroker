from services import startup_profiles as profiles


def test_shadowbroker_profile_requires_all_requested_feeds(monkeypatch):
    monkeypatch.setattr(profiles, "_SELECTED_PROFILE", profiles.PROFILE_SHADOWBROKER)
    monkeypatch.setattr(profiles, "_SELECTED_AT", 1.0)
    monkeypatch.setattr(profiles, "_PROCESS_ERRORS", {})
    monkeypatch.setattr(profiles, "_port_open", lambda port: port == 3000)
    ready_keys = {
        "commercial_flights",
        "news",
        "tinygs_satellites",
        "telegram_osint",
        "wastewater",
    }
    monkeypatch.setattr(
        profiles,
        "_feed_ready",
        lambda *keys: any(key in ready_keys for key in keys),
    )

    status = profiles.startup_status()

    assert status["ready"] is True
    assert status["progress"] == 100
    ids = {item["id"] for item in status["components"]}
    assert {"tinygs", "telegram-osint", "wastewater"} <= ids
    assert "odysseus" not in ids


def test_lite_excludes_voice_and_avatar_but_keeps_vergilius(monkeypatch):
    monkeypatch.setattr(profiles, "_SELECTED_PROFILE", profiles.PROFILE_LITE)
    monkeypatch.setattr(profiles, "_SELECTED_AT", 1.0)
    monkeypatch.setattr(profiles, "_PROCESS_ERRORS", {})
    monkeypatch.setattr(profiles, "_port_open", lambda _port: True)
    monkeypatch.setattr(profiles, "_feed_ready", lambda *_keys: True)
    monkeypatch.setattr(profiles, "_odysseus_profile_ready", lambda: True)

    status = profiles.startup_status()
    ids = {item["id"] for item in status["components"]}

    assert status["ready"] is True
    assert {"llama-swap", "chromadb", "odysseus", "odysseus-warmup"} <= ids
    assert {"pockettts", "voice-bridge", "avatar2d"}.isdisjoint(ids)


def test_full_requires_voice_and_avatar(monkeypatch):
    monkeypatch.setattr(profiles, "_SELECTED_PROFILE", profiles.PROFILE_FULL)
    monkeypatch.setattr(profiles, "_SELECTED_AT", 1.0)
    monkeypatch.setattr(profiles, "_PROCESS_ERRORS", {})
    monkeypatch.setattr(profiles, "_port_open", lambda _port: True)
    monkeypatch.setattr(profiles, "_feed_ready", lambda *_keys: True)
    monkeypatch.setattr(profiles, "_odysseus_profile_ready", lambda: True)

    ids = {item["id"] for item in profiles.startup_status()["components"]}

    assert {"pockettts", "voice-bridge", "avatar2d"} <= ids
