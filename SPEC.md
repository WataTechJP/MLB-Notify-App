# MLB日本人選手 通知アプリ - 仕様書（Python Backend版）

## 1. 概要

本アプリは、MLBに所属する日本人選手の活躍（例：ホームラン、奪三振など）を検知し、ユーザーへ15〜30秒以内にプッシュ通知を送信するアプリである。

対象：

- iOS / Android（Expo / React Native）
- バックエンド：Python（FastAPI）
- データ取得：MLB Stats API（statsapi.mlb.com）
- ポーリング間隔：15〜30秒

目的：

- 準リアルタイム通知（最大遅延30秒）
- 拡張可能なアーキテクチャ
- 将来的な商用化対応

---

## 2. システム構成

### 2.1 全体アーキテクチャ

MLB Stats API
        ↓
Python FastAPI Server（常時稼働）
        ↓
イベント検知ロジック（15〜30秒ごと）
        ↓
Redis（重複防止）
        ↓
Expo Push API
        ↓
ユーザー端末

---

## 3. 機能要件

### 3.1 ポーリング処理

- 15〜30秒ごとに試合データ取得
- 試合ID（gamePk）を事前取得
- live feedを解析
- 新規イベントのみ検知

---

### 3.2 対象イベント（初期）

野手：

- ホームラン

将来的に以下も対象

- ヒット
- 打点

投手：

- 奪三振

将来的に以下も対象

- 勝利
- セーブ

---

### 3.3 重複通知防止

Redisに保存：

last_event:{player_id}

フロー：

- 最新イベントID取得
- Redis保存値と比較
- 異なる場合のみ通知
- 通知後Redis更新

---

### 3.4 ユーザー通知制御

ユーザーは以下を選択可能：

- 通知対象選手
- 通知対象イベント種別
- 通知ON/OFF

DB例：

users/
  user_id
    push_token
    selected_players[]
    selected_events{}

通知処理時：

- イベント発生
- 該当プレイヤーを選択しているユーザー抽出
- 該当イベントをONにしているユーザーにのみ送信

---

## 4. 非機能要件

### 4.1 パフォーマンス

- API反映後30秒以内通知
- ポーリング処理 < 2秒

### 4.2 可用性

- 常時稼働サーバー
- Docker化推奨
- VPS or Cloud VM配置

### 4.3 スケール設計

- ユーザー数1,000人想定
- Push送信は非同期処理
- 将来Queue（RabbitMQ / Redis Queue）導入可能

---

## 5. 技術スタック

Backend:

- Python 3.11+
- FastAPI
- APScheduler（定期実行）
- Redis（重複防止）
- Uvicorn

Frontend:

- Expo
- expo-notifications

Infra: 今後検討

- VPS / Oracle Cloud Free Tier / AWS EC2
- Docker

---

## 6. 将来拡張

- WebSocket化（有料API導入時）
- 試合速報モード
- 日本人選手自動同期
- プレミアム機能（高速通知）
- サブスクモデル

---

## 7. 成功基準

- 15〜30秒以内通知達成
- 重複通知なし
- ユーザー別通知制御成功
- 安定稼働（MLBシーズン中）

### 7. まず何から作りますか？ → バックエンドのみ（Recommended）

- ユーザーデータ（push_token、選手設定など）の保存先は？ → SQLite（Recommended）
- Redis の環境は？ → Docker Compose で立てる（Recommended）
