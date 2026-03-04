# MLB日本人選手通知アプリ

MLBに所属する日本人選手のイベント（ホームラン・奪三振）を検知し、Expo Push通知を送るフルスタックアプリです。

- Backend: FastAPI + APScheduler + PostgreSQL + Redis
- Frontend: Expo (React Native + TypeScript)
- Deploy: Railway（Dockerfile運用）

## 1. システム全体像

```text
MLB Stats API
  ↓
FastAPI バックエンド
  - スケジューラーが試合状況に応じてポーリング間隔を自動調整
  - イベント検知 + 重複防止
  - ユーザー設定に基づいて通知対象を絞り込み
  ↓
Expo Push API
  ↓
iOS / Android アプリ
```

## 2. 現在の主要機能

- 日本人選手一覧の配信
- Push Token 登録
- ユーザー設定取得（未登録なら自動作成）
- 選手ごとの購読ON/OFF
- 選手ごとのイベントON/OFF（ホームラン/奪三振）
- MLB APIポーリング（状態に応じて自動間隔変更）
- Redisでイベント重複通知防止
- テスト通知API（`DEBUG=true` または `ENABLE_TEST_ENDPOINTS=true` 時のみ）

## 3. ディレクトリ構成

```text
MLB APP/
├── Dockerfile                    # Railway本番用（backendをビルド）
├── docker-compose.yml            # ローカルRedis
├── backend/
│   ├── Dockerfile                # backend単体Docker起動用
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── tests/
│   └── app/
│       ├── main.py               # FastAPI起動・lifespan
│       ├── config.py             # 環境変数定義
│       ├── database.py           # PostgreSQL/SQLite SQLAlchemy初期化
│       ├── redis_client.py       # Redis接続
│       ├── api/v1/               # APIルーティング
│       ├── constants/            # 選手マスタ
│       ├── models/               # DBモデル
│       ├── schemas/              # Pydanticスキーマ
│       └── services/             # MLB取得・検知・通知・スケジューラ
├── frontend/
│   ├── app/                      # 画面（Expo Router）
│   ├── components/               # UIコンポーネント
│   ├── hooks/                    # 状態取得・更新ロジック
│   ├── lib/                      # API/通知/ストレージ
│   └── types/
├── SPEC.md
└── RESEARCH.md
```

## 4. バックエンド起動（ローカル）

### 前提

- Python 3.11+
- Docker / Docker Compose

### 手順

```bash
# 1) Redis起動
cd /Users/macow/personal-projects/MLB\ APP
docker compose up -d redis

# 2) backend依存インストール
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) backend環境変数
cp ../.env.example .env

# 4) API起動
uvicorn app.main:app --reload --port 8001
```

## 5. フロントエンド起動（ローカル）

```bash
cd /Users/macow/personal-projects/MLB\ APP/frontend
npm install
cp .env.example .env
npx expo start
```

`.env` の最低設定:

```env
EXPO_PUBLIC_API_BASE_URL=http://localhost:8001
EXPO_PUBLIC_EAS_PROJECT_ID=<your eas project id>
```

## 6. 環境変数

### backend

| 変数 | デフォルト | 説明 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis接続先 |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:YOUR_PASSWORD@postgres-production-97d8.up.railway.app:5432/railway` | DB接続URL（本番はPostgreSQL推奨） |
| `MLB_API_BASE_URL` | `https://statsapi.mlb.com/api` | MLB APIベースURL |
| `DEBUG` | `false` | `true` で `/docs` と `/openapi.json` 有効 |
| `ENABLE_TEST_ENDPOINTS` | `false` | 本番でも `/api/v1/test/*` を有効化 |
| `GAME_TYPE` | `S` | MLB gameType（`S`,`R`,`P` など） |
| `POLL_LIVE_SECONDS` | `20` | LIVE時ポーリング間隔 |
| `POLL_PREGAME_SECONDS` | `60` | 試合直前間隔 |
| `POLL_POST_GAME_SECONDS` | `120` | 試合終了直後間隔 |
| `POLL_POST_GAME_COUNT` | `3` | 終了直後の追加ポーリング回数 |
| `POLL_IDLE_MINUTES` | `30` | 通常待機間隔 |
| `POLL_IDLE_NIGHT_HOURS` | `1` | ET深夜帯待機間隔 |
| `PREGAME_WINDOW_MINUTES` | `15` | 試合直前判定窓 |

