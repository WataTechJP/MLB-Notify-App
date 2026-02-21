from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.japanese_players import PLAYER_MAP
from app.database import get_db
from app.models.user import User, UserEventPref, UserPlayer
from app.schemas.user import (
    EventPrefsUpdate,
    PlayerPrefsUpdate,
    PreferencesResponse,
    RegisterRequest,
    RegisterResponse,
)

# POST /api/v1/users/register
register_router = APIRouter()

# GET/PUT /api/v1/preferences/{push_token}/...
preferences_router = APIRouter()


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

    await db.commit()
    await db.refresh(user)
    return user


@preferences_router.get("/{push_token}", response_model=PreferencesResponse)
async def get_preferences(push_token: str, db: AsyncSession = Depends(get_db)):
    """ユーザー設定を取得する"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    player_result = await db.execute(select(UserPlayer).where(UserPlayer.user_id == user.id))
    players = player_result.scalars().all()

    pref_result = await db.execute(select(UserEventPref).where(UserEventPref.user_id == user.id))
    prefs = pref_result.scalars().all()

    return PreferencesResponse(
        expo_push_token=user.expo_push_token,
        is_active=user.is_active,
        player_ids=[p.player_id for p in players],
        event_prefs={p.event_type: p.is_enabled for p in prefs},
    )


@preferences_router.put("/{push_token}/players", status_code=status.HTTP_204_NO_CONTENT)
async def update_player_prefs(
    push_token: str, body: PlayerPrefsUpdate, db: AsyncSession = Depends(get_db)
):
    """購読選手を更新する"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # 無効な選手IDチェック
    invalid = [pid for pid in body.player_ids if pid not in PLAYER_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid player IDs: {invalid}")

    # 既存レコードを削除して再登録
    existing = await db.execute(select(UserPlayer).where(UserPlayer.user_id == user.id))
    for record in existing.scalars().all():
        await db.delete(record)

    for player_id in body.player_ids:
        db.add(UserPlayer(user_id=user.id, player_id=player_id))

    await db.commit()


@preferences_router.put("/{push_token}/events", status_code=status.HTTP_204_NO_CONTENT)
async def update_event_prefs(
    push_token: str, body: EventPrefsUpdate, db: AsyncSession = Depends(get_db)
):
    """イベント通知設定を更新する"""
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
