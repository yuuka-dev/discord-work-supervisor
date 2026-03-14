"""
claude_client.py

Sends session state to Claude and receives a structured supervisor judgment.
セッション状態をClaudeに送り、構造化された判断結果を受け取るモジュール。
Mengirim status sesi ke Claude dan menerima penilaian supervisor yang terstruktur.
"""

import json

import anthropic
from pydantic import BaseModel

# ──────────────────────────────────────────────
# Response schema / レスポンスのスキーマ / Skema respons
# ──────────────────────────────────────────────

class SupervisorJudgment(BaseModel):
    """
    Represents a structured judgment returned by Claude.
    Claudeが返す構造化された判断結果を表すモデル。
    Mewakili penilaian terstruktur yang dikembalikan oleh Claude.

    All fields align with the output spec defined in CLAUDE.md.
    全フィールドはCLAUDE.mdで定義された出力仕様に対応しています。
    Semua field sesuai dengan spesifikasi output yang didefinisikan di CLAUDE.md.
    """
    assessment: str              # e.g. "on_track" | "stagnating" | "overloaded"
    action: str                  # e.g. "continue" | "reduce_scope" | "reduce_tasks"
    message: str                 # Short directive message / 短い指示メッセージ / Pesan arahan singkat
    summary: str | None = None   # Optional condensed summary / 任意の要約 / Ringkasan opsional
    clarification_needed: bool = False  # True if input is ambiguous / 入力が曖昧な場合True / True jika input ambigu


# ──────────────────────────────────────────────
# System prompt / システムプロンプト / System prompt
# ──────────────────────────────────────────────

# This mirrors the CLAUDE.md supervisor role definition.
# CLAUDE.mdのSupervisorロール定義を反映しています。
# Ini mencerminkan definisi peran Supervisor di CLAUDE.md.
SYSTEM_PROMPT = """
You are a Task Supervisor for remote work sessions.

Your only job is to assess the current state of a work session and return a structured JSON judgment.

## Rules

- Output JSON only. No prose, no markdown, no explanation outside JSON.
- Allowed keys: assessment, action, message, summary, clarification_needed
- No emotional encouragement. No praise. No criticism. Neutral and concise only.
- Never invent new assessment or action categories.

## Decision logic

- elapsed_minutes > 90 AND progress is vague or missing:
    assessment = "stagnating", action = "reduce_scope"

- task count exceeds realistic capacity:
    assessment = "overloaded", action = "reduce_tasks"

- progress is clear and recent:
    assessment = "on_track", action = "continue"

- input is insufficient to judge:
    clarification_needed = true, ask ONE short clarification in message

## Output example

{
  "assessment": "stagnating",
  "action": "reduce_scope",
  "message": "Focus only on investigation today.",
  "summary": null,
  "clarification_needed": false
}
""".strip()


# ──────────────────────────────────────────────
# Client / クライアント / Klien
# ──────────────────────────────────────────────

