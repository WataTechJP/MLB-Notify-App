from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.japanese_players import PLAYER_MAP
from app.database import get_db
from app.models.user import User, UserEventPref, UserPlayer, UserPlayerEventPref
from app.schemas.user import (
    EventPrefsUpdate,
    PlayerEventPrefsUpdate,
    PlayerPrefsUpdate,
    PreferencesResponse,
    RegisterRequest,
    RegisterResponse,
)

# POST /api/v1/users/register
register_router = APIRouter()

# GET/PUT /api/v1/preferences/{push_token}/...
preferences_router = APIRouter()


async def _seed_player_event_prefs(db: AsyncSession, user_id: int) -> None:
    """選手ごとのイベント設定をシードする（既存レコードはスキップ）。
    既存ユーザーにも選手マスタ更新時に自動でシードされるよう毎回呼ぶ設計。
    """
    # 1回のSELECTで既存レコードを全取得
    existing_result = await db.execute(
        select(UserPlayerEventPref.player_id, UserPlayerEventPref.event_type)
        .where(UserPlayerEventPref.user_id == user_id)
    )
    existing: set[tuple[int, str]] = {(row.player_id, row.event_type) for row in existing_result}

    for player_id, player_info in PLAYER_MAP.items():
        if player_info.position in ("batter", "two_way"):
            if (player_id, "home_run") not in existing:
                db.add(UserPlayerEventPref(user_id=user_id, player_id=player_id, event_type="home_run", is_enabled=True))
        if player_info.position in ("pitcher", "two_way"):
            if (player_id, "strikeout") not in existing:
                db.add(UserPlayerEventPref(user_id=user_id, player_id=player_id, event_type="strikeout", is_enabled=True))


@register_router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_user(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Expo Push Tokenを登録（既存なら更新）する"""
    result = await db.execute(select(User).where(User.expo_push_token == body.expo_push_token))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(expo_push_token=body.expo_push_token, is_active=True)
        db.add(user)
        await db.flush()

        # デフォルトで全選手・全イベントを購読
        for player_id in PLAYER_MAP:
            db.add(UserPlayer(user_id=user.id, player_id=player_id))
        for event_type in ("home_run", "strikeout"):
            db.add(UserEventPref(user_id=user.id, event_type=event_type, is_enabled=True))
    else:
        user.is_active = True

    # 選手ごとのイベント設定をシード（既存ユーザーにもなければ追加）
    await _seed_player_event_prefs(db, user.id)

    await db.commit()
    await db.refresh(user)
    return user


PushTokenPath = Annotated[str, Path(pattern=r"^ExponentPushToken\[.+\]$", description="Expo Push Token")]


@preferences_router.get("/{push_token}", response_model=PreferencesResponse)
async def get_preferences(
    push_token: PushTokenPath, db: AsyncSession = Depends(get_db)
):
    """ユーザー設定を取得する"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    player_result = await db.execute(select(UserPlayer).where(UserPlayer.user_id == user.id))
    players = player_result.scalars().all()

    pref_result = await db.execute(select(UserEventPref).where(UserEventPref.user_id == user.id))
    prefs = pref_result.scalars().all()

    player_event_result = await db.execute(
        select(UserPlayerEventPref).where(UserPlayerEventPref.user_id == user.id)
    )
    player_event_prefs_rows = player_event_result.scalars().all()

    # {"660271": {"home_run": true, "strikeout": false}, ...}
    player_event_prefs: dict[str, dict[str, bool]] = {}
    for row in player_event_prefs_rows:
        key = str(row.player_id)
        if key not in player_event_prefs:
            player_event_prefs[key] = {}
        player_event_prefs[key][row.event_type] = row.is_enabled

    return PreferencesResponse(
        expo_push_token=user.expo_push_token,
        is_active=user.is_active,
        player_ids=[p.player_id for p in players],
        event_prefs={p.event_type: p.is_enabled for p in prefs},
        player_event_prefs=player_event_prefs,
    )


@preferences_router.put("/{push_token}/players", status_code=status.HTTP_204_NO_CONTENT)
async def update_player_prefs(
    push_token: PushTokenPath, body: PlayerPrefsUpdate, db: AsyncSession = Depends(get_db)
):
    """購読選手を更新する"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # 重複IDを除去しつつ順序は維持
    unique_player_ids = list(dict.fromkeys(body.player_ids))

    # 無効な選手IDチェック
    invalid = [pid for pid in unique_player_ids if pid not in PLAYER_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid player IDs: {invalid}")

    # 一括削除後に再登録する（ユニーク制約衝突を回避）
    await db.execute(delete(UserPlayer).where(UserPlayer.user_id == user.id))

    for player_id in unique_player_ids:
        db.add(UserPlayer(user_id=user.id, player_id=player_id))

    await db.commit()


@preferences_router.put("/{push_token}/events", status_code=status.HTTP_204_NO_CONTENT)
async def update_event_prefs(
    push_token: PushTokenPath, body: EventPrefsUpdate, db: AsyncSession = Depends(get_db)
):
    """イベント通知設定を更新する（後方互換エンドポイント）"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    event_settings = {"home_run": body.home_run, "strikeout": body.strikeout}

    for event_type, is_enabled in event_settings.items():
        pref_result = await db.execute(
            select(UserEventPref).where(
                UserEventPref.user_id == user.id,
                UserEventPref.event_type == event_type,
            )
        )
        pref = pref_result.scalar_one_or_none()
        if pref is None:
            db.add(UserEventPref(user_id=user.id, event_type=event_type, is_enabled=is_enabled))
        else:
            pref.is_enabled = is_enabled

    await db.commit()


@preferences_router.put("/{push_token}/player-events", status_code=status.HTTP_204_NO_CONTENT)
async def update_player_event_prefs(
    push_token: PushTokenPath, body: PlayerEventPrefsUpdate, db: AsyncSession = Depends(get_db)
):
    """選手ごとのイベント通知設定を更新する"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.player_id not in PLAYER_MAP:
        raise HTTPException(status_code=422, detail=f"Invalid player ID: {body.player_id}")

    player_info = PLAYER_MAP[body.player_id]
    updates: dict[str, bool] = {}

    if body.home_run is not None and player_info.position in ("batter", "two_way"):
        updates["home_run"] = body.home_run
    if body.strikeout is not None and player_info.position in ("pitcher", "two_way"):
        updates["strikeout"] = body.strikeout

    for event_type, is_enabled in updates.items():
        pref_result = await db.execute(
            select(UserPlayerEventPref).where(
                UserPlayerEventPref.user_id == user.id,
                UserPlayerEventPref.player_id == body.player_id,
                UserPlayerEventPref.event_type == event_type,
            )
        )
        pref = pref_result.scalar_one_or_none()
        if pref is None:
            db.add(UserPlayerEventPref(
                user_id=user.id,
                player_id=body.player_id,
                event_type=event_type,
                is_enabled=is_enabled,
            ))
        else:
            pref.is_enabled = is_enabled

    await db.commit()
