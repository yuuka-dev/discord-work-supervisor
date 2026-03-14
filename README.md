
# discord-work-supervisor

在宅勤務時のタスク管理とサボり防止を目的とした  
**Discord常駐型の個人向けワーク管理Bot**。

監視や稼働時間計測は行わず、  
「タスクの言語化」と「定期的な進捗確認」によって  
作業の停滞を防ぐ。

---

## 🎯 目的

- 在宅勤務で「今日は何をするか」を明確にする
- サボり・停滞を**監視なし**で防止する
- Discordを業務のメインUIとして使う
- 無反応時のみメール通知を行う

---

## ✅ できること

- 朝のタスク提出（必須 / できたら / 余力）
- 定期的な進捗確認
- 無反応検知とリマインド
- 最終手段としてのメール通知
- 夕方の振り返り

---

## ❌ やらないこと（重要）

- 常時監視
- 稼働時間の記録
- スクリーンショット取得
- 感情的なフィードバック
- 自動実行・勝手な予定追加

---

## 🧠 全体構成

- UI: Discord Bot
- 制御: Python Orchestrator
- 判断: Claude（Supervisorロール）
- 実行環境: ローカルPC常駐
- 通知: Discord + SMTPメール

Claudeは**判断のみ**を担当し、  
実行・時間管理・状態管理はすべてPython側で行う。

---

## 🕹 コマンド

- `/startday`  
  今日のタスクを提出する

- `/progress`  
  現在の作業状況を一言で報告する

- `/endday`  
  1日の振り返りを行う

---

## 🛠 セットアップ（ローカルPC）

### 前提

- Python 3.10+
- Discord Bot Token
- Claude API Key
- SMTPサーバ情報
- PCはスリープ無効・常時起動

### 手順

```bash
pip install -r requirements.txt
cp .env.example .env
python bot.py
