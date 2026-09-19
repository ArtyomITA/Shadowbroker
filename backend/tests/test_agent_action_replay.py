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

