"""
tests/test_integration.py

Integration tests: Orchestrator + StateStore + ClaudeClient wired together.
Discord notify callback is a real AsyncMock; only the Anthropic API is mocked.

結合テスト: Orchestrator + StateStore + ClaudeClient を実際に結線して動作確認。
discord_notify は実際の AsyncMock を使用し、Anthropic API のみモック。
"""

import json
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

# ──────────────────────────────────────────────
# Helpers / ヘルパー
# ──────────────────────────────────────────────

def _make_mock_response(payload: dict) -> MagicMock:
    """Builds a mock Anthropic streaming response from a judgment dict."""
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps(payload)

    message = MagicMock()
    message.content = [block]

    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.get_final_message.return_value = message
    return stream


PAYLOAD_ON_TRACK = {
    "assessment": "on_track",
    "action": "continue",
    "message": "Progress is clear.",
    "summary": None,
    "clarification_needed": False,
}

PAYLOAD_OVERLOADED = {
    "assessment": "overloaded",
    "action": "reduce_tasks",
    "message": "Too many tasks for one session.",
    "summary": None,
    "clarification_needed": False,
}

PAYLOAD_STAGNATING = {
    "assessment": "stagnating",
    "action": "reduce_scope",
    "message": "No progress detected. Focus on one item.",
    "summary": None,
    "clarification_needed": False,
}

PAYLOAD_CLARIFY = {
    "assessment": "on_track",
    "action": "continue",
    "message": "What is the current blocker?",
    "summary": None,
    "clarification_needed": True,
}


# ──────────────────────────────────────────────
# Fixtures / フィクスチャ
# ──────────────────────────────────────────────

@pytest.fixture
def notify() -> AsyncMock:
    """Real AsyncMock acting as the Discord notify callback."""
    return AsyncMock()


@pytest.fixture
def mock_stream_factory():
    """Returns a factory that patches anthropic.Anthropic with a given payload."""
    def factory(payload: dict):
        stream = _make_mock_response(payload)
        patcher = patch("claude_client.anthropic.Anthropic")
        mock_cls = patcher.start()
        mock_cls.return_value.messages.stream.return_value = stream
        return patcher
    return factory


# ──────────────────────────────────────────────
# Full session flow / フルセッションフロー
# ──────────────────────────────────────────────

class TestFullSessionFlow:
    @pytest.mark.asyncio
    async def test_startday_progress_endday(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_ON_TRACK)
        try:
            orch = Orchestrator(discord_notify=notify)

            # /startday
            result = await orch.handle_startday(["タスクA", "タスクB"])
            assert isinstance(result, SupervisorJudgment)
            assert orch._store.state == State.PLANNED
            assert orch._store.tasks == ["タスクA", "タスクB"]

            # /progress
            result = await orch.handle_progress("タスクAの設計完了")
            assert isinstance(result, SupervisorJudgment)
            assert orch._store.state == State.WORKING

            # /endday
            result = await orch.handle_endday()
            assert isinstance(result, SupervisorJudgment)
            assert orch._store.state == State.DONE
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_overloaded_judgment_propagates(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_OVERLOADED)
        try:
            orch = Orchestrator(discord_notify=notify)
            result = await orch.handle_startday(["A", "B", "C", "D", "E", "F", "G", "H"])
            assert result.assessment == "overloaded"
            assert result.action == "reduce_tasks"
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_clarification_needed_propagates(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_CLARIFY)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["タスクA"])
            result = await orch.handle_progress("")
            assert result.clarification_needed is True
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_new_startday_resets_previous_session(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_ON_TRACK)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["旧タスク"])
            orch._store.transition(State.WORKING)

            await orch.handle_startday(["新タスク"])
            assert orch._store.tasks == ["新タスク"]
            assert orch._store.state == State.PLANNED
        finally:
            patcher.stop()


# ──────────────────────────────────────────────
# Discord notify callback integration / Discord通知コールバック結合
# ──────────────────────────────────────────────

class TestDiscordNotifyIntegration:
    @pytest.mark.asyncio
    async def test_discord_reminder_calls_notify(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_ON_TRACK)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["タスクA"])
            orch._store.transition(State.WORKING)
            orch._store.get_minutes_since_last_activity = MagicMock(
                return_value=THRESHOLD_DISCORD_REMINDER
            )

            await orch._check_inactivity()

            notify.assert_called_once()
            payload = json.loads(notify.call_args[0][0])
            assert payload["action"] == "remind"
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_email_alert_calls_notify(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_ON_TRACK)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["タスクA"])
            orch._store.transition(State.WORKING)
            orch._notified.add(THRESHOLD_DISCORD_REMINDER)
            orch._store.get_minutes_since_last_activity = MagicMock(
                return_value=THRESHOLD_EMAIL_ALERT
            )

            await orch._check_inactivity()

            notify.assert_called_once()
            payload = json.loads(notify.call_args[0][0])
            assert payload["action"] == "alert"
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_reduce_scope_calls_notify_with_claude_judgment(
        self, notify, mock_stream_factory
    ):
        patcher = mock_stream_factory(PAYLOAD_STAGNATING)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["タスクA"])
            orch._store.transition(State.WORKING)
            orch._notified.add(THRESHOLD_DISCORD_REMINDER)
            orch._notified.add(THRESHOLD_EMAIL_ALERT)
            orch._store.get_minutes_since_last_activity = MagicMock(
                return_value=THRESHOLD_REDUCE_SCOPE
            )

            await orch._check_inactivity()

            notify.assert_called_once()
            payload = json.loads(notify.call_args[0][0])
            assert payload["assessment"] == "stagnating"
            assert payload["action"] == "reduce_scope"
            assert orch._store.state == State.STAGNATING
        finally:
            patcher.stop()

    @pytest.mark.asyncio
    async def test_progress_after_notify_resets_reminder(self, notify, mock_stream_factory):
        patcher = mock_stream_factory(PAYLOAD_ON_TRACK)
        try:
            orch = Orchestrator(discord_notify=notify)
            await orch.handle_startday(["タスクA"])
            orch._store.transition(State.WORKING)

            # リマインド発火済みにする
            orch._notified.add(THRESHOLD_DISCORD_REMINDER)

            # /progress で解除されることを確認
            await orch.handle_progress("再開しました")
            assert THRESHOLD_DISCORD_REMINDER not in orch._notified
        finally:
            patcher.stop()