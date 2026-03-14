"""
tests/test_orchestrator.py

Unit tests for Orchestrator (ClaudeClient and discord_notify mocked).
Orchestratorのユニットテスト（ClaudeClientとdiscord_notifyはモック）。
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_client import SupervisorJudgment
from orchestrator import (
    THRESHOLD_DISCORD_REMINDER,
    THRESHOLD_EMAIL_ALERT,
    THRESHOLD_REDUCE_SCOPE,
    Orchestrator,
)
from state_store import State

JUDGMENT_ON_TRACK = SupervisorJudgment(
    assessment="on_track",
    action="continue",
    message="Keep going.",
    clarification_needed=False,
)

JUDGMENT_STAGNATING = SupervisorJudgment(
    assessment="stagnating",
    action="reduce_scope",
    message="Focus only on investigation.",
    clarification_needed=False,
)


def _make_orchestrator(judgment: SupervisorJudgment = JUDGMENT_ON_TRACK) -> Orchestrator:
    """Returns an Orchestrator with mocked ClaudeClient and discord_notify."""
    notify = AsyncMock()
    with patch("orchestrator.ClaudeClient") as mock_claude:
        mock_claude.return_value.judge.return_value = judgment
        orch = Orchestrator(discord_notify=notify)
    orch._claude.judge.return_value = judgment
    orch._discord_notify = notify
    return orch


class TestHandleStartday:
    @pytest.mark.asyncio
    async def test_returns_judgment(self):
        orch = _make_orchestrator()
        result = await orch.handle_startday(["タスクA", "タスクB"])
        assert isinstance(result, SupervisorJudgment)

    @pytest.mark.asyncio
    async def test_state_is_planned(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        assert orch._store.state == State.PLANNED

    @pytest.mark.asyncio
    async def test_tasks_are_stored(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA", "タスクB"])
        assert orch._store.tasks == ["タスクA", "タスクB"]

    @pytest.mark.asyncio
    async def test_notified_is_cleared(self):
        orch = _make_orchestrator()
        orch._notified.add(60)
        await orch.handle_startday(["タスクA"])
        assert len(orch._notified) == 0


class TestHandleProgress:
    @pytest.mark.asyncio
    async def test_transitions_planned_to_working(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        await orch.handle_progress("設計完了")
        assert orch._store.state == State.WORKING

    @pytest.mark.asyncio
    async def test_recovers_from_stagnating(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        orch._store.transition(State.STAGNATING)
        await orch.handle_progress("再開しました")
        assert orch._store.state == State.WORKING

    @pytest.mark.asyncio
    async def test_returns_judgment(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        result = await orch.handle_progress("設計完了")
        assert isinstance(result, SupervisorJudgment)


class TestHandleEndday:
    @pytest.mark.asyncio
    async def test_state_is_done(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        await orch.handle_endday()
        assert orch._store.state == State.DONE

    @pytest.mark.asyncio
    async def test_returns_judgment(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        result = await orch.handle_endday()
        assert isinstance(result, SupervisorJudgment)

    @pytest.mark.asyncio
    async def test_already_done_does_not_raise(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        await orch.handle_endday()
        await orch.handle_endday()  # 2回目も例外なし


class TestInactivityCheck:
    @pytest.mark.asyncio
    async def test_discord_reminder_fires_at_threshold(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)

        orch._store.get_minutes_since_last_activity = MagicMock(
            return_value=THRESHOLD_DISCORD_REMINDER
        )
        await orch._check_inactivity()

        orch._discord_notify.assert_called_once()
        assert THRESHOLD_DISCORD_REMINDER in orch._notified

    @pytest.mark.asyncio
    async def test_email_alert_fires_at_threshold(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        orch._notified.add(THRESHOLD_DISCORD_REMINDER)

        orch._store.get_minutes_since_last_activity = MagicMock(
            return_value=THRESHOLD_EMAIL_ALERT
        )
        await orch._check_inactivity()

        orch._discord_notify.assert_called_once()
        assert THRESHOLD_EMAIL_ALERT in orch._notified

    @pytest.mark.asyncio
    async def test_reduce_scope_fires_at_threshold(self):
        orch = _make_orchestrator(JUDGMENT_STAGNATING)
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        orch._notified.add(THRESHOLD_DISCORD_REMINDER)
        orch._notified.add(THRESHOLD_EMAIL_ALERT)

        orch._store.get_minutes_since_last_activity = MagicMock(
            return_value=THRESHOLD_REDUCE_SCOPE
        )
        await orch._check_inactivity()

        assert orch._store.state == State.STAGNATING
        assert THRESHOLD_REDUCE_SCOPE in orch._notified

    @pytest.mark.asyncio
    async def test_does_not_fire_when_idle(self):
        orch = _make_orchestrator()
        orch._store.get_minutes_since_last_activity = MagicMock(return_value=200)
        await orch._check_inactivity()
        orch._discord_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_fire_twice(self):
        orch = _make_orchestrator()
        await orch.handle_startday(["タスクA"])
        orch._store.transition(State.WORKING)
        orch._notified.add(THRESHOLD_DISCORD_REMINDER)

        orch._store.get_minutes_since_last_activity = MagicMock(
            return_value=THRESHOLD_DISCORD_REMINDER
        )
        await orch._check_inactivity()
        orch._discord_notify.assert_not_called()