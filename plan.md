# Issue #22: 修正箇所

## 要件

- TestFlightで「通知を許可して始める」を押すと502エラーが出る。原因を特定し修正し、デバッグ用ログも追加する
- 日本人選手リストにTatsuya Imai（今井達也）を追加する（Murakami・Okamotoは既に追加済み）
- ホームランの通知メッセージに対戦相手のピッチャー名を含める
- ピッチャーの三振の通知メッセージに三振を奪ったバッターの名前を含める

---

## 現状の把握

### 502エラーの発生フロー

1. フロントエンド `frontend/app/onboarding.tsx` の `handleAllow()` が呼ばれる
2. `frontend/lib/notifications.ts` の `requestAndGetToken()` でExpo Push Tokenを取得する
3. `frontend/lib/api.ts` の `registerUser(token)` が `POST /api/v1/users/register` を呼ぶ
4. `api.ts` 内の `request()` 関数は502をリトライ対象 (`RETRYABLE_STATUSES = new Set([502, 503, 504])`) として最大3回リトライする。リトライ間隔は `RETRY_DELAYS_MS = [500, 1500]` で定義されており、合計待機時間は 500+1500=2000ms（約2秒）
5. 3回とも502が返ると `throw new Error("通信エラーが発生しました (502)")` が発生し、`onboarding.tsx` の `Alert.alert("エラー", message)` で表示される

### 502エラーの原因候補（コードから特定）

**最有力: Railwayのコールドスタート / ヘルスチェック未設定**
- バックエンドのURLは `https://mlb-notify-app-production.up.railway.app`（`frontend/.env.example` 参照）
- `backend/app/main.py` の `lifespan` でスタートアップ時に `create_tables()` と `start_scheduler()` が実行される
- `start_scheduler()` は `httpx.AsyncClient` を生成し `APScheduler` を起動する
- このスタートアップが完了する前にリクエストが届くと502になる可能性がある
- Railway では `EXPOSE 8000` のみで、ヘルスチェックパスが設定されていない可能性がある（`/api/v1/health` エンドポイントは存在するがRailway設定で指定されているか不明）

**原因候補2: スケジューラのポーリング時のRedis障害**
- `backend/app/redis_client.py` の `get_redis()` は遅延接続であり、スタートアップ時はRedisに接続しない
- Redisが使われるのは `scheduler.py` の `_poll_job()` 内（201行目）で `detect_events()` を呼ぶ時のみ
- `/api/v1/users/register` はDBのみを使用しており、Redisは関与しない
- Redis障害は `/register` の502とは無関係。スケジューラのポーリング失敗として現れる

**原因候補3: 本番環境でのデバッグログ欠如**
- `api.ts` では `if (__DEV__)` の中だけでエラーレスポンスのbodyをログする（74行目）
- TestFlight（本番ビルド）では `__DEV__ = false` のため、サーバーが返した実際のエラー内容が一切ログされない
- これにより原因特定が困難になっている

**原因候補4: `/api/v1/users/register` のURLがリダイレクトされている場合**
- Railway上でHTTPSリダイレクトが発生し、POSTボディが失われて422エラー → フロントが502として表示しない（この場合は422で別エラーになるため可能性は低い）

### 選手リストの現状

`backend/app/constants/japanese_players.py` を確認した結果：
- 村上宗隆（Munetaka Murakami）: id=808959, position="batter", team="CWS" → **既に追加済み**
- 岡本和真（Kazuma Okamoto）: id=672960, position="batter", team="TOR" → **既に追加済み**
- 今井達也（Tatsuya Imai）: **未追加** → MLB Stats API検索で id=837227, Pitcher と確認済み

### 通知メッセージの現状

`backend/app/services/event_detector.py` の `_build_notification_message()` 関数（93行目）：
- 現在のシグネチャ: `(player_id, event_type, today_count, season_total, career_total)`
- ホームラン通知例: `「大谷翔平選手が本日2本目のホームランを打ちました！これで今シーズン44本目、MLB通算280本目です。」`
- 三振通知例: `「山本由伸選手が本日3個目の三振を奪いました！これで今シーズン136個目、MLB通算412個目です。」`
- ピッチャー名・バッター名は含まれていない

### `LIVE_FEED_FIELDS` の現状

