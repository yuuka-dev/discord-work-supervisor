# Discord 在宅タスク管理 Bot 設計メモ

## 1. 目的
- 在宅勤務のタスク明確化
- サボり防止（監視なし）
- Discord中心、無反応時のみメール

## 2. 全体構成
- UI: Discord Bot
- 制御: Python Orchestrator
- 判断: Claude（Supervisorロール）
- 実行環境: 自分PC常駐
- 通知: Discord + SMTPメール

## 3. 役割分担
- Discord: 入出力のみ
- Python: 状態管理・時間管理・通知制御
- Claude: 判断・要約・縮小提案のみ（実行不可）

## 4. 状態設計
IDLE → PLANNED → WORKING → DONE  
例外: 無反応 → STAGNATING

## 5. コマンド
- /startday
- /progress
- /endday

## 6. サボり防止ルール
- 60分無反応: Discordリマインド
- 120分無反応: メール通知
- 180分無反応: タスク縮小

## 7. 運用前提
- PCは常時起動
- スリープ無効
- Botは自動起動
- トークンは.env管理

## 8. 意図的にやらないこと
- 常時監視
- 稼働時間計測
- 感情的フィードバック