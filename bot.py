"""
bot.py

Discord Bot — UI layer only. Receives slash commands and displays Claude judgments.
Discord Bot — UIレイヤーのみ。スラッシュコマンドを受け取りClaudeの判断を表示する。
Discord Bot — Hanya lapisan UI. Menerima perintah slash dan menampilkan penilaian Claude.
"""

import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from orchestrator import EmailConfig, Orchestrator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Bot setup / Bot設定 / Pengaturan Bot
# ──────────────────────────────────────────────

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Active notification channel (set on first /startday call)
# アクティブな通知チャンネル（最初の/startday呼び出し時に設定）
# Saluran notifikasi aktif (diatur saat panggilan /startday pertama)
_notify_channel: discord.TextChannel | None = None


async def _discord_notify(message: str) -> None:
    """
    Callback passed to Orchestrator for inactivity notifications.
    無反応通知のためにOrchestratorに渡すコールバック。
    Callback yang diteruskan ke Orchestrator untuk notifikasi ketidakaktifan.

    Args:
        message (str): Raw JSON string to display in Discord.
                       Discordに表示する生のJSON文字列。
                       String JSON mentah untuk ditampilkan di Discord.
    """
    if _notify_channel is None:
        logger.warning("No notify channel set / 通知チャンネル未設定 / Saluran notifikasi belum diatur")
        return
    await _notify_channel.send(_format_judgment(message))


# Build EmailConfig from .env (optional — skipped if vars are missing)
# .envからEmailConfigを構築する（任意 — 変数がない場合はスキップ）
# Bangun EmailConfig dari .env (opsional — dilewati jika variabel tidak ada)
def _build_email_config() -> EmailConfig | None:
    """
    Reads SMTP settings from environment variables.
    環境変数からSMTP設定を読み込む。
    Membaca pengaturan SMTP dari variabel environment.

    Returns:
        EmailConfig | None: Config if all required vars are set, else None.
                            必要な変数が全て設定されていればConfig、なければNone。
                            Config jika semua variabel yang diperlukan diatur, jika tidak None.
    """
    required = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "ALERT_SENDER", "ALERT_RECIPIENT")
    if not all(os.getenv(k) for k in required):
        logger.info("Email not configured — skipping / メール未設定 — スキップ / Email tidak dikonfigurasi — dilewati")
        return None
    return EmailConfig(
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ["SMTP_PORT"]),
        username=os.environ["SMTP_USER"],
        password=os.environ["SMTP_PASS"],
        sender=os.environ["ALERT_SENDER"],
        recipient=os.environ["ALERT_RECIPIENT"],
    )


orchestrator = Orchestrator(
    discord_notify=_discord_notify,
    email_config=_build_email_config(),
)


# ──────────────────────────────────────────────
# Formatting / フォーマット / Format
# ──────────────────────────────────────────────

def _format_judgment(raw: str) -> str:
    """
    Pretty-prints a JSON judgment string for display in Discord.
    Discord表示用にJSON判断文字列を整形する。
    Mencetak indentasi string penilaian JSON untuk ditampilkan di Discord.

    Args:
        raw (str): Raw JSON string (from SupervisorJudgment.model_dump_json()).
                   生のJSON文字列。
                   String JSON mentah.

    Returns:
        str: Discord message with a fenced JSON code block.
             コードブロック付きのDiscordメッセージ。
             Pesan Discord dengan blok kode JSON berpagar.
    """
    try:
        pretty = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, ValueError):
        pretty = raw
    return f"```json\n{pretty}\n```"


# ──────────────────────────────────────────────
# Bot events / Botイベント / Event Bot
# ──────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    """
    Called when the bot connects to Discord. Starts the orchestrator loop and syncs commands.
    BotがDiscordに接続した際に呼ばれる。オーケストレーターループを開始しコマンドを同期する。
    Dipanggil saat bot terhubung ke Discord. Memulai loop orchestrator dan menyinkronkan perintah.
    """
    await orchestrator.start()
    await bot.tree.sync()
    logger.info("Bot ready / Bot起動完了 / Bot siap: %s", bot.user)


# ──────────────────────────────────────────────
# Slash commands / スラッシュコマンド / Perintah slash
# ──────────────────────────────────────────────

@bot.tree.command(name="startday", description="Start your work session with today's tasks.")
@app_commands.describe(tasks="Comma-separated list of tasks / タスクをカンマ区切りで / Daftar tugas dipisah koma")
async def startday(interaction: discord.Interaction, tasks: str) -> None:
    """
    /startday — Registers tasks and starts the supervision session.
    /startday — タスクを登録し、監視セッションを開始する。
    /startday — Mendaftarkan tugas dan memulai sesi pengawasan.
    """
    global _notify_channel
    _notify_channel = interaction.channel  # type: ignore[assignment]

    await interaction.response.defer()

    task_list = [t.strip() for t in tasks.split(",") if t.strip()]
    judgment = await orchestrator.handle_startday(task_list)

    await interaction.followup.send(_format_judgment(judgment.model_dump_json()))


@bot.tree.command(name="progress", description="Report your current progress.")
@app_commands.describe(update="What have you done so far? / 現在の進捗は？ / Apa yang sudah kamu kerjakan?")
async def progress(interaction: discord.Interaction, update: str) -> None:
    """
    /progress — Records activity and returns Claude's assessment.
    /progress — 活動を記録し、Claudeの評価を返す。
    /progress — Mencatat aktivitas dan mengembalikan penilaian Claude.
    """
    await interaction.response.defer()

    judgment = await orchestrator.handle_progress(update)

    await interaction.followup.send(_format_judgment(judgment.model_dump_json()))


@bot.tree.command(name="endday", description="End your work session.")
async def endday(interaction: discord.Interaction) -> None:
    """
    /endday — Closes the session and returns Claude's end-of-day summary.
    /endday — セッションを終了し、Claudeの終業要約を返す。
    /endday — Menutup sesi dan mengembalikan ringkasan akhir hari dari Claude.
    """
    await interaction.response.defer()

    judgment = await orchestrator.handle_endday()

    await interaction.followup.send(_format_judgment(judgment.model_dump_json()))


# ──────────────────────────────────────────────
# Entry point / エントリーポイント / Titik masuk
# ──────────────────────────────────────────────

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN is not set in .env. "
            ".envにDISCORD_BOT_TOKENが設定されていません。"
            "DISCORD_BOT_TOKEN tidak diatur di .env."
        )
    bot.run(token)