`backend/app/services/mlb_api.py` 21行目：
```python
LIVE_FEED_FIELDS = (
    "gameData,status,abstractGameState,"
    "liveData,plays,allPlays,"
    "result,event,eventType,"
    "about,atBatIndex,isComplete,"
    "matchup,batter,id,pitcher,id"
)
```
- `batter` と `pitcher` の `id` のみ取得。`fullName` が含まれていない
- MLB Stats APIに `fullName` を追加すると正常に返ることをAPIへの直接リクエストで確認済み:
  ```json
  {"batter": {"id": 664761, "fullName": "Alec Bohm"}, "pitcher": {"id": 640448, "fullName": "Kyle Finnegan"}}
  ```

### `_process_play()` の現状

`backend/app/services/event_detector.py` 144行目：
- `matchup.get("batter", {}).get("id", 0)` と `matchup.get("pitcher", {}).get("id", 0)` のみ取得
- `fullName` の取得はしていない
- `_build_notification_message()` への呼び出し時に相手選手名を渡していない

---

## 影響範囲

### 変更が必要なファイル

| ファイル | 変更理由 |
|---|---|
| `backend/app/constants/japanese_players.py` | 今井達也を追加 |
| `backend/app/services/mlb_api.py` | `LIVE_FEED_FIELDS` に `fullName` を追加 |
| `backend/app/services/event_detector.py` | `_process_play()` で相手選手名を取得し `_build_notification_message()` に渡す。`_build_notification_message()` のシグネチャと本文を修正 |
| `backend/app/main.py` | `create_tables()` 前後にDB接続確認ログを追加。502エラー原因特定のためのスタートアップログを強化 |
| `backend/app/api/v1/users.py` | `/register` エンドポイントに詳細なエラーログを追加。`_get_or_create_user()` に `UserPlayer` のバックフィルロジックを追加（既存ユーザーへの今井達也購読状態の補完） |
| `frontend/lib/api.ts` | 本番環境でも最小限のエラー情報をログできるよう修正 |
| `backend/app/api/v1/test.py` | デモ通知文を新フォーマット（対戦相手名を含む形式）に合わせて更新 |

### 影響を受ける既存テスト

- `backend/tests/test_scheduler_logic.py`: `_determine_composite_state` と `_calc_next_run_time` のテストのみ。今回の変更対象外のため影響なし

---

## 修正方針

### 1. 502エラーの原因特定と修正

#### 診断ステップ（実装変更前に実施）

502エラーの根本原因はコードの静的解析のみでは断定できない。以下の順序で診断を行う。

(a) **Railwayのデプロイログを確認する**: Railway ダッシュボード > Deployments > ビルドログ・起動ログを確認し、スタートアップが正常に完了しているか確認する。DB接続エラー・ポート起動失敗などがログに出ていないか確認する。

(b) **フロントエンドログで実際の502を観測する**: 後述の 1-c（フロントエンドログ強化）をデプロイした後、TestFlight で再現し、Expo DevTools の console.error に `[API] 502` が出ることを確認する。`register_user()` 内のログ（1-b）は Railway ゲートウェイ起因の502では観測できないため、まずフロントエンドログでステータスコードを確認することが先決。

#### 1-a. バックエンドのスタートアップログ強化 (`backend/app/main.py`)

現在の `lifespan` 関数はスタートアップログが少ない。以下を追加：
- `create_tables()` の実行前後にDB接続確認ログを追加（成功/失敗を記録）
- `start_scheduler()` の完了ログを追加
- Redis ping はスタートアップ時には不要（Redisは `_poll_job()` 内で初めて使われるため）。Redis健全性確認はスケジューラのポーリングログで確認する

```python
# lifespan 内に追加（create_tables() 前後）
logger.info("Initializing database tables...")
try:
    await create_tables()
    logger.info("Database tables initialized successfully")
except Exception as e:
    logger.error("Failed to initialize database tables: %s", e)
    raise
start_scheduler()
logger.info("Scheduler started")
```

#### 1-b. `/register` エンドポイントの詳細ログ追加と例外処理の明示（診断と並行して適用する緩和策 - `backend/app/api/v1/users.py`）

