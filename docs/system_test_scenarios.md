# システムテストシナリオ

## 前提条件

- テスト用Discordサーバーが作成済みであること
- テスト用BotがサーバーにINVITE済みであること
- `.env.test` に以下が設定済みであること

```env
DISCORD_BOT_TOKEN=     # テスト用Botトークン
ANTHROPIC_API_KEY= # テスト用APIキー
SMTP_HOST=         # メールテスト用（省略可）
SMTP_PORT=
SMTP_USER=
SMTP_PASS=
ALERT_SENDER=
ALERT_RECIPIENT=
```

- Bot起動コマンド: `.venv/Scripts/python bot.py`

---

## ST-01: 正常系 — 1日の基本フロー

**目的**: startday → progress → endday の基本フローが正常に動作すること

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `/startday tasks:設計,実装,レビュー` を送信 | JSONが返る。`assessment` が `on_track` または `overloaded` |
| 2 | 返却JSONに `action` キーが含まれること | `continue` または `reduce_tasks` |
| 3 | `/progress update:設計完了、実装着手中` を送信 | JSONが返る。`assessment` が `on_track` |
| 4 | 返却JSONの `clarification_needed` が `false` | 確認 |
| 5 | `/endday` を送信 | JSONが返る。`summary` に文字列が含まれること |

**合否判定**: 全ステップでJSONが返り、キーが仕様通りであること

---

## ST-02: 正常系 — タスク過多による過負荷検知

**目的**: タスク数が多い場合に `overloaded` 判定が返ること

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `/startday tasks:A,B,C,D,E,F,G,H,I,J` を送信（10件以上） | JSONが返る |
| 2 | `assessment` が `overloaded` | 確認 |
| 3 | `action` が `reduce_tasks` | 確認 |

**合否判定**: `overloaded` + `reduce_tasks` の組み合わせが返ること

---

## ST-03: 正常系 — 曖昧な進捗への clarification

**目的**: 進捗内容が曖昧な場合に `clarification_needed: true` が返ること

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `/startday tasks:タスクA` を送信 | JSONが返る |
| 2 | `/progress update:...` （内容なし、または極端に短い） | JSONが返る |
| 3 | `clarification_needed` が `true` | 確認 |
| 4 | `message` に質問文が含まれること | 確認 |

**合否判定**: `clarification_needed: true` かつ `message` が1文の質問であること

---

## ST-04: 正常系 — セッションリセット

**目的**: `/startday` を2回実行した場合に前のセッションがリセットされること

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `/startday tasks:旧タスク` を送信 | JSONが返る |
| 2 | `/progress update:作業中` を送信 | JSONが返る |
| 3 | `/startday tasks:新タスク` を再送信 | JSONが返る |
| 4 | 返却JSONが新タスクに基づいた判断であること | 確認 |

**合否判定**: 2回目の `/startday` が正常に受け付けられ、新しいセッションで動作すること

---

## ST-05: 正常系 — 60分無反応リマインド

**目的**: 60分間 `/progress` がない場合にDiscordへリマインドが送信されること

> **注意**: `orchestrator.py` の `THRESHOLD_DISCORD_REMINDER` を一時的に `1`（分）に変更してテストすること。テスト後は元の値（`60`）に戻すこと。

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `THRESHOLD_DISCORD_REMINDER = 1` に変更してBot起動 | — |
| 2 | `/startday tasks:タスクA` を送信 | JSONが返る |
| 3 | 約1分間何も操作しない | — |
| 4 | Botから自動でJSONが送信される | `action: "remind"` を含むこと |

**合否判定**: ユーザー操作なしでDiscordにリマインドメッセージが届くこと

---

## ST-06: 正常系 — 120分無反応メールアラート

**目的**: 120分間無反応の場合にメールが送信されDiscordにも通知されること

> **注意**: `THRESHOLD_EMAIL_ALERT` を一時的に `2`（分）に変更してテストすること。SMTPが設定済みであること。

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `THRESHOLD_DISCORD_REMINDER = 1`, `THRESHOLD_EMAIL_ALERT = 2` に変更してBot起動 | — |
| 2 | `/startday tasks:タスクA` を送信 | JSONが返る |
| 3 | 約2分間何も操作しない | — |
| 4 | Discordに `action: "alert"` を含むJSONが届く | 確認 |
| 5 | `ALERT_RECIPIENT` 宛にメールが届く | 確認 |

**合否判定**: Discord通知とメール送信の両方が行われること

---

## ST-07: 正常系 — 180分無反応スコープ縮小

**目的**: 180分間無反応の場合にClaudeが `stagnating` 判定を返しDiscordに通知されること

> **注意**: `THRESHOLD_REDUCE_SCOPE` を一時的に `3`（分）に変更してテストすること。

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | 各しきい値を `1`, `2`, `3` 分に変更してBot起動 | — |
| 2 | `/startday tasks:タスクA` を送信 | JSONが返る |
| 3 | 約3分間何も操作しない | — |
| 4 | Discordに `assessment: "stagnating"` を含むJSONが届く | 確認 |
| 5 | その後 `/progress update:再開` を送信 | `on_track` に回復すること |

**合否判定**: `stagnating` 通知後に `/progress` で正常に回復できること

---

## ST-08: 異常系 — セッション未開始での /progress

**目的**: `/startday` なしで `/progress` を実行した場合に適切に処理されること

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | Bot起動直後（`/startday` 未実行）に `/progress update:作業中` を送信 | エラーにならずJSONが返ること |
| 2 | `clarification_needed: true` またはエラーメッセージが返る | 確認 |

**合否判定**: クラッシュせず何らかのJSONが返ること

---

## ST-09: 異常系 — /endday の二重実行

**目的**: `/endday` を連続で2回実行してもクラッシュしないこと

| # | 操作 | 期待結果 |
|---|---|---|
| 1 | `/startday tasks:タスクA` → `/progress update:完了` → `/endday` | JSONが返る |
| 2 | 続けて `/endday` を再送信 | エラーにならずJSONが返ること |

**合否判定**: 2回目の `/endday` でもクラッシュしないこと

---

## 実施記録テンプレート

```
実施日    : YYYY-MM-DD
実施者    :
Botバージョン（git commit）:
環境      : テスト用Discordサーバー名

| シナリオ | 結果 | 備考 |
|---|---|---|
| ST-01 | 合格 / 不合格 / 未実施 | |
| ST-02 | 合格 / 不合格 / 未実施 | |
| ST-03 | 合格 / 不合格 / 未実施 | |
| ST-04 | 合格 / 不合格 / 未実施 | |
| ST-05 | 合格 / 不合格 / 未実施 | |
| ST-06 | 合格 / 不合格 / 未実施 | |
| ST-07 | 合格 / 不合格 / 未実施 | |
| ST-08 | 合格 / 不合格 / 未実施 | |
| ST-09 | 合格 / 不合格 / 未実施 | |
```