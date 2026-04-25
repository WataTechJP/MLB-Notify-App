# RESEARCH.md — MLB通知アプリ 内部設計・ロジック詳細

実装を続ける上で参照すべき、アプリの構造・ロジック・動作の詳細ドキュメント。

---

## 目次

### バックエンド (FastAPI)
1. [アプリ全体の起動フロー](#1-アプリ全体の起動フロー)
2. [ポーリングサイクルの詳細](#2-ポーリングサイクルの詳細)
3. [MLB Stats API の構造](#3-mlb-stats-api-の構造)
4. [イベント検知ロジック](#4-イベント検知ロジック)
5. [重複防止メカニズム (Redis)](#5-重複防止メカニズム-redis)
6. [通知送信フロー (Expo Push)](#6-通知送信フロー-expo-push)
7. [DB設計と各テーブルの役割](#7-db設計と各テーブルの役割)
8. [ユーザー管理フロー](#8-ユーザー管理フロー)
9. [モジュール依存関係](#9-モジュール依存関係)
10. [非同期処理の設計方針](#10-非同期処理の設計方針)
11. [選手マスタの設計](#11-選手マスタの設計)
12. [拡張時の注意点・落とし穴](#12-拡張時の注意点落とし穴)

### フロントエンド (Expo React Native)
13. [フロントエンド全体の起動フロー](#13-フロントエンド全体の起動フロー)
14. [画面遷移ロジック](#14-画面遷移ロジック)
15. [Push Token 取得・登録フロー](#15-push-token-取得登録フロー)
16. [APIクライアントの設計](#16-apiクライアントの設計)
17. [状態管理・カスタムフック](#17-状態管理カスタムフック)
18. [フロントエンド モジュール依存関係](#18-フロントエンド-モジュール依存関係)
19. [フロントエンド 拡張時の注意点・落とし穴](#19-フロントエンド-拡張時の注意点落とし穴)

---

## 1. アプリ全体の起動フロー

```
uvicorn app.main:app
    │
    └─ FastAPI lifespan (asynccontextmanager)
         │
         ├─ [startup]
         │   ├─ create_tables()        ← SQLiteにテーブルがなければ作成
         │   └─ start_scheduler()      ← APScheduler + httpx.AsyncClient を初期化
         │
         ├─ [running]
         │   ├─ API リクエスト処理 (通常のFastAPIルーティング)
         │   └─ scheduler._poll_job() が20秒ごとに非同期実行
         │
         └─ [shutdown]
             ├─ stop_scheduler()       ← scheduler停止 + httpx.AsyncClient.aclose()
             └─ close_redis()          ← Redis接続をクローズ
```

### 重要ポイント
- `start_scheduler()` は **同期関数** (APSchedulerのAPIがsync)。内部で登録するジョブ `_poll_job` は async関数で問題なし。
- `httpx.AsyncClient` はアプリ全体で1インスタンスを使い回す（接続プールの効率化）。
- `create_tables()` は `Base.metadata.create_all` を使用するため、**テーブルが既存の場合は何もしない**（マイグレーションではない）。スキーマ変更が必要な場合は別途対応が必要。

---

## 2. ポーリングサイクルの詳細

20秒ごとに以下が実行される。

```
_poll_job()                         ← APSchedulerが呼び出す
    │
    ├─ get_redis()                  ← Redisシングルトンを取得
    ├─ AsyncSessionLocal()          ← DBセッションをcontextmanagerで開く
    └─ detect_events(redis, db, http_client)
         │
         ├─ get_todays_games()      ← 今日の試合一覧 (gamePk[])
         │   └─ 試合なし → 早期リターン
         │
         ├─ asyncio.gather(          ← 複数試合のライブフィードを並列取得
         │   get_live_feed(gamePk1),
         │   get_live_feed(gamePk2),
         │   ...
         │  return_exceptions=True   ← 1試合失敗しても他は継続
         │  )
         │
         └─ [各試合について]
              ├─ is_live_game()     ← "Live" でなければスキップ
              ├─ extract_plays()    ← allPlays[] を取得
              └─ [各プレイについて]
                   └─ _process_play()  ← イベント検知・通知
```

### タイムアウト設定
| リクエスト先 | タイムアウト |
|------------|------------|
| MLB Schedule API | 10秒 |
| MLB Live Feed API | 10秒 |
| Expo Push API | 15秒 |
| httpx.AsyncClient グローバル | 30秒 (connect: 5秒) |

### APScheduler の `max_instances=1`
同一ジョブが前の実行中に再度トリガーされることを防ぐ。ポーリング処理が20秒を超えた場合でも2重実行しない。

---

## 3. MLB Stats API の構造

### エンドポイント

```
# 今日の試合一覧
GET https://statsapi.mlb.com/api/v1/schedule
    ?sportId=1
    &date=2025-04-15       ← YYYY-MM-DD
    &gameType=R            ← R=レギュラーシーズン, S=Spring Training, P=ポストシーズン

# ライブフィード
GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live
    ?fields=...            ← 取得フィールドを絞り込む (軽量化)
```

### Schedule レスポンス構造
```json
{
  "dates": [
    {
      "date": "2025-04-15",
      "games": [
        {
          "gamePk": 745804,
          "gameType": "R",
          "status": { "abstractGameState": "Live" }
        }
      ]
    }
  ]
}
```

### Live Feed レスポンス構造 (fieldsで絞り込み後)
```json
{
  "gameData": {
    "status": {
      "abstractGameState": "Live"   ← "Preview" | "Live" | "Final"
    }
  },
  "liveData": {
    "plays": {
      "allPlays": [
        {
          "result": {
            "event": "Home Run",    ← "Home Run" | "Strikeout" | "Single" など
            "eventType": "home_run"
          },
          "about": {
            "atBatIndex": 42,       ← 試合内の打席番号 (0始まり、単調増加)
            "isComplete": true      ← falseの場合は進行中の打席 = スキップ
          },
          "matchup": {
            "batter": { "id": 660271 },   ← 打者のMLB player_id
            "pitcher": { "id": 681936 }   ← 投手のMLB player_id
          }
        }
      ]
    }
  }
}
```

### `abstractGameState` の値
| 値 | 意味 | 処理 |
|----|------|------|
| `"Preview"` | 試合前 | スキップ |
| `"Live"` | 試合中 | 処理対象 |
| `"Final"` | 試合終了 | スキップ |

### `fields` パラメータ (LIVE_FEED_FIELDS)
現在の設定:
```
gameData,status,abstractGameState,
liveData,plays,allPlays,
result,event,eventType,
about,atBatIndex,isComplete,
matchup,batter,id,pitcher,id
```
フィールドを絞ることでレスポンスサイズを大幅削減。新しいフィールドが必要になったら追記する。

---

## 4. イベント検知ロジック

### `_process_play()` の判定フロー

```python
play = {result, about, matchup}

# Step 1: イベント種別チェック
event_name = result["event"]           # "Home Run" or "Strikeout"
event_type = EVENT_MAP.get(event_name) # "home_run" or "strikeout" or None
if not event_type: return              # 対象外イベントは即スキップ

# Step 2: 打席完了チェック
if not about["isComplete"]: return     # 進行中打席はスキップ

# Step 3: 日本人選手チェック
if event_type == "home_run":
    player_id = batter_id if batter_id in BATTER_IDS else None
elif event_type == "strikeout":
    player_id = pitcher_id if pitcher_id in PITCHER_IDS else None
if not player_id: return

# Step 4: Redis重複チェック
last_index = redis.get(f"last_event:{player_id}:{game_pk}")
if at_bat_index <= last_index: return  # 既知のイベント

# Step 5: 新規イベント → 通知
redis.set(key, at_bat_index, ex=86400)
tokens = db.query(購読中ユーザーのpush_token)
asyncio.create_task(send_notifications(tokens))
```

### EVENT_MAP (拡張ポイント)
```python
EVENT_MAP = {
    "Home Run": "home_run",
    "Strikeout": "strikeout",
    # 将来追加候補:
    # "Single": "single",
    # "Double": "double",
    # "Triple": "triple",
    # "Walk": "walk",
}
```
MLB Stats APIの `result.event` の文字列と内部イベントタイプのマッピング。
新イベントを追加する場合はここに追記し、`user_event_prefs` の `event_type` 列挙値も合わせて拡張する。

### 大谷翔平 (two_way) の扱い
`position="two_way"` の選手は `BATTER_IDS` と `PITCHER_IDS` 両方に含まれる。
- 打席でホームラン → `batter_id` で検知 → `home_run` 通知
- 登板で奪三振 → `pitcher_id` で検知 → `strikeout` 通知

---

## 5. 重複防止メカニズム (Redis)

### キー設計
```
key:   "last_event:{player_id}:{game_pk}"
value: {atBatIndex}  (整数文字列)
TTL:   86400秒 (24時間)
```

### なぜ `atBatIndex` を使うか
- `allPlays` は試合の全打席履歴が累積で入っている
- 20秒ごとにポーリングするたびに同じ打席が繰り返し現れる
- `atBatIndex` は試合内で単調増加するため「既に処理済みか」の判定に使える
- 「最後に処理した atBatIndex」を Redis に持っておき、それ以下なら無視する

### TTL が24時間な理由
- 1試合は最大でも5〜6時間程度
- 翌日同じ選手が別の試合 (別の `game_pk`) でイベントを起こした場合は別キーになるため問題なし
- `{player_id}:{game_pk}` の組み合わせでユニークになっている

### Redis が落ちた場合
`redis_client.py` の `get_redis()` がエラーを投げ、`_poll_job()` の `except` でキャッチされ、そのポーリングサイクルがスキップされる。
**重複通知が発生するリスク**: Redis再起動後の最初のポーリングで、既に送信済みのイベントを「新規」と判定してしまう可能性がある。
→ 将来的には DB側に `sent_events` テーブルを持つことで Redis 依存を減らせる。

---

## 6. 通知送信フロー (Expo Push)

### Expo Push API の仕様
```
POST https://exp.host/--/api/v2/push/send
Content-Type: application/json

# リクエスト (配列で最大100件)
[
  {
    "to": "ExponentPushToken[xxx]",
    "title": "⚾ 大谷翔平 ホームラン！",
    "body": "大谷翔平 がホームランを打ちました！",
    "data": {},          ← クライアントアプリで受け取れるカスタムデータ
    "sound": "default"   ← 通知音
  }
]
```

### チャンク送信 (100件単位)
Expo Push APIの推奨上限が100件/リクエスト。`send_notifications()` が自動でチャンク分割する。
1000ユーザーなら10リクエストが順次送信される（現在は `for chunk in _chunk` でシリアル）。
→ 将来 `asyncio.gather` で並列化可能。

### `asyncio.create_task` で非同期実行する理由
通知送信は検知ロジックとは独立した処理。送信に時間がかかっても次のポーリングサイクルをブロックしないよう、fire-and-forget で実行する。
エラーは `task.add_done_callback(_handle_notification_task_error)` でログに記録される。

### `data` フィールドの活用 (将来)
クライアント側で通知タップ時の画面遷移などに使える。例:
```python
data={"player_id": player_id, "event_type": event_type, "game_pk": game_pk}
```

---

## 7. DB設計と各テーブルの役割

### ER図
```
users (1)
  ├── (N) user_players      ← ユーザーが購読している選手
  └── (N) user_event_prefs  ← ユーザーのイベント種別ごとのON/OFF
```

### users テーブル
```sql
id               INTEGER  PK, autoincrement
expo_push_token  TEXT     UNIQUE, NOT NULL, INDEX
                          ← アプリの識別子。端末再インストールで変わりうる
is_active        BOOLEAN  DEFAULT TRUE
                          ← 将来の論理削除 or 通知停止フラグ
created_at       DATETIME server_default=now()
updated_at       DATETIME onupdate=now()
```

**expo_push_token について**: Expo は端末・アプリの組み合わせごとにトークンを発行する。アプリ再インストールで変わる可能性があるため、`/register` を毎回アプリ起動時に呼ぶ設計が推奨される。

### user_players テーブル
```sql
id         INTEGER  PK
user_id    INTEGER  FK→users.id (CASCADE DELETE)
player_id  INTEGER  ← constants/japanese_players.py の id を参照 (外部テーブルなし)
UNIQUE(user_id, player_id)
```

`player_id` は外部テーブルを持たず、constants から参照する設計。
理由: 選手マスタは頻繁に変わらず、コードに持つ方が管理が簡単なため。

### user_event_prefs テーブル
```sql
id         INTEGER  PK
user_id    INTEGER  FK→users.id (CASCADE DELETE)
event_type TEXT     ← "home_run" | "strikeout" (将来拡張可能)
is_enabled BOOLEAN  DEFAULT TRUE
UNIQUE(user_id, event_type)
```

新しいイベントタイプを追加した場合、**既存ユーザーのレコードは自動生成されない**。
`update_event_prefs()` で upsert しているため、既存ユーザーへのバックフィルが必要になる場合がある。

### マイグレーション方針
現在は `Base.metadata.create_all` のみ (新規テーブルのみ作成)。
スキーマ変更 (カラム追加・変更) が必要になったら Alembic の導入を検討する。
```bash
uv add alembic
alembic init alembic
```

---

## 8. ユーザー管理フロー

### 登録時のデフォルト設定
`POST /api/v1/users/register` で新規ユーザーが登録されると、自動で:
- **全選手を購読** (`user_players` に PLAYER_MAP の全 player_id を挿入)
- **全イベントをON** (`user_event_prefs` に home_run=true, strikeout=true を挿入)

既存トークンで再登録した場合は `is_active = True` に更新するだけ (設定は変更しない)。

### 通知対象ユーザーのクエリ
```sql
-- _get_target_users() が実行するSQLのイメージ
SELECT u.expo_push_token
FROM users u
JOIN user_players up ON up.user_id = u.id
JOIN user_event_prefs uep ON uep.user_id = u.id AND uep.event_type = :event_type
WHERE up.player_id = :player_id
  AND uep.is_enabled = TRUE
  AND u.is_active = TRUE
```

3テーブルのJOINになっているが、ユーザー数1,000人程度ではインデックスで十分高速。

---

## 9. モジュール依存関係

```
main.py
  ├── config.py           ← 全モジュールが参照
  ├── database.py         ← get_db(), create_tables()
  ├── redis_client.py     ← get_redis(), close_redis()
  ├── api/v1/router.py
  │   ├── api/v1/users.py
  │   │   ├── models/user.py
  │   │   ├── schemas/user.py
  │   │   └── constants/japanese_players.py
  │   └── api/v1/players.py
  │       └── constants/japanese_players.py
  └── services/scheduler.py
      └── services/event_detector.py
          ├── services/mlb_api.py
          ├── services/notification.py
          ├── constants/japanese_players.py
          └── models/user.py (型参照)
```

**循環インポートの注意点**: `create_tables()` 内で `from app.models import user` を遅延インポートしている。これは `database.py` → `models/user.py` → `database.py` の循環を避けるため。

---

## 10. 非同期処理の設計方針

### イベントループの共有
FastAPI + uvicorn が管理するイベントループを APScheduler のジョブも共有している。
`AsyncIOScheduler` を使うことで、ジョブ内で `await` が使える。

### DB セッションのスコープ
ポーリングジョブごとに `async with AsyncSessionLocal() as db:` で新しいセッションを作成・破棄する。
APIエンドポイントは `Depends(get_db)` でリクエストごとのセッション。
セッションを長時間保持しないことで SQLite の競合を防いでいる。

### Redis 接続のスコープ
`get_redis()` はモジュールグローバルなシングルトンを返す。
接続プールは redis-py が管理するため、毎回接続のオーバーヘッドなし。

### `asyncio.create_task` のライフサイクル
`asyncio.create_task(send_notifications(...))` で作成されたタスクは、イベントループが生きている限り実行される。
**注意**: サーバーシャットダウン時に未完了のタスクが破棄される可能性がある。
完全性が求められる場合はキュー (Redis Queue / Celery) の導入を検討する。

---

## 11. 選手マスタの設計

### PlayerInfo データクラス
```python
@dataclass(frozen=True)
class PlayerInfo:
    id: int        ← MLB Stats API の player_id (変わらない)
    name_ja: str   ← 日本語名
    name_en: str   ← 英語名
    position: str  ← "batter" | "pitcher" | "two_way"
    team: str      ← 球団略称 (チーム移籍で変わりうる)
```

### 選手追加手順
1. `backend/app/constants/japanese_players.py` の `JAPANESE_PLAYERS` リストに追加
2. MLB Stats API で player_id を調べる:
   ```
   GET https://statsapi.mlb.com/api/v1/people/search?names={名前}
   ```
3. サーバー再起動で反映される
4. **既存ユーザーへの影響**: 新選手は既存ユーザーの `user_players` に自動追加されない。新規登録ユーザーのみデフォルト購読に含まれる。既存ユーザーへのバックフィルが必要な場合は別途スクリプトが必要。

### 選手のチーム移籍
`team` フィールドは表示用のみで、ロジックには影響しない。
MLB Stats API は player_id でトラッキングするため、チームが変わっても検知は継続して動作する。

---

## 12. 拡張時の注意点・落とし穴

### イベント追加 (例: ヒット、打点)
1. `event_detector.py` の `EVENT_MAP` に追加
2. `user_event_prefs` の `event_type` として使える文字列を増やす
3. `schemas/user.py` の `EventPrefsUpdate` にフィールド追加
4. 通知メッセージ `_build_notification_message()` にケース追加
5. 既存ユーザーの `user_event_prefs` に新 event_type のレコードがないため、バックフィルかデフォルト値のフォールバックが必要

### ヒット・打点の検知について
- **ヒット** (`result.event = "Single" / "Double" / "Triple"`) は打者の検知
- **打点** (`result.rbi`) は `allPlays[n].result.rbi` で取得可能。ただし現在の `LIVE_FEED_FIELDS` にこのフィールドが含まれていないため追加が必要

### Spring Training / ポストシーズン切り替え
`detect_events()` の `game_type` 引数で制御:
```python
# scheduler.py の _poll_job() を修正
await detect_events(redis, db, _http_client, game_type="R")  # レギュラー
await detect_events(redis, db, _http_client, game_type="S")  # Spring Training
await detect_events(redis, db, _http_client, game_type="P")  # ポストシーズン
```
または `.env` から読み込む環境変数にするとコード変更不要になる。

### SQLite の並行書き込み制限
SQLite はデフォルトで複数プロセスからの同時書き込みに弱い。
現在は1プロセスで動作しているので問題ないが、将来複数ワーカー (`--workers 4`) を使う場合は PostgreSQL への移行を検討する。

### 通知のタイムラグ
MLB Stats API 自体のデータ反映ラグ (2〜5秒程度) + ポーリング間隔 (20秒) が最大遅延。
理論上の最大遅延: **約25秒**。目標の30秒以内を満たす。

### Expo Push Token の無効化
ユーザーがアプリをアンインストールすると Expo Push Token が無効になる。
Expo Push API のレスポンスに `"status": "error", "details": {"error": "DeviceNotRegistered"}` が含まれる。
現在この処理は未実装。将来 `notification.py` で無効トークンを検知して `users.is_active = False` にする処理が必要。

### タイムゾーンについて
MLB の試合スケジュール日付は東部時間 (ET) 基準で扱う。
日本時間の朝や UTC 深夜帯では、サーバーのローカル日付を使うと「米国ではまだ前日」の試合を取り逃がす。
そのため `mlb_api.py` では `ZoneInfo("America/New_York")` を使って schedule の `date` と stats の `season` を決めている。

---

---

# フロントエンド (Expo React Native)

---

## 13. フロントエンド全体の起動フロー

```
npx expo start
    │
    └─ expo-router/entry
         │
         └─ app/_layout.tsx  (RootLayout)
              │
              ├─ setupNotificationHandlers()  ← フォアグラウンド通知ハンドラー登録
              │
              └─ getPushToken()               ← SecureStore を確認
                   │
                   ├─ トークンあり  → router.replace("/(tabs)")
                   └─ トークンなし  → router.replace("/onboarding")
```

### 重要ポイント
- `_layout.tsx` は2つの `useEffect` を持つ。1つは通知ハンドラーの登録（マウント時1回）、もう1つはトークン確認によるリダイレクト。
- Expo Router v6 の `Stack` がルートナビゲーターとして機能し、`onboarding` と `(tabs)` の2つのスタックを管理する。
- `app/index.tsx` は保険的なリダイレクト用で、`_layout.tsx` の判定より後に到達した場合のフォールバック。

---

## 14. 画面遷移ロジック

```
起動
  └─ _layout.tsx
       ├─ SecureStore にトークンあり ─────────────────→ (tabs)
       │                                                    ├─ index.tsx  (ホーム)
       │                                                    └─ settings.tsx (設定)
       └─ SecureStore にトークンなし → onboarding.tsx
                                            │
                                     通知許可 + 登録成功
                                            │
                                            └─ router.replace("/(tabs)")
```

### 各画面の責務

| 画面 | パス | 責務 |
|------|------|------|
| ルートレイアウト | `app/_layout.tsx` | 初期ルーティング判定・通知ハンドラー設定 |
| オンボーディング | `app/onboarding.tsx` | 通知許可取得・push_token 登録・SecureStore 保存 |
| ホーム | `app/(tabs)/index.tsx` | フォロー選手と通知設定のサマリー表示 |
| 設定 | `app/(tabs)/settings.tsx` | 選手・イベント種別ごとのトグル（即時API反映） |

### タブナビゲーター (`(tabs)/_layout.tsx`)
- Expo Router の `Tabs` コンポーネントを使用。
- ホームタブ（⚾）と設定タブ（⚙️）の2タブ構成。
- `tabBarStyle.backgroundColor` に `Colors.tabBar` を適用し、ダーク配色に統一。

---

## 15. Push Token 取得・登録フロー

```
onboarding.tsx
  │
  └─ handleAllow()
       │
       ├─ requestAndGetToken()          ← lib/notifications.ts
       │   ├─ Android: setNotificationChannelAsync("default")
       │   ├─ getPermissionsAsync()
       │   ├─ 未許可なら requestPermissionsAsync()
       │   ├─ 許可されなかった → Error をthrow
       │   └─ getExpoPushTokenAsync({ projectId? })
       │        └─ "ExponentPushToken[xxx]" を返す
       │
       ├─ registerUser(token)           ← lib/api.ts → POST /api/v1/users/register
       │   └─ バックエンドで users + user_players + user_event_prefs を初期作成
       │
       ├─ savePushToken(token)          ← lib/storage.ts → SecureStore.setItemAsync
       │
       └─ router.replace("/(tabs)")
```

### `getExpoPushTokenAsync` の `projectId` について
- Expo Go で開発中は `Constants.expoConfig.extra.eas.projectId` が未設定のため `undefined` を渡す（Expo Go が自動処理）。
- EAS Build でビルドした本番バイナリでは `projectId` が必要になるため、`eas.json` と `app.json` の `extra.eas.projectId` の設定が必要。

### 通知ハンドラーの設定 (`notifications.ts`)
```typescript
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});
```
これはモジュールトップレベルで実行されるため、`import` 時に自動的に設定される。

---

## 16. APIクライアントの設計

### ベースURL
```typescript
const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
```
- `EXPO_PUBLIC_` プレフィックスにより、Expo のビルド時にバンドルへインライン展開される。
- **本番では必ず `https://` を使うこと**。`__DEV__ === false` の場合に `http://` だと `console.error` で警告が出るよう実装済み。

### push_token のURLエンコード
```typescript
function encodedToken(token: string): string {
  return encodeURIComponent(token);
}
// "ExponentPushToken[xxx]" → "ExponentPushToken%5Bxxx%5D"
```
`[` `]` はURLとして不正な文字のためエンコード必須。`encodeURIComponent` でエスケープしている。

### エラーハンドリング方針
```typescript
// ネットワーク障害 (fetch自体が失敗)
throw new Error("サーバーに接続できませんでした。ネットワーク接続を確認してください。");

// HTTPエラー (4xx / 5xx)
throw new Error(`通信エラーが発生しました (${res.status})`);
// DEV環境のみ console.error でバックエンドの生レスポンスを出力
```
バックエンドの内部情報（スタックトレース等）がユーザーに見えないよう、エラーメッセージはサニタイズ済み。

### API 関数一覧

| 関数 | HTTP | パス |
|------|------|------|
| `registerUser(token)` | POST | `/api/v1/users/register` |
| `getPlayers()` | GET | `/api/v1/players` |
| `getPreferences(token)` | GET | `/api/v1/preferences/{token}` |
| `updatePlayers(token, ids)` | PUT | `/api/v1/preferences/{token}/players` |
| `updateEvents(token, prefs)` | PUT | `/api/v1/preferences/{token}/events` |

---

## 17. 状態管理・カスタムフック

### `usePushToken` (`hooks/usePushToken.ts`)

```typescript
// 返り値
{ token: string | null, isLoading: boolean, setToken: Dispatch }
```

- マウント時に `SecureStore.getItemAsync` で push_token を1回読み込む。
- `isLoading: true` の間はリダイレクト判定を保留できる。
- `setToken` を onboarding から呼ぶことで、登録後にトークンをstateへ反映させる（ただし現在はリダイレクトで画面を切り替えるため直接使用は少ない）。

### `usePreferences` (`hooks/usePreferences.ts`)

```typescript
// 返り値
{
  players: Player[],
  preferences: UserPreferences | null,
  isLoading: boolean,
  error: string | null,
  togglePlayer: (playerId: number) => Promise<void>,
  toggleEvent: (key: "home_run" | "strikeout", value: boolean) => Promise<void>,
  refresh: () => Promise<void>,
}
```

**初回ロード:**
```
useEffect → load()
  └─ Promise.all([getPlayers(), getPreferences(token)])
       ├─ setPlayers(p)
       └─ setPreferences(prefs)
```

**選手トグル (`togglePlayer`):**
```
現在の player_ids からtoggle（含む→除く、含まない→追加）
  └─ updatePlayers(token, next)  → setPreferences(updated)
```

**イベントトグル (`toggleEvent`):**
```
event_prefs の該当キーをtoggle
  └─ updateEvents(token, next)  → setPreferences(updated)
```

**注意点:** `togglePlayer` / `toggleEvent` は連続呼び出し時にレースコンディションが発生しうる（楽観的更新なし + API レスポンスで state を上書き）。MVP段階では許容。将来は楽観的更新か debounce + キャンセルを導入する。

### データフロー図

```
SecureStore
    │ getPushToken()
    ▼
usePushToken
    │ token
    ▼
usePreferences(token)
    ├─ GET /api/v1/players        → players[]
    └─ GET /api/v1/preferences/.. → preferences
              │
              ├─ ホーム画面: 表示のみ (subscribedPlayers, event_prefs サマリー)
              └─ 設定画面:  togglePlayer / toggleEvent
                                │
                                ├─ PUT /players → setPreferences(updated)
                                └─ PUT /events  → setPreferences(updated)
```

---

## 18. フロントエンド モジュール依存関係

```
app/_layout.tsx
  ├── lib/storage.ts      (getPushToken)
  └── lib/notifications.ts (setupNotificationHandlers)

app/onboarding.tsx
  ├── lib/notifications.ts (requestAndGetToken)
  ├── lib/api.ts           (registerUser)
  └── lib/storage.ts       (savePushToken)

app/(tabs)/index.tsx
app/(tabs)/settings.tsx
  ├── hooks/usePushToken.ts
  │     └── lib/storage.ts
  ├── hooks/usePreferences.ts
  │     └── lib/api.ts
  ├── components/PlayerCard.tsx
  │     ├── types/api.ts
  │     └── constants/colors.ts
  └── components/EventToggle.tsx
        └── constants/colors.ts

lib/api.ts
  └── types/api.ts

lib/notifications.ts
  └── expo-notifications, expo-constants

lib/storage.ts
  └── expo-secure-store
```

**循環依存なし**。`types/api.ts` と `constants/colors.ts` は全モジュールから参照される末端モジュール。

---

## 19. フロントエンド 拡張時の注意点・落とし穴

### 新しいイベント種別を追加する場合
1. バックエンドの `EVENT_MAP` に追加（RESEARCH.md §4 参照）
2. `types/api.ts` の `EventPreferences` インターフェースにキーを追加
3. `hooks/usePreferences.ts` の `toggleEvent` の型引数 `key: keyof EventPreferences` は自動対応
4. `app/(tabs)/settings.tsx` に `EventToggle` コンポーネントを追加
5. `app/(tabs)/index.tsx` の `SummaryBadge` にも追加

### EAS Build で本番リリースする場合
- `eas.json` を作成し、`eas build` でネイティブビルドを生成する
- `app.json` の `extra.eas.projectId` に Expo Dashboard のプロジェクトIDを設定
- `EXPO_PUBLIC_API_BASE_URL` を本番URLに変更（`https://` 必須）
- iOS: `bundleIdentifier`、Android: `package` が `app.json` に設定済み

### Expo Go での動作制限 (SDK 53以降)
**Expo SDK 53 以降、`expo-notifications` のリモートプッシュ通知機能は Expo Go から完全に削除された。**
- UI の確認（画面遷移・トグル動作）は Expo Go でも可能
- push token の取得 (`requestAndGetToken()`) は Expo Go でも実行できるが、実際の通知は届かない
- push 通知の E2E テストには **EAS Build による開発ビルド** が必須

```bash
npm install -g eas-cli
eas login
eas build --profile development --platform ios      # iOS 開発ビルド
eas build --profile development --platform android  # Android 開発ビルド
```

- 開発ビルドをインストールした実機で `npx expo start` に接続すれば、ホットリロードを維持しつつ push 通知もテストできる

### `expo-secure-store` の制限
- Web (`expo start --web`) ではSecureStoreが動作しないため、Web対応が必要な場合は `localStorage` へのフォールバックを実装する
- 値の最大サイズは 2048 バイト。push_tokenは通常100バイト以下のため問題なし

### push_token がURLパスに含まれるリスク
- バックエンドのアクセスログに push_token が平文で記録される
- push_token を知る第三者が設定の読み書きができてしまう（認証なし設計の制約）
- 将来的にはリクエストヘッダー（`X-Push-Token` 等）へ移行することで露出範囲を限定できる

### `__DEV__` グローバル変数
- Expo では開発中 (`expo start`) は `__DEV__ === true`、本番ビルドでは `false`
- `lib/api.ts` でエラーレスポンスの詳細を `__DEV__` フラグで出し分けている
- TypeScript の型定義は `expo/tsconfig.base` に含まれるため追加設定不要
