# MLB日本人選手通知アプリ

MLBに所属する日本人選手のホームラン・奪三振を15〜30秒以内に検知し、Expo Push通知を送信するフルスタックアプリ。

---

## アーキテクチャ

```
MLB Stats API (20秒ごとポーリング)
        ↓
FastAPI バックエンド (APScheduler)
        ↓
イベント検知 (ホームラン / 奪三振)
        ↓
Redis (重複防止)
        ↓
Expo Push API
        ↓
Expo React Native アプリ (iOS / Android)
```

---

## 技術スタック

### バックエンド

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

### フロントエンド (Expo React Native)

| 項目 | 内容 |
|------|------|
| フレームワーク | Expo SDK 54 (Managed Workflow) |
| 言語 | TypeScript |
| ルーティング | Expo Router v6 |
| UI | React Native (素のコンポーネント) |
| 通知 | expo-notifications |
| ストレージ | expo-secure-store (push_token 永続化) |
| HTTP クライアント | fetch API |
| パッケージ管理 | npm |

---

## ディレクトリ構成

```
MLB APP/
├── docker-compose.yml        # Redis
├── .env                      # 環境変数 (gitignore済み)
├── .env.example
├── backend/
│   ├── pyproject.toml        # 依存パッケージ (uv管理)
│   ├── Dockerfile
│   └── app/
│       ├── main.py           # FastAPI app + lifespan
│       ├── config.py         # 環境変数管理 (pydantic-settings)
│       ├── database.py       # SQLAlchemy async engine
│       ├── redis_client.py   # Redis接続管理
│       ├── models/
│       │   └── user.py       # users / user_players / user_event_prefs
│       ├── schemas/
│       │   └── user.py       # Pydantic リクエスト/レスポンス
│       ├── constants/
│       │   └── japanese_players.py  # 日本人選手マスタ
│       ├── api/v1/
│       │   ├── router.py
│       │   ├── users.py      # 登録・設定エンドポイント
│       │   └── players.py    # 選手一覧エンドポイント
│       └── services/
│           ├── mlb_api.py        # MLB Stats API クライアント
│           ├── event_detector.py # イベント検知 + Redis重複チェック
│           ├── notification.py   # Expo Push送信
│           └── scheduler.py      # APScheduler (20秒間隔)
└── frontend/
    ├── app.json              # Expo設定 (スキーム・権限・プラグイン)
    ├── .env.example          # 環境変数テンプレート
    ├── app/
    │   ├── _layout.tsx       # ルートレイアウト (トークン判定・通知ハンドラー)
    │   ├── index.tsx         # エントリポイント (リダイレクト)
    │   ├── onboarding.tsx    # 通知許可取得・初回登録画面
    │   └── (tabs)/
    │       ├── _layout.tsx   # タブナビゲーター
    │       ├── index.tsx     # ホーム画面 (フォロー選手・設定サマリー)
    │       └── settings.tsx  # 設定画面 (選手・イベントON/OFF)
    ├── components/
    │   ├── PlayerCard.tsx    # 選手カード (サブスクリプション表示・トグル)
    │   └── EventToggle.tsx   # イベント通知設定トグル
    ├── lib/
    │   ├── api.ts            # バックエンドAPIクライアント
    │   ├── storage.ts        # SecureStore wrapper
    │   └── notifications.ts  # Expo push token取得・ハンドラー設定
    ├── hooks/
    │   ├── usePushToken.ts   # SecureStore からトークンを読むフック
    │   └── usePreferences.ts # 選手・設定の取得・更新フック
    ├── types/
    │   └── api.ts            # TypeScript 型定義
    └── constants/
        └── colors.ts         # カラーパレット (野球ダークテーマ)
```

---

## セットアップ

### 前提条件
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) インストール済み
- Docker / Docker Compose
- Node.js 18+ / npm
- iOS / Android 実機 (push通知のテストに必要)

> **注意:** Expo SDK 53 以降、`expo-notifications` のリモートプッシュ通知は **Expo Go では動作しません**。
> UI の確認は Expo Go で可能ですが、push 通知のテストには EAS Build による開発ビルドが必要です。

### バックエンド起動

```bash
# 1. Redisを起動
docker compose up -d redis

# 2. プロジェクトへ移動して依存を同期
cd backend
uv sync

# 3. 環境変数を設定 (backend/.env を読む)
cp ../.env.example .env
# .env を必要に応じて編集

# 4. サーバーを起動 (uv経由で仮想環境の実行ファイルを使う)
uv run uvicorn app.main:app --reload --port 8001
```