現在の `register_user()` は `IntegrityError` のみ特別処理し、それ以外の例外は素通りする（コード99行目）。以下を追加：
- リクエスト受信時のログ（push_tokenの先頭部分をマスクして記録）
- `IntegrityError` 以外の例外をキャッチしてエラーログを記録し、`rollback` 後に `HTTPException(500)` を送出する

```python
@register_router.post("/register", ...)
async def register_user(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    logger.info("register_user called for token prefix=%s", body.expo_push_token[:20])
    try:
        user, _ = await _get_or_create_user(db, body.expo_push_token)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("register_user race detected ...", exc_info=True)
        user = await _get_user_by_token(db, body.expo_push_token)
        if user is None:
            raise HTTPException(status_code=500, detail="Failed to register user")
        user.is_active = True
        await _seed_player_event_prefs(db, user.id)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error("register_user unexpected error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
    await db.refresh(user)
    return user
```

**バリデーション系エラー（422）の扱い**: Pydantic による `RegisterRequest` のバリデーションは FastAPI が自動処理するため `except Exception` に入らない。`except Exception` はDB操作エラー（接続タイムアウト、DB障害など）のみが対象。

#### 1-c. フロントエンドのエラーロギング強化 (`frontend/lib/api.ts`)

現在は `__DEV__` の時のみエラーbodyをログする。本番（TestFlight）でも原因が分かるよう、エラー時のステータスコードとURLを常にログに出す：

```typescript
// 現在（74-77行目）
if (__DEV__) {
  const body = await res.text();
  console.error(`[API] ${res.status} ${url}:`, body);
}
throw new Error(`通信エラーが発生しました (${res.status})`);
```

修正後：
```typescript
// 本番でも最低限ステータスコードとURLはログする
console.error(`[API] ${res.status} ${url}`);
if (__DEV__) {
  const body = await res.text();
  console.error(`[API] response body:`, body);
}
throw new Error(`通信エラーが発生しました (${res.status})`);
```

**なぜこのアプローチか**: TestFlightのクラッシュログやExpo DevToolsでconsole.errorが確認できる。URLとステータスコードはセンシティブ情報ではないため本番でも出して問題ない。

#### 1-d. Railwayのヘルスチェック設定確認（コード外の対応）

`/api/v1/health` エンドポイントは既存のため、Railway側の設定で以下を確認する必要がある（これはコード変更ではなく運用対応）：
- Railway > Settings > Deploy > Health Check Path = `/api/v1/health`
- Health Check Timeout を適切に設定する

これにより、スタートアップ完了前にトラフィックが流れない。

#### 1-e. クライアントサイドのリトライ戦略延長（診断と並行して適用する緩和策 - `frontend/lib/api.ts`）

コールドスタートが主因の場合、現在の合計待機時間 2000ms（500+1500ms）では Railway の起動を待ちきれない可能性がある。リトライ間隔を延長して待機時間を増やす。

```typescript
// 変更前（11行目）
const RETRY_DELAYS_MS = [500, 1500];

// 変更後
const RETRY_DELAYS_MS = [1000, 3000];
```

合計待機時間が 1000+3000=4000ms（約4秒）に延長される。Railway のコールドスタートが原因であれば、この延長により3回目の試行までに起動が完了する可能性が高まる。

**なぜこのアプローチか**: Railway ヘルスチェックの設定（1-d）がコード外の運用対応であるのに対し、クライアント側のリトライ延長はコード変更で即座に対処できる。ヘルスチェック設定が適切になればリトライが不要になるが、設定確認が取れるまでのクライアント側の保険として機能する。

### 2. 今井達也の追加 (`backend/app/constants/japanese_players.py`)

MLB Stats API で id=837227 を確認済み。

```python
PlayerInfo(id=837227, name_ja="今井達也", name_en="Tatsuya Imai", position="pitcher", team="HOU"),
```

#### 2-a. 選手定数への追加

`PLAYER_MAP`, `PITCHER_IDS` は `JAPANESE_PLAYERS` から自動生成されるため、リストに追加するだけで他の箇所への影響は最小限。

#### 2-b. 既存ユーザーへの UserPlayer バックフィル（修正案Aを採用）

