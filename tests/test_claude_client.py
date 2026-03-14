"""
tests/test_claude_client.py

Unit tests for ClaudeClient (Anthropic API mocked).
ClaudeClientのユニットテスト（Anthropic APIはモック）。
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from claude_client import ClaudeClient, SupervisorJudgment
from pydantic import ValidationError

VALID_JUDGMENT = {
    "assessment": "on_track",
    "action": "continue",
    "message": "Progress is clear.",
    "summary": None,
    "clarification_needed": False,
}


def _make_mock_response(text: str) -> MagicMock:
    """Builds a mock anthropic.types.Message with a single text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    response = MagicMock()
    response.content = [block]
    return response


class TestParseResponse:
    def test_valid_json(self):
        result = ClaudeClient._parse_response(json.dumps(VALID_JUDGMENT))
        assert isinstance(result, SupervisorJudgment)
        assert result.assessment == "on_track"

    def test_strips_markdown_fences(self):
        wrapped = f"```json\n{json.dumps(VALID_JUDGMENT)}\n```"
        result = ClaudeClient._parse_response(wrapped)
        assert result.action == "continue"

    def test_invalid_json_raises(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            ClaudeClient._parse_response("not json")

    def test_missing_field_raises(self):
        bad = {"assessment": "on_track"}  # action, message が欠落
        with pytest.raises(ValidationError):
            ClaudeClient._parse_response(json.dumps(bad))


class TestExtractText:
    def test_returns_text_block(self):
        response = _make_mock_response("hello")
        assert ClaudeClient._extract_text(response) == "hello"

    def test_skips_thinking_block(self):
        thinking = MagicMock()
        thinking.type = "thinking"

        text = MagicMock()
        text.type = "text"
        text.text = "result"

        response = MagicMock()
        response.content = [thinking, text]
        assert ClaudeClient._extract_text(response) == "result"

    def test_no_text_block_raises(self):
        thinking = MagicMock()
        thinking.type = "thinking"
        response = MagicMock()
        response.content = [thinking]
        with pytest.raises(ValueError, match="No text block"):
            ClaudeClient._extract_text(response)


class TestJudge:
    def test_judge_returns_judgment(self):
        mock_response = _make_mock_response(json.dumps(VALID_JUDGMENT))

        mock_stream = MagicMock()
        mock_stream.__enter__ = MagicMock(return_value=mock_stream)
        mock_stream.__exit__ = MagicMock(return_value=False)
        mock_stream.get_final_message.return_value = mock_response

        with patch("claude_client.anthropic.Anthropic") as mock_anthropic:
            mock_anthropic.return_value.messages.stream.return_value = mock_stream
            client = ClaudeClient()
            result = client.judge({"state": "WORKING", "tasks": ["タスクA"]})

        assert isinstance(result, SupervisorJudgment)
        assert result.assessment == "on_track"