起動ログに `Scheduler started (interval=20s)` が出ていれば正常。

### フロントエンド起動

```bash
cd frontend

# 1. 環境変数を設定
cp .env.example .env
# EXPO_PUBLIC_API_BASE_URL をバックエンドのURLに合わせて編集

# 2. 開発サーバーを起動
npx expo start
```

> **push通知をテストするには開発ビルドが必要です。**
> Expo SDK 53 以降、`expo-notifications` のリモートプッシュ通知は Expo Go から削除されました。
>
> ```bash
> # EAS CLI のインストール (初回のみ)
> npm install -g eas-cli
> eas login
>
> # 開発ビルドを実機にインストール
> eas build --profile development --platform ios   # iOS
> eas build --profile development --platform android  # Android
> ```
>
> UI の確認のみであれば Expo Go (`i` / `a` キー) で動作します。

---

## 環境変数

### バックエンド (`backend/.env`)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 接続URL |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/mlb_app.db` | SQLite DB パス |
| `POLL_INTERVAL_SECONDS` | `20` | MLB APIポーリング間隔(秒) |
| `MLB_API_BASE_URL` | `https://statsapi.mlb.com/api` | MLB Stats API ベースURL |
| `DEBUG` | `false` | trueにすると `/docs` が有効・SQLログ出力 |

### フロントエンド (`frontend/.env`)

| 変数名 | デフォルト | 説明 |
|--------|-----------|------|
| `EXPO_PUBLIC_API_BASE_URL` | `http://localhost:8001` | バックエンド API のベースURL |

> **注意:** `EXPO_PUBLIC_` プレフィックスの変数はビルド時にバンドルへ埋め込まれ、クライアントに公開される。機密情報は絶対に設定しないこと。本番環境では必ず `https://` を使用すること。

---

## API エンドポイント

| Method | Path | 説明 |
|--------|------|---------|
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
|--------|-----------|------------|--------|
| 大谷翔平 | 660271 | 投手/野手 | LAD |
| 吉田正尚 | 807799 | 野手 | BOS |
| 鈴木誠也 | 673548 | 野手 | CHC |
| 今永昇太 | 684007 | 投手 | CHC |
| 菊池雄星 | 579328 | 投手 | LAA |
| ダルビッシュ有 | 506433 | 投手 | SD |
| 千賀滉大 | 673540 | 投手 | NYM |
| 山本由伸 | 808967 | 投手 | LAD |
| 佐々木朗希 | 808963 | 投手 | LAD |
| 松井裕樹 | 673513 | 投手 | SD |
| 小笠原慎之介 | 829272 | 投手 | WSH |
| 菅野智之 | 608372 | 投手 | BAL |
| 村上宗隆 | 808959 | 野手 | CWS |
| 岡本和真 | 672960 | 野手 | TOR |

選手追加は `backend/app/constants/japanese_players.py` を編集。

---

## イベント検知ロジック

```text
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

## 画面構成 (フロントエンド)

| 画面 | 表示条件 | 内容 |
| --- | --- | --- |
| オンボーディング | 初回起動 (push_token 未保存) | 通知許可取得・バックエンド登録 |
| ホーム | push_token 保存済み | フォロー中選手一覧・通知設定サマリー |
| 設定 | push_token 保存済み | 選手ごとのON/OFF・ホームラン/奪三振のON/OFF |

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

### バックエンド TODO

- [ ] レートリミット追加 (`slowapi`)
- [ ] push_token をURLパスからヘッダーへ移動
- [ ] 日本人選手の自動同期 (MLB Stats API から取得)
- [ ] 対象イベント拡充 (ヒット、打点、勝利、セーブ)
- [ ] Expo Push Token の無効化検知 (`DeviceNotRegistered` ハンドリング)
- [ ] 本番デプロイ (Oracle Cloud / AWS EC2 + Docker)
- [ ] WebSocket化 (有料APIリアルタイムストリーム対応時)

### フロントエンド TODO

- [ ] EAS Build での実機ビルド・push通知の E2E テスト
- [ ] 通知タップ時の詳細画面遷移 (deep link + `data` フィールド活用)
- [ ] プルリフレッシュの楽観的更新 (連続トグルのレースコンディション解消)
- [ ] 通知履歴画面 (過去に受け取った通知の一覧)
- [ ] 多言語対応 (英語)
