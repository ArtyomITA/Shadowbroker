import time

from routers import ai_intel


def _reset_actions():
    with ai_intel._agent_actions_changed:
        ai_intel._agent_actions.clear()
        ai_intel._agent_action_replay.clear()
        ai_intel._agent_action_seq = 0


def test_cursor_clients_receive_the_same_action_without_consuming_it():
    _reset_actions()
    first_cursor = ai_intel.push_agent_action({"action": "fly_to", "lat": 1, "lng": 2})

    actions_a, cursor_a, reset_a = ai_intel.wait_agent_actions(0, 0)
    actions_b, cursor_b, reset_b = ai_intel.wait_agent_actions(0, 0)

    assert first_cursor == 1
    assert [item["seq"] for item in actions_a] == [1]
    assert actions_b == actions_a
    assert cursor_a == cursor_b == 1
    assert reset_a is reset_b is False


def test_legacy_pop_does_not_destroy_cursor_replay():
    _reset_actions()
    ai_intel.push_agent_action({"action": "highlight", "points": []})

    assert len(ai_intel.pop_agent_actions()) == 1
    assert ai_intel.pop_agent_actions() == []
    replay, cursor, _reset = ai_intel.wait_agent_actions(0, 0)

    assert cursor == 1
    assert [item["action"] for item in replay] == ["highlight"]


def test_negative_cursor_starts_at_current_sequence_without_stale_replay():
    _reset_actions()
    ai_intel.push_agent_action({"action": "set_layers", "on": ["ships"]})

    actions, cursor, replay_reset = ai_intel.wait_agent_actions(-1, 0)

    assert actions == []
    assert cursor == 1
    assert replay_reset is False


# Vergilius (focus a vista appena nata)

def test_replay_recent_gives_a_new_view_the_last_command_of_each_kind():
    _reset_actions()
    ai_intel.push_agent_action({"action": "fly_to", "lat": 1, "lng": 2})
    ai_intel.push_agent_action({"action": "set_layers", "on": ["ships"]})
    ai_intel.push_agent_action({"action": "fly_to", "lat": 46.48, "lng": 30.73})
    ai_intel.push_agent_action({"action": "highlight", "points": []})
    # Fuori elenco: non deve tornare.
    ai_intel.push_agent_action({"action": "show_image", "lat": 1, "lng": 2})

    actions, cursor, replay_reset = ai_intel.wait_agent_actions(-1, 0, 90.0)

    assert [item["action"] for item in actions] == ["set_layers", "fly_to", "highlight"]
    assert actions[1]["lat"] == 46.48
    assert cursor == 5
    assert replay_reset is False


def test_replay_recent_ignores_commands_older_than_the_window():
    _reset_actions()
    ai_intel.push_agent_action({"action": "fly_to", "lat": 1, "lng": 2, "ts": time.time() - 600})

    assert ai_intel.wait_agent_actions(-1, 0, 90.0)[0] == []


def test_without_the_parameter_nothing_changes():
    _reset_actions()
    ai_intel.push_agent_action({"action": "fly_to", "lat": 1, "lng": 2})

    assert ai_intel.wait_agent_actions(-1, 0)[0] == []