**問題の確認**: `_get_or_create_user()` の 80-84 行目のコードを読んだ結果、既存ユーザー（`else:` ブランチ）では `_seed_player_event_prefs()` のみ呼ばれる。`_seed_player_event_prefs()` は `UserPlayerEventPref`（通知種別設定）のみを補完し、`UserPlayer`（購読状態）は補完しない。一方 `frontend/app/(tabs)/settings.tsx` 179行目の購読判定は `preferences?.player_ids.includes(player.id) ?? false` であり、`player_ids` は `get_preferences()` の143行目の `select(UserPlayer).where(UserPlayer.user_id == user.id)` から取得される。

**結論**: 今井達也を `JAPANESE_PLAYERS` に追加しても、既存ユーザーには `UserPlayer` レコードが存在しないため、設定画面で「未購読」状態として表示される。

**方針**: 修正案Aを採用する。`_get_or_create_user()` の `else:` ブランチ（既存ユーザー）内で `_seed_player_event_prefs()` と同様に `UserPlayer` のバックフィルを行う。1回の SELECT で既存 player_id を取得し、`PLAYER_MAP` に存在するが `UserPlayer` レコードがない player_id のみを追加する。この処理は冪等であり、既存の購読状態を変更しない。

```python
# _get_or_create_user() の else: ブランチ（83行目付近）に追加
# 既存ユーザーにも不足分のUserPlayerを補完（新選手追加時の自動バックフィル）
existing_player_result = await db.execute(
    select(UserPlayer.player_id).where(UserPlayer.user_id == user.id)
)
existing_player_ids: set[int] = {row.player_id for row in existing_player_result}
for player_id in PLAYER_MAP:
    if player_id not in existing_player_ids:
        db.add(UserPlayer(user_id=user.id, player_id=player_id))
```

このロジックは `_get_or_create_user()` の `else:` ブランチと `await _seed_player_event_prefs(db, user.id)` の呼び出しの間に配置する。新規ユーザー（`if user is None:` ブランチ）では既に `for player_id in PLAYER_MAP:` で全員分の `UserPlayer` を登録しているため変更不要。

### 3. ホームランにピッチャー名を追加

#### 3-a. `LIVE_FEED_FIELDS` の修正 (`backend/app/services/mlb_api.py`)

```python
# 変更前
"matchup,batter,id,pitcher,id"

# 変更後
"matchup,batter,id,fullName,pitcher,id,fullName"
```

**なぜこのアプローチか**: MLB Stats API の `fields` パラメータで `fullName` を追加するだけで、他の処理への影響を最小限に抑えられる。APIへの直接リクエストで動作確認済み。

#### 3-b. `_process_play()` の修正 (`backend/app/services/event_detector.py`)

```python
# 変更前（166-167行目）
batter_id: int = matchup.get("batter", {}).get("id", 0)
pitcher_id: int = matchup.get("pitcher", {}).get("id", 0)

# 変更後
batter_id: int = matchup.get("batter", {}).get("id", 0)
batter_name: str = matchup.get("batter", {}).get("fullName", "")
pitcher_id: int = matchup.get("pitcher", {}).get("id", 0)
pitcher_name: str = matchup.get("pitcher", {}).get("fullName", "")
```

`_build_notification_message()` への呼び出し時に `opponent_name` を追加：

```python
# 変更前（203-209行目）
title, body = _build_notification_message(
    player_id,
    event_type,
    today_count=today_count,
    season_total=season_total,
    career_total=career_total,
)

# 変更後
opponent_name = pitcher_name if event_type == "home_run" else batter_name
title, body = _build_notification_message(
    player_id,
    event_type,
    today_count=today_count,
    season_total=season_total,
    career_total=career_total,
    opponent_name=opponent_name,
)
```

#### 3-c. `_build_notification_message()` のシグネチャと本文修正 (`backend/app/services/event_detector.py`)

シグネチャに `opponent_name: str = ""` を追加する：

```python
# 変更前
def _build_notification_message(
    player_id: int,
    event_type: str,
    today_count: int | None = None,
    season_total: int | None = None,
    career_total: int | None = None,
) -> tuple[str, str]:

# 変更後
def _build_notification_message(
    player_id: int,
    event_type: str,
    today_count: int | None = None,
    season_total: int | None = None,
    career_total: int | None = None,
    opponent_name: str = "",
) -> tuple[str, str]:
```

現在の関数本体には `home_run` と `strikeout` それぞれで4つのリターンパスがある。全パスにおける `pitcher_suffix`/`batter_suffix` の挿入箇所を以下に示す。

