# MLB日本人選手通知アプリ - バックエンド

MLBに所属する日本人選手のホームラン・奪三振を15〜30秒以内に検知し、Expo Push通知を送信するバックエンド。

---

## アーキテクチャ

```
MLB Stats API (20秒ごとポーリング)
        ↓
FastAPI (APScheduler)
        ↓
イベント検知 (ホームラン / 奪三振)
        ↓
Redis (重複防止)
        ↓
Expo Push API
        ↓
ユーザー端末 (iOS / Android)
```

---

## 技術スタック

| 項目 | 内容 |
|------|------|
| 言語 | Python 3.11+ |
| フレームワーク | FastAPI 0.115 |
| パッケージ管理 | uv |
| DB | SQLite (SQLAlchemy 2.0 async + aiosqlite) |
| キャッシュ | Redis 7 (Docker Compose) |
| スケジューラー | APScheduler 3.10 (AsyncIOScheduler) |
| HTTP クライアント | httpx 0.27 |
| プッシュ通知 | Expo Push API |

---

## ディレクトリ構成

```
MLB APP/
├── docker-compose.yml        # Redis
├── .env                      # 環境変数 (gitignore済み)
├── .env.example
└── backend/
    ├── pyproject.toml        # 依存パッケージ (uv管理)
    ├── Dockerfile
    └── app/
        ├── main.py           # FastAPI app + lifespan
        ├── config.py         # 環境変数管理 (pydantic-settings)
        ├── database.py       # SQLAlchemy async engine
        ├── redis_client.py   # Redis接続管理
        ├── models/
        │   └── user.py       # users / user_players / user_event_prefs
        ├── schemas/
        │   └── user.py       # Pydantic リクエスト/レスポンス
        ├── constants/
        │   └── japanese_players.py  # 日本人選手マスタ
        ├── api/v1/
        │   ├── router.py
        │   ├── users.py      # 登録・設定エンドポイント
        │   └── players.py    # 選手一覧エンドポイント
        └── services/
            ├── mlb_api.py        # MLB Stats API クライアント
            ├── event_detector.py # イベント検知 + Redis重複チェック
            ├── notification.py   # Expo Push送信
            └── scheduler.py      # APScheduler (20秒間隔)
```

---

## セットアップ

### 前提条件
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) インストール済み
- Docker / Docker Compose

### 手順

```bash
# 1. Redisを起動
docker compose up -d redis

# 2. Python仮想環境を作成・依存インストール
cd backend
uv venv .venv
uv sync

# 3. 環境変数を設定
cp ../.env.example ../.env
# .env を必要に応じて編集

# 4. サーバーを起動
.venv/bin/uvicorn app.main:app --reload --port 8001
```

起動ログに `Scheduler started (interval=20s)` が出ていれば正常。

---

## 環境変数

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis接続URL |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/mlb_app.db` | SQLite DB パス |
| `POLL_INTERVAL_SECONDS` | `20` | MLB APIポーリング間隔(秒) |
| `MLB_API_BASE_URL` | `https://statsapi.mlb.com/api` | MLB Stats API ベースURL |
| `DEBUG` | `false` | trueにすると `/docs` が有効・SQLログ出力 |

---

## API エンドポイント

| Method | Path | 説明 |
|--------|------|------|
| `GET` | `/api/v1/health` | ヘルスチェック |
| `GET` | `/api/v1/players` | 日本人選手一覧 |
| `POST` | `/api/v1/users/register` | Expo Push Token 登録/更新 |
| `GET` | `/api/v1/preferences/{push_token}` | ユーザー設定取得 |
| `PUT` | `/api/v1/preferences/{push_token}/players` | 購読選手を更新 |
| `PUT` | `/api/v1/preferences/{push_token}/events` | イベント通知設定を更新 |

### リクエスト例

```bash
# ユーザー登録
curl -X POST http://localhost:8001/api/v1/users/register \
  -H "Content-Type: application/json" \
  -d '{"expo_push_token": "ExponentPushToken[xxxxxx]"}'

# 購読選手を大谷翔平のみに変更
curl -X PUT http://localhost:8001/api/v1/preferences/ExponentPushToken[xxxxxx]/players \
  -H "Content-Type: application/json" \
  -d '{"player_ids": [660271]}'

# ホームランのみ通知ON・三振通知OFF
curl -X PUT http://localhost:8001/api/v1/preferences/ExponentPushToken[xxxxxx]/events \
  -H "Content-Type: application/json" \
  -d '{"home_run": true, "strikeout": false}'
```

---

## 対象選手（初期）

| 選手名 | player_id | ポジション | チーム |
|--------|-----------|-----------|-------|
| 大谷翔平 | 660271 | 投手/野手 | LAD |
| 吉田正尚 | 807799 | 野手 | BOS |
| 鈴木誠也 | 673548 | 野手 | CHC |
| 今永昇太 | 681936 | 投手 | CHC |
| 菊池雄星 | 579328 | 投手 | TOR |

選手追加は `backend/app/constants/japanese_players.py` を編集。

---

## イベント検知ロジック

```
20秒ごと
  → 今日の試合一覧取得 (MLB Stats API)
  → 各試合のライブフィードを並列取得
  → abstractGameState == "Live" の試合のみ処理
  → allPlays をループ
      → event が "Home Run" または "Strikeout" か？
      → batter/pitcher が日本人選手か？
      → Redis key "last_event:{player_id}:{game_pk}" と atBatIndex を比較
      → 新規なら Redis更新 → 対象ユーザー取得 → Expo Push送信
```

### Redis スキーマ
- Key: `last_event:{player_id}:{game_pk}`
- Value: `atBatIndex` (int)
- TTL: 86400秒 (24h)

---

## DBスキーマ

```sql
users (
  id INTEGER PRIMARY KEY,
  expo_push_token TEXT UNIQUE NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at DATETIME,
  updated_at DATETIME
)

user_players (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  player_id INTEGER,
  UNIQUE(user_id, player_id)
)

user_event_prefs (
  id INTEGER PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  event_type TEXT,         -- "home_run" | "strikeout"
  is_enabled BOOLEAN DEFAULT TRUE,
  UNIQUE(user_id, event_type)
)
```

---

## テスト (Spring Training 中)

レギュラーシーズン以外は `gameType` を変更して動作確認できる。

`backend/app/services/event_detector.py` 末尾の呼び出しを一時的に変更：

```python
# R = Regular Season (本番)
# S = Spring Training (オープン戦)
await detect_events(redis, db, http_client, game_type="S")
```

---

## 今後の対応候補

- [ ] レートリミット追加 (`slowapi`)
- [ ] push_token をURLパスからヘッダーへ移動
- [ ] 日本人選手の自動同期 (MLB Stats API から取得)
- [ ] 対象イベント拡充 (ヒット、打点、勝利、セーブ)
- [ ] 本番デプロイ (Oracle Cloud / AWS EC2 + Docker)
- [ ] WebSocket化 (有料APIリアルタイムストリーム対応時)
