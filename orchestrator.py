"""
orchestrator.py

Coordinates state management, inactivity detection, Claude judgment, and notifications.
状態管理・無反応検出・Claude判断・通知を統合するオーケストレーターモジュール。
Mengoordinasikan manajemen status, deteksi tidak aktif, penilaian Claude, dan notifikasi.
"""

import asyncio
import logging
import smtplib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from email.mime.text import MIMEText

from claude_client import ClaudeClient, SupervisorJudgment
from state_store import InvalidTransitionError, State, StateStore

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Configuration / 設定 / Konfigurasi
# ──────────────────────────────────────────────

@dataclass
class EmailConfig:
    """
    SMTP settings for sending inactivity alert emails.
    無反応アラートメール送信用のSMTP設定。
    Pengaturan SMTP untuk mengirim email peringatan tidak aktif.
    """
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    sender: str
    recipient: str


# Inactivity thresholds (minutes) / 無反応しきい値（分） / Ambang batas tidak aktif (menit)
THRESHOLD_DISCORD_REMINDER = 60    # Discord reminder / Discordリマインド / Pengingat Discord
THRESHOLD_EMAIL_ALERT      = 120   # Email notification / メール通知 / Notifikasi email
THRESHOLD_REDUCE_SCOPE     = 180   # Claude-driven scope reduction / Claudeによる縮小提案 / Pengurangan lingkup oleh Claude

# How often the background loop checks inactivity (seconds)
# バックグラウンドループが無反応を確認する間隔（秒）
# Seberapa sering loop background memeriksa ketidakaktifan (detik)
CHECK_INTERVAL_SECONDS = 60


# ──────────────────────────────────────────────
# Notify callback type / 通知コールバック型 / Tipe callback notifikasi
# ──────────────────────────────────────────────

# Async function that sends a message to Discord.
# Discordにメッセージを送る非同期関数の型。
# Fungsi async yang mengirim pesan ke Discord.
DiscordNotify = Callable[[str], Awaitable[None]]


# ──────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────