class ClaudeClient:
    """
    Wraps the Anthropic API to request supervisor judgments.
    Anthropic APIをラップして監視判断をリクエストするクラス。
    Membungkus Anthropic API untuk meminta penilaian supervisor.
    """

    def __init__(self) -> None:
        """
        Initializes the Anthropic client using ANTHROPIC_API_KEY from the environment.
        環境変数 ANTHROPIC_API_KEY を使ってAnthropicクライアントを初期化する。
        Menginisialisasi klien Anthropic menggunakan ANTHROPIC_API_KEY dari environment.
        """
        # API key is loaded automatically from ANTHROPIC_API_KEY env var.
        # APIキーは環境変数 ANTHROPIC_API_KEY から自動的に読み込まれます。
        # API key dimuat otomatis dari variabel environment ANTHROPIC_API_KEY.
        self._client = anthropic.Anthropic()

    def judge(self, state_snapshot: dict) -> SupervisorJudgment:
        """
        Sends a state snapshot to Claude and returns a parsed supervisor judgment.
        状態スナップショットをClaudeに送り、解析済みの判断結果を返す。
        Mengirim snapshot status ke Claude dan mengembalikan penilaian supervisor yang diparsing.

        Args:
            state_snapshot (dict): Output of StateStore.to_dict().
                                   StateStore.to_dict() の出力。
                                   Output dari StateStore.to_dict().

        Returns:
            SupervisorJudgment: Parsed and validated judgment.
                                解析・検証済みの判断結果。
                                Penilaian yang telah diparsing dan divalidasi.

        Raises:
            anthropic.APIError: On any API-level failure.
                                APIレベルの障害発生時。
                                Saat terjadi kegagalan di level API.
            ValueError: If the response cannot be parsed as SupervisorJudgment.
                        レスポンスがSupervisorJudgmentとして解析できない場合。
                        Jika respons tidak dapat diparsing sebagai SupervisorJudgment.
        """
        user_message = self._build_user_message(state_snapshot)

        # Use streaming to avoid HTTP timeouts on slow responses.
        # 遅いレスポンスでのHTTPタイムアウトを防ぐためにストリーミングを使用。
        # Gunakan streaming untuk menghindari timeout HTTP pada respons yang lambat.
        with self._client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()

        raw_text = self._extract_text(response)
        return self._parse_response(raw_text)

    # ──────────────────────────────────────────
    # Internal helpers / 内部ヘルパー / Helper internal
    # ──────────────────────────────────────────

    @staticmethod
    def _build_user_message(state_snapshot: dict) -> str:
        """
        Formats the state snapshot as a JSON string for the Claude prompt.
        状態スナップショットをClaudeプロンプト用のJSON文字列にフォーマットする。
        Memformat snapshot status sebagai string JSON untuk prompt Claude.

        Args:
            state_snapshot (dict): Raw state data.
                                   生の状態データ。
                                   Data status mentah.

        Returns:
            str: Formatted prompt string.
                 フォーマットされたプロンプト文字列。
                 String prompt yang diformat.
        """
        serialized = json.dumps(state_snapshot, ensure_ascii=False, indent=2)
        return f"Current session state:\n{serialized}"

    @staticmethod
    def _extract_text(response: anthropic.types.Message) -> str:
        """
        Extracts the plain text content from a Claude API response.
        Claude APIレスポンスからテキストコンテンツを抽出する。
        Mengekstrak konten teks biasa dari respons API Claude.

        Skips thinking blocks; returns the first text block found.
        思考ブロックをスキップし、最初のテキストブロックを返す。
        Melewati blok thinking; mengembalikan blok teks pertama yang ditemukan.

        Args:
            response (anthropic.types.Message): Full API response object.
                                                完全なAPIレスポンスオブジェクト。
                                                Objek respons API lengkap.

        Returns:
            str: Raw text content.
                 生のテキストコンテンツ。
                 Konten teks mentah.

        Raises:
            ValueError: If no text block is found in the response.
                        レスポンスにテキストブロックが見つからない場合。
                        Jika tidak ada blok teks yang ditemukan dalam respons.
        """
        for block in response.content:
            if block.type == "text":
                return block.text
        raise ValueError(
            "No text block in Claude response. "
            "Claudeのレスポンスにテキストブロックがありません。"
            "Tidak ada blok teks dalam respons Claude."
        )

    @staticmethod
    def _parse_response(raw_text: str) -> SupervisorJudgment:
        """
        Parses raw Claude output into a validated SupervisorJudgment.
        Claudeの生出力を検証済みのSupervisorJudgmentに解析する。
        Mengurai output mentah Claude menjadi SupervisorJudgment yang tervalidasi.

        Strips markdown code fences if present before parsing.
        存在する場合はmarkdownのコードフェンスを除去してから解析する。
        Menghapus markdown code fence jika ada sebelum parsing.

        Args:
            raw_text (str): Text output from Claude.
                            Claudeからのテキスト出力。
                            Output teks dari Claude.

        Returns:
            SupervisorJudgment: Validated judgment object.
                                検証済みの判断オブジェクト。
                                Objek penilaian yang tervalidasi.

        Raises:
            ValueError: If JSON is invalid or fields do not match the schema.
                        JSONが無効またはフィールドがスキーマに一致しない場合。
                        Jika JSON tidak valid atau field tidak sesuai dengan skema.
        """
        # Strip markdown fences that Claude may wrap around JSON.
        # ClaudeがJSONを囲むmarkdownフェンスを除去する。
        # Hapus markdown fence yang mungkin membungkus JSON dari Claude.
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Claude returned invalid JSON: {exc}. "
                f"ClaudeのレスポンスがJSONとして解析できません: {exc}。"
                f"Claude mengembalikan JSON yang tidak valid: {exc}."
            ) from exc

        return SupervisorJudgment(**data)
