"""
tests/test_state_store.py

Unit tests for StateStore and State transitions.
StateStoreと状態遷移のユニットテスト。
"""

import pytest
from state_store import InvalidTransitionError, State, StateStore


class TestStateTransitions:
    def test_initial_state_is_idle(self):
        store = StateStore()
        assert store.state == State.IDLE

    def test_idle_to_planned(self):
        store = StateStore()
        store.transition(State.PLANNED)
        assert store.state == State.PLANNED

    def test_planned_to_working(self):
        store = StateStore()
        store.transition(State.PLANNED)
        store.transition(State.WORKING)
        assert store.state == State.WORKING

    def test_working_to_done(self):
        store = StateStore()
        store.transition(State.PLANNED)
        store.transition(State.WORKING)
        store.transition(State.DONE)
        assert store.state == State.DONE

    def test_working_to_stagnating(self):
        store = StateStore()
        store.transition(State.PLANNED)
        store.transition(State.WORKING)
        store.transition(State.STAGNATING)
        assert store.state == State.STAGNATING

    def test_stagnating_to_working(self):
        store = StateStore()
        store.transition(State.PLANNED)
        store.transition(State.WORKING)
        store.transition(State.STAGNATING)
        store.transition(State.WORKING)
        assert store.state == State.WORKING

    def test_invalid_transition_raises(self):
        store = StateStore()
        with pytest.raises(InvalidTransitionError):
            store.transition(State.WORKING)  # IDLE → WORKING は無効

    def test_invalid_transition_planned_to_done(self):
        store = StateStore()
        store.transition(State.PLANNED)
        with pytest.raises(InvalidTransitionError):
            store.transition(State.DONE)  # PLANNED → DONE は無効


class TestStateStoreMethods:
    def test_set_tasks(self):
        store = StateStore()
        store.set_tasks(["タスクA", "タスクB"])
        assert store.tasks == ["タスクA", "タスクB"]

    def test_start_session_sets_timestamps(self):
        store = StateStore()
        store.start_session()
        assert store.session_started_at is not None
        assert store.last_activity_at is not None

    def test_record_activity_updates_timestamp(self):
        store = StateStore()
        store.start_session()
        before = store.last_activity_at
        store.record_activity()
        assert store.last_activity_at >= before

    def test_get_minutes_since_last_activity_none_before_start(self):
        store = StateStore()
        assert store.get_minutes_since_last_activity() is None

    def test_get_minutes_since_last_activity_returns_float(self):
        store = StateStore()
        store.start_session()
        result = store.get_minutes_since_last_activity()
        assert isinstance(result, float)
        assert result >= 0

    def test_reset_restores_defaults(self):
        store = StateStore()
        store.set_tasks(["タスクA"])
        store.start_session()
        store.transition(State.PLANNED)
        store.reset()
        assert store.state == State.IDLE
        assert store.tasks == []
        assert store.last_activity_at is None
        assert store.session_started_at is None

    def test_to_dict_keys(self):
        store = StateStore()
        d = store.to_dict()
        assert set(d.keys()) == {
            "state",
            "tasks",
            "last_activity_at",
            "session_started_at",
            "minutes_since_last_activity",
        }

    def test_to_dict_state_value(self):
        store = StateStore()
        assert store.to_dict()["state"] == "IDLE"
