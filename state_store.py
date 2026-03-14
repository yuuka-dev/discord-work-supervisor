"""
state_store.py

Manages the state of the work supervision session.
作業監視セッションの状態を管理するモジュール。
Mengelola status sesi pengawasan kerja.
"""

from datetime import datetime
from enum import Enum


class State(Enum):
    """
    Represents the possible states of a work session.
    作業セッションの状態を表す列挙型。
    Mewakili kemungkinan status sesi kerja.

    Transitions / 遷移 / Transisi:
        IDLE → PLANNED → WORKING → DONE
                                 ↘ STAGNATING (on inactivity / 無反応時 / saat tidak ada respons)
    """
    IDLE       = "IDLE"        # Not started / 未開始 / Belum dimulai
    PLANNED    = "PLANNED"     # Tasks defined / タスク定義済み / Tugas telah ditentukan
    WORKING    = "WORKING"     # In progress / 作業中 / Sedang dikerjakan
    DONE       = "DONE"        # Completed / 完了 / Selesai
    STAGNATING = "STAGNATING"  # No response detected / 無反応検出 / Tidak ada respons terdeteksi


# Valid state transitions
# 有効な状態遷移
# Transisi status yang valid
VALID_TRANSITIONS: dict[State, list[State]] = {
    State.IDLE:       [State.PLANNED],
    State.PLANNED:    [State.WORKING, State.IDLE],
    State.WORKING:    [State.DONE, State.STAGNATING],
    State.STAGNATING: [State.WORKING, State.DONE],
    State.DONE:       [State.IDLE],
}


class InvalidTransitionError(Exception):
    """
    Raised when an invalid state transition is attempted.
    無効な状態遷移が試みられたときに発生する例外。
    Dikembalikan saat transisi status yang tidak valid dicoba.
    """
    pass


class StateStore:
    """
    Stores and manages session state and timing information.
    セッションの状態とタイミング情報を保存・管理するクラス。
    Menyimpan dan mengelola status sesi serta informasi waktu.

    Attributes:
        state (State): Current session state / 現在のセッション状態 / Status sesi saat ini
        last_activity_at (datetime | None): Timestamp of last user activity
                                            最後のユーザー活動のタイムスタンプ
                                            Waktu aktivitas pengguna terakhir
        session_started_at (datetime | None): Timestamp when session began
                                              セッション開始のタイムスタンプ
                                              Waktu sesi dimulai
        tasks (list[str]): List of planned tasks / 計画タスクのリスト / Daftar tugas yang direncanakan
    """

    def __init__(self) -> None:
        """
        Initializes the store with default values.
        デフォルト値でストアを初期化する。
        Menginisialisasi store dengan nilai default.
        """
        self.state: State = State.IDLE
        self.last_activity_at: datetime | None = None
        self.session_started_at: datetime | None = None
        self.tasks: list[str] = []

    def transition(self, new_state: State) -> None:
        """
        Transitions to a new state if the transition is valid.
        有効な場合に新しい状態へ遷移する。
        Melakukan transisi ke status baru jika transisi valid.

        Args:
            new_state (State): The target state / 遷移先の状態 / Status tujuan

        Raises:
            InvalidTransitionError: If the transition is not allowed.
                                    遷移が許可されていない場合。
                                    Jika transisi tidak diizinkan.
        """
        allowed = VALID_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {self.state.value} to {new_state.value}. "
                f"{self.state.value} から {new_state.value} への遷移は無効です。"
                f"Transisi dari {self.state.value} ke {new_state.value} tidak diizinkan."
            )
        self.state = new_state

    def record_activity(self) -> None:
        """
        Records the current time as the latest user activity.
        現在時刻を最新のユーザー活動として記録する。
        Mencatat waktu saat ini sebagai aktivitas pengguna terbaru.
        """
        self.last_activity_at = datetime.now()

    def start_session(self) -> None:
        """
        Marks the session start time and records initial activity.
        セッション開始時刻を記録し、初期活動を記録する。
        Menandai waktu mulai sesi dan mencatat aktivitas awal.
        """
        now = datetime.now()
        self.session_started_at = now
        self.last_activity_at = now

    def get_minutes_since_last_activity(self) -> float | None:
        """
        Returns elapsed minutes since the last recorded activity.
        最後の活動から経過した分数を返す。
        Mengembalikan menit yang telah berlalu sejak aktivitas terakhir.

        Returns:
            float | None: Elapsed minutes, or None if no activity has been recorded.
                          経過分数。活動が記録されていない場合は None。
                          Menit yang berlalu, atau None jika tidak ada aktivitas yang tercatat.
        """
        if self.last_activity_at is None:
            return None
        delta = datetime.now() - self.last_activity_at
        return delta.total_seconds() / 60

    def set_tasks(self, tasks: list[str]) -> None:
        """
        Stores the list of planned tasks for the session.
        セッションの計画タスクリストを保存する。
        Menyimpan daftar tugas yang direncanakan untuk sesi.

        Args:
            tasks (list[str]): Task descriptions / タスクの説明リスト / Deskripsi tugas
        """
        self.tasks = tasks

    def reset(self) -> None:
        """
        Resets all state to initial values.
        全状態を初期値にリセットする。
        Mengatur ulang semua status ke nilai awal.
        """
        self.__init__()

    def to_dict(self) -> dict:
        """
        Returns the current state as a plain dictionary (for logging or Claude input).
        現在の状態を辞書形式で返す（ログやClaudeへの入力用）。
        Mengembalikan status saat ini sebagai kamus biasa (untuk logging atau input Claude).

        Returns:
            dict: Serialized state snapshot / 状態のスナップショット / Snapshot status
        """
        return {
            "state": self.state.value,
            "tasks": self.tasks,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "session_started_at": self.session_started_at.isoformat() if self.session_started_at else None,
            "minutes_since_last_activity": self.get_minutes_since_last_activity(),
        }