class Orchestrator:
    """
    Central coordinator between StateStore, ClaudeClient, Discord, and email.
    StateStore・ClaudeClient・Discord・メールを統合する中央コーディネーター。
    Koordinator pusat antara StateStore, ClaudeClient, Discord, dan email.

    The Discord bot calls handle_* methods; this class owns all business logic.
    Discord botはhandle_*メソッドを呼ぶ。このクラスがビジネスロジック全体を担う。
    Discord bot memanggil metode handle_*; kelas ini memiliki semua logika bisnis.
    """

    def __init__(
        self,
        discord_notify: DiscordNotify,
        email_config: EmailConfig | None = None,
    ) -> None:
        """
        Args:
            discord_notify (DiscordNotify): Async callback to send a Discord message.
                                            Discordメッセージ送信用の非同期コールバック。
                                            Callback async untuk mengirim pesan Discord.
            email_config (EmailConfig | None): SMTP config, or None to disable email.
                                               SMTP設定、またはNoneでメール無効。
                                               Konfigurasi SMTP, atau None untuk nonaktifkan email.
        """
        self._store = StateStore()
        self._claude = ClaudeClient()
        self._discord_notify = discord_notify
        self._email_config = email_config

        # Track which inactivity notifications have already fired this session.
        # 今のセッションで既に発火した無反応通知を追跡する。
        # Melacak notifikasi ketidakaktifan mana yang sudah dipicu sesi ini.
        self._notified: set[int] = set()

        self._loop_task: asyncio.Task | None = None

    # ──────────────────────────────────────────
    # Lifecycle / ライフサイクル / Siklus hidup
    # ──────────────────────────────────────────

    async def start(self) -> None:
        """
        Starts the background inactivity monitoring loop.
        バックグラウンドの無反応監視ループを開始する。
        Memulai loop pemantauan ketidakaktifan di latar belakang.
        """
        if self._loop_task and not self._loop_task.done():
            return
        self._loop_task = asyncio.create_task(self._inactivity_loop())
        logger.info("Orchestrator started / 起動 / Dimulai")

    async def stop(self) -> None:
        """
        Cancels the background monitoring loop.
        バックグラウンド監視ループをキャンセルする。
        Membatalkan loop pemantauan latar belakang.
        """
        if self._loop_task:
            self._loop_task.cancel()
            logger.info("Orchestrator stopped / 停止 / Dihentikan")

    # ──────────────────────────────────────────
    # Command handlers / コマンドハンドラー / Handler perintah
    # ──────────────────────────────────────────

    async def handle_startday(self, tasks: list[str]) -> SupervisorJudgment:
        """
        Handles the /startday command: sets tasks and transitions to PLANNED.
        /startdayコマンド処理: タスクを設定しPLANNEDへ遷移する。
        Menangani perintah /startday: mengatur tugas dan bertransisi ke PLANNED.

        Args:
            tasks (list[str]): Tasks the user plans to complete today.
                               ユーザーが今日完了する予定のタスク。
                               Tugas yang direncanakan pengguna untuk diselesaikan hari ini.

        Returns:
            SupervisorJudgment: Claude's initial assessment of the plan.
                                計画に対するClaudeの初期評価。
                                Penilaian awal Claude terhadap rencana.
        """
        self._store.reset()
        self._store.set_tasks(tasks)
        self._store.start_session()
        self._store.transition(State.PLANNED)
        self._notified.clear()

        judgment = self._claude.judge(self._store.to_dict())
        logger.info("Session started / セッション開始 / Sesi dimulai: %s", tasks)
        return judgment

    async def handle_progress(self, update_text: str) -> SupervisorJudgment:
        """
        Handles the /progress command: records activity and asks Claude to assess.
        /progressコマンド処理: 活動を記録しClaudeに評価を依頼する。
        Menangani perintah /progress: mencatat aktivitas dan meminta Claude menilai.

        Args:
            update_text (str): User's progress description.
                               ユーザーの進捗説明。
                               Deskripsi kemajuan pengguna.

        Returns:
            SupervisorJudgment: Claude's assessment of current progress.
                                現在の進捗に対するClaudeの評価。
                                Penilaian Claude atas kemajuan saat ini.
        """
        # Transition to WORKING if still in PLANNED.
        # まだPLANNEDなら WORKINGへ遷移する。
        # Transisi ke WORKING jika masih di PLANNED.
        if self._store.state == State.PLANNED:
            self._store.transition(State.WORKING)

        # If STAGNATING, recovery on progress report.
        # STAGNATINGなら進捗報告で回復する。
        # Jika STAGNATING, pulihkan saat ada laporan kemajuan.
        if self._store.state == State.STAGNATING:
            self._store.transition(State.WORKING)

        self._store.record_activity()
        self._notified.discard(THRESHOLD_DISCORD_REMINDER)
        self._notified.discard(THRESHOLD_EMAIL_ALERT)

        snapshot = self._store.to_dict()
        snapshot["progress_update"] = update_text

        judgment = self._claude.judge(snapshot)
        logger.info("Progress recorded / 進捗記録 / Kemajuan dicatat: %s", update_text[:80])
        return judgment

    async def handle_endday(self) -> SupervisorJudgment:
        """
        Handles the /endday command: transitions to DONE and asks Claude to summarize.
        /enddayコマンド処理: DONEへ遷移しClaudeに要約を依頼する。
        Menangani perintah /endday: bertransisi ke DONE dan meminta Claude merangkum.

        Returns:
            SupervisorJudgment: Claude's end-of-day summary judgment.
                                Claudeの終業時の総括評価。
                                Penilaian ringkasan akhir hari dari Claude.
        """
        try:
            self._store.transition(State.DONE)
        except InvalidTransitionError:
            # Already DONE or IDLE — still ask Claude for a summary.
            # すでにDONEまたはIDLE — それでもClaudeに要約を依頼する。
            # Sudah DONE atau IDLE — tetap minta Claude merangkum.
            pass

        self._store.record_activity()
        judgment = self._claude.judge(self._store.to_dict())
        logger.info("Session ended / セッション終了 / Sesi berakhir")
        return judgment

    # ──────────────────────────────────────────
    # Background loop / バックグラウンドループ / Loop latar belakang
    # ──────────────────────────────────────────

    async def _inactivity_loop(self) -> None:
        """
        Periodically checks inactivity and fires notifications at each threshold.
        定期的に無反応を確認し、各しきい値で通知を発火する。
        Secara berkala memeriksa ketidakaktifan dan memicu notifikasi pada setiap ambang batas.
        """
        while True:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            await self._check_inactivity()

    async def _check_inactivity(self) -> None:
        """
        Evaluates elapsed time and triggers the appropriate notification tier.
        経過時間を評価し、適切な通知ティアをトリガーする。
        Mengevaluasi waktu yang berlalu dan memicu tingkatan notifikasi yang sesuai.

        Thresholds (from DESIGN.md):
        - 60 min  → Discord reminder
        - 120 min → email alert
        - 180 min → Claude-driven scope reduction + STAGNATING state
        """
        # Only monitor during an active session.
        # アクティブなセッション中のみ監視する。
        # Hanya pantau selama sesi aktif.
        if self._store.state not in (State.WORKING, State.PLANNED):
            return

        elapsed = self._store.get_minutes_since_last_activity()
        if elapsed is None:
            return

        # Fire each threshold exactly once per session.
        # 各しきい値はセッションごとに1回だけ発火する。
        # Picu setiap ambang batas tepat sekali per sesi.
        if elapsed >= THRESHOLD_REDUCE_SCOPE and THRESHOLD_REDUCE_SCOPE not in self._notified:
            await self._on_reduce_scope()
            self._notified.add(THRESHOLD_REDUCE_SCOPE)

        elif elapsed >= THRESHOLD_EMAIL_ALERT and THRESHOLD_EMAIL_ALERT not in self._notified:
            await self._on_email_alert()
            self._notified.add(THRESHOLD_EMAIL_ALERT)

        elif elapsed >= THRESHOLD_DISCORD_REMINDER and THRESHOLD_DISCORD_REMINDER not in self._notified:
            await self._on_discord_reminder()
            self._notified.add(THRESHOLD_DISCORD_REMINDER)

    # ──────────────────────────────────────────
    # Notification actions / 通知アクション / Aksi notifikasi
    # ──────────────────────────────────────────

    async def _on_discord_reminder(self) -> None:
        """
        Sends a 60-minute inactivity reminder to Discord.
        60分無反応のリマインドをDiscordに送る。
        Mengirim pengingat ketidakaktifan 60 menit ke Discord.
        """
        logger.info("60min inactivity / 60分無反応 / 60 menit tidak aktif")
        await self._discord_notify(
            '{"assessment": "idle", "action": "remind", '
            '"message": "No update for 60 minutes. Use /progress to check in.", '
            '"clarification_needed": false}'
        )

    async def _on_email_alert(self) -> None:
        """
        Sends a 120-minute inactivity alert via email (if configured).
        120分無反応のアラートをメールで送る（設定済みの場合）。
        Mengirim peringatan ketidakaktifan 120 menit melalui email (jika dikonfigurasi).
        """
        logger.warning("120min inactivity — sending email / 120分無反応 — メール送信 / 120 menit tidak aktif — mengirim email")
        await self._discord_notify(
            '{"assessment": "idle", "action": "alert", '
            '"message": "No update for 120 minutes. Email alert sent.", '
            '"clarification_needed": false}'
        )
        if self._email_config:
            await asyncio.get_event_loop().run_in_executor(
                None, self._send_email
            )

    async def _on_reduce_scope(self) -> None:
        """
        Marks the session as STAGNATING and asks Claude to propose a scope reduction.
        セッションをSTAGNATINGにマークし、Claudeに縮小提案を依頼する。
        Menandai sesi sebagai STAGNATING dan meminta Claude mengusulkan pengurangan lingkup.
        """
        logger.warning("180min inactivity — reducing scope / 180分無反応 — スコープ縮小 / 180 menit tidak aktif — mengurangi lingkup")

        try:
            self._store.transition(State.STAGNATING)
        except InvalidTransitionError:
            pass  # Already STAGNATING / すでにSTAGNATING / Sudah STAGNATING

        judgment = self._claude.judge(self._store.to_dict())
        await self._discord_notify(judgment.model_dump_json())

    # ──────────────────────────────────────────
    # Email / メール / Email
    # ──────────────────────────────────────────

    def _send_email(self) -> None:
        """
        Sends an inactivity alert email via SMTP (blocking — run in executor).
        SMTPで無反応アラートメールを送信する（ブロッキング — executorで実行）。
        Mengirim email peringatan ketidakaktifan melalui SMTP (blocking — jalankan di executor).
        """
        if not self._email_config:
            return

        cfg = self._email_config
        body = (
            "Work supervisor alert: no activity detected for 120 minutes.\n"
            "作業監視アラート: 120分間活動が検出されませんでした。\n"
            "Peringatan supervisor kerja: tidak ada aktivitas yang terdeteksi selama 120 menit."
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "[Work Supervisor] Inactivity Alert / 無反応アラート"
        msg["From"] = cfg.sender
        msg["To"] = cfg.recipient

        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
                server.starttls()
                server.login(cfg.username, cfg.password)
                server.sendmail(cfg.sender, [cfg.recipient], msg.as_string())
            logger.info("Email sent / メール送信完了 / Email terkirim → %s", cfg.recipient)
        except smtplib.SMTPException as exc:
            logger.error("Email failed / メール送信失敗 / Email gagal: %s", exc)