**`home_run` の4パス（`pitcher_suffix = f"（対 {opponent_name}）" if opponent_name else ""` を関数先頭で1回定義）**:

```python
pitcher_suffix = f"（対 {opponent_name}）" if opponent_name else ""

# パス(a): MLBデビュー時 career_total == 1
body = (
    f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！"
    "これがMLB初ホームランです。"
)
return title, body

# パス(b): today_count + season_total + career_total すべてあり（通常パス）
body = (
    f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！"
    f"これで今シーズン{season_total}本目、MLB通算{career_total}本目です。"
)
return title, body

# パス(c): today_count のみあり（season_total/career_total がNoneまたは0）
return title, f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！"

# パス(d): フォールバック（today_count もNone）
# opponent_name は挿入しない（今日のカウントも不明な状況のため）
return title, f"{name}選手がホームランを打ちました！"
```

**`strikeout` の4パス（`batter_suffix = f"（{opponent_name}から）" if opponent_name else ""` を関数先頭で1回定義）**:

```python
batter_suffix = f"（{opponent_name}から）" if opponent_name else ""

# パス(a): MLBデビュー時 career_total == 1
body = (
    f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"
    "これがMLB初奪三振です。"
)
return title, body

# パス(b): today_count + season_total + career_total すべてあり（通常パス）
body = (
    f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"
    f"これで今シーズン{season_total}個目、MLB通算{career_total}個目です。"
)
return title, body

# パス(c): today_count のみあり（season_total/career_total がNoneまたは0）
return title, f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"

# パス(d): フォールバック（today_count もNone）
# opponent_name は挿入しない（today_count も不明な状況のため）
return title, f"{name}選手が三振を奪いました！"
```

**なぜこのアプローチか**: デフォルト引数 `opponent_name=""` にすることで後方互換性を保ちつつ、全4パスで動作する。`pitcher_suffix`/`batter_suffix` を各パスの先頭で一度だけ定義することでDRYを保つ。パス(d)（フォールバック）は `today_count` も不明な状態のため、相手名の挿入は行わず従来通りの表示とする。opponent_nameが空文字の場合はsuffixが空になり従来通りの表示になる。

### 4. `test.py` のデモ通知を新しい形式に合わせて更新

`backend/app/api/v1/test.py` のデモ通知文も新フォーマットに合わせて更新する（任意。デモとして対戦相手名を含む例文にする）。

---

## テスト計画

### バックエンドの手動テスト

1. **スタートアップログ確認**: バックエンドを起動し、DB初期化ログ（`Database tables initialized successfully`）が正常に出ることを確認
2. **選手リスト確認**: `GET /api/v1/players` で今井達也（id=837227）が返ることを確認
3. **既存ユーザーへの補完確認**: 既存のpush tokenで `GET /api/v1/preferences/{token}` を呼び、(a) `player_ids` に837227が含まれること（`UserPlayer` バックフィルの確認）、(b) `player_event_prefs` に `837227: {strikeout: true}` が追加されること（`UserPlayerEventPref` バックフィルの確認）を確認する
4. **通知文面確認**: `POST /api/v1/test/send-demo-notification` でホームラン・三振のデモ通知を送り、ピッチャー/バッター名が含まれることを確認
   - **前提条件**: このエンドポイントは `backend/app/api/v1/router.py:16` の条件に従い、`DEBUG=true` または `ENABLE_TEST_ENDPOINTS=true` の環境変数が設定されている場合のみルートが登録される（`backend/app/config.py:21,23` 参照）。手動テスト実施時はいずれかの環境変数を設定すること

### ユニットテストの追加

`backend/tests/` に新しいテストファイルを追加：

**`test_event_detector.py`**:

単体テスト (`_build_notification_message()`):
- `opponent_name` ありの場合のテスト（ホームラン: ピッチャー名が含まれること、三振: バッター名が含まれること）
- `opponent_name` なし（空文字）の場合は従来通りの出力になることのテスト
- 全パス（`today_count=None`, 初本塁打 `career_total=1`, 通常）のテスト