補足: ルートの `.env.example` にある `POLL_INTERVAL_SECONDS` は旧名で、現行のアダプティブポーリングでは未使用です。

### frontend

| 変数 | 説明 |
|---|---|
| `EXPO_PUBLIC_API_BASE_URL` | バックエンドURL |
| `EXPO_PUBLIC_EAS_PROJECT_ID` | Expo Push Token取得に必要なProject ID |

## 7. API一覧

| Method | Path | 説明 |
|---|---|---|
| `GET` | `/api/v1/health` | ヘルスチェック |
| `GET` | `/api/v1/players` | 対象日本人選手一覧 |
| `POST` | `/api/v1/users/register` | PushToken登録（冪等） |
| `GET` | `/api/v1/preferences/{push_token}` | 設定取得（未登録なら自動作成） |
| `PUT` | `/api/v1/preferences/{push_token}/players` | 選手購読更新 |
| `PUT` | `/api/v1/preferences/{push_token}/events` | 旧互換イベント設定更新 |
| `PUT` | `/api/v1/preferences/{push_token}/player-events` | 選手別イベント設定更新 |
| `POST` | `/api/v1/test/send-notification` | テスト通知（条件付き） |
| `POST` | `/api/v1/test/send-demo-notification` | デモ通知（条件付き） |

注意:

- `push_token` は URL エンコードが必要です。
- `/docs` は `DEBUG=true` の時のみ表示されます。

## 8. ポーリングロジック（現行）

スケジューラーは単純固定間隔ではなく、試合状態で自動調整します。

- `LIVE`: 20秒
- `PREGAME`（開始15分前まで）: 60秒
- `POST_GAME`: 120秒（最大3回）
- `IDLE`: 30分（ET深夜帯は1時間）

内部では `DateTrigger` の単発ジョブを毎回 upsert する方式で再スケジュールしています。

## 9. デプロイ（Railway）

現在は root の `Dockerfile` を使う運用です。

推奨設定:

1. Builder: `Dockerfile`
2. Root Directory: リポジトリルート
3. 必須環境変数: `REDIS_URL`（Railway Redis を指定）
4. 任意: `ENABLE_TEST_ENDPOINTS=true`（テスト通知エンドポイントを使う時だけ）

## 10. テスト

```bash
cd backend
pytest
```

現在は主に `scheduler` のロジックテストを実装しています。

## 11. よくあるハマりどころ

- `404 /docs`: `DEBUG=false` なら正常。
- `404 /api/v1/test/...`: `DEBUG` も `ENABLE_TEST_ENDPOINTS` も `false` なら正常。
- `500 users/register`（UNIQUE制約）: 同時登録競合。現コードでは競合吸収済み。
- Expo本番通知は Expo Go では確認不可。開発ビルドまたは本番ビルドが必要。

## 12. 追加ドキュメント

- 詳細調査メモ: `RESEARCH.md`
- 初期仕様: `SPEC.md`
- 非エンジニア向け解説: `PROJECT_EXPLAINED_FOR_NON_ENGINEERS.md`

## 13. TestFlighリリース後の対応

### ① コードを修正したときの流れ（TestFlight更新）

基本は 同じ流れをもう一度やるだけです。

全体図

コード修正
↓
git commit / push
↓
eas build
↓
eas submit
↓
Apple processing
↓
TestFlightに新バージョン

⸻

実際のコマンド

1️⃣ コード修正

例

git add .
git commit -m "fix: push notification bug"
git push

※これは必須ではないですが、履歴管理のためにおすすめ。

⸻

2️⃣ バージョンを上げる（重要）

iOSは同じバージョンはアップロードできません。

app.json または app.config.ts

{
  "expo": {
    "version": "1.0.1"
  }
}

または

npx expo version:patch

⸻

3️⃣ ビルド

eas build -p ios

これで

React Native code
↓
Xcode build
↓
.ipa

が作られます。

⸻

4️⃣ Appleへ送信

eas submit -p ios

⸻

5️⃣ Apple processing

5〜15分

⸻

6️⃣ TestFlight

TestFlightに

version 1.0.1

が追加されます。