結合テスト (`_process_play()` → `_build_notification_message()` フロー):
- `LIVE_FEED_FIELDS` で取得した形式（`{"batter": {"id": 660271, "fullName": "Shohei Ohtani"}, "pitcher": {"id": 640448, "fullName": "Kyle Finnegan"}}`）のplayデータをモックとして `_process_play()` に渡す
- Redis・DB・httpクライアントをモックし、`_build_notification_message()` に渡される `opponent_name` が正しく `fullName` の値になっていることをアサートする
- `home_run` イベント時: `opponent_name` が `pitcher.fullName` になること
- `strikeout` イベント時: `opponent_name` が `batter.fullName` になること
- `fullName` が存在しない（APIが返さない）場合: `opponent_name` が空文字になり通知メッセージが従来通りになること

**`test_japanese_players.py`**:
- `JAPANESE_PLAYERS` に837227が含まれることのテスト
- `PITCHER_IDS` に837227が含まれることのテスト
- `BATTER_IDS` に837227が含まれないことのテスト

**`test_register_user.py`**:

`backend/app/api/v1/users.py` の `register_user()` に対するテスト（`AsyncSession` をモック）：

- (a) 正常系（新規ユーザー登録）: `POST /register` に新しいpush tokenを送ると、`User`・`UserPlayer`・`UserEventPref`・`UserPlayerEventPref` が作成され、`201` と登録済みユーザーが返ること
- (b) `IntegrityError` 発生時の吸収と成功: `_get_or_create_user()` が `IntegrityError` を送出した場合、rollback後に `_get_user_by_token()` でユーザーを取得して成功扱い（`201`）になること。競合ユーザーが見つかる場合と見つからない場合（`HTTPException(500)` を返すべき）の両方をテストする
- (c) 想定外 Exception 発生時の rollback + HTTPException(500) 返却: `_get_or_create_user()` が `IntegrityError` 以外の例外（例: `sqlalchemy.exc.OperationalError`）を送出した場合、rollback 後に `HTTPException(status_code=500)` が返ること

---

## リスク

### 1. 今井達也のチーム情報

MLB Stats API の `/v1/people/837227?hydrate=currentTeam` で `currentTeam = Houston Astros` を確認済み。`team="HOU"` を使用する。

### 2. 村上宗隆・岡本和真の所属チーム変更の可能性

現在のリストでは村上宗隆 `team="CWS"`, 岡本和真 `team="TOR"` だが、シーズン中にトレードがあると古い情報になる。今回の変更範囲外だが、確認が必要。

### 3. `LIVE_FEED_FIELDS` に `fullName` を追加した場合のAPIレスポンスサイズ増加

`fullName` は選手名（通常10〜30文字程度）であり、1試合あたり数十プレイを取得するため、レスポンスサイズへの影響は軽微。

### 4. `opponent_name` が空文字になるケース

MLB Stats APIが `fullName` を返さないケース（APIの仕様変更や特定試合タイプ）では `opponent_name=""` となり、従来通りの通知文が表示される。デフォルト引数を空文字にすることでこのケースをカバー済み。

### 5. 既存ユーザーへのバックフィル処理

今井達也追加後、既存ユーザーが次にアプリを開いたとき（`_get_or_create_user()` が呼ばれたとき）に以下の2つのバックフィルが自動実行される。

- **`UserPlayer` バックフィル（修正案A）**: `_get_or_create_user()` の `else:` ブランチに追加するロジック。既存 player_id と `PLAYER_MAP` を差分比較し、不足分のみ `UserPlayer` レコードを追加する。これにより設定画面で今井達也が「購読済み」状態で表示される。
- **`UserPlayerEventPref` バックフィル**: 既存の `_seed_player_event_prefs()` が処理する。今井達也の `strikeout: true` 設定が追加される。

両処理ともに冪等であり、既存レコードはスキップされる。`UserPlayer` のバックフィルが未実装の場合、設定画面では今井達也が「未購読」として表示されるが、`UserPlayerEventPref` のシードは行われるため通知種別設定テーブルと購読状態テーブルが不整合な状態になる。修正案Aの採用によりこの不整合を回避する。

### 6. 502エラーの真の原因が別にある可能性

調査はコードベースの静的解析に基づいており、Railway側のログや実際のエラーレスポンスのbodyを確認していない。コード変更に加えて、Railwayのデプロイログを直接確認することが推奨される。スタートアップログの強化により、次回デプロイ後に原因特定が容易になる。
