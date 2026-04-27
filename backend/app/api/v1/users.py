import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
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

register_router = APIRouter()
preferences_router = APIRouter()
logger = logging.getLogger(__name__)

LEGACY_PLAYER_ID_MAP: dict[int, int] = {
    681936: 684007,  # 今永昇太
}

PushTokenHeader = Annotated[
    str,
    Header(
        alias="X-Push-Token",
        pattern=r"^ExponentPushToken\[.+\]$",
        description="Expo Push Token",
    ),
]


def _normalize_player_ids(player_ids: list[int]) -> list[int]:
    normalized: list[int] = []
    for pid in player_ids:
        canonical = LEGACY_PLAYER_ID_MAP.get(pid, pid)
        normalized.append(canonical)
    return list(dict.fromkeys(normalized))


async def _seed_player_event_prefs(db: AsyncSession, user_id: int) -> None:
    """選手ごとのイベント設定をシードする（既存レコードはスキップ）。"""
    existing_result = await db.execute(
        select(UserPlayerEventPref.player_id, UserPlayerEventPref.event_type).where(
            UserPlayerEventPref.user_id == user_id
        )
    )
    existing: set[tuple[int, str]] = {
        (row.player_id, row.event_type) for row in existing_result
    }

    for player_id, player_info in PLAYER_MAP.items():
        if player_info.position in ("batter", "two_way"):
            if (player_id, "home_run") not in existing:
                db.add(
                    UserPlayerEventPref(
                        user_id=user_id,
                        player_id=player_id,
                        event_type="home_run",
                        is_enabled=True,
                    )
                )
        if player_info.position in ("pitcher", "two_way"):
            if (player_id, "strikeout") not in existing:
                db.add(
                    UserPlayerEventPref(
                        user_id=user_id,
                        player_id=player_id,
                        event_type="strikeout",
                        is_enabled=True,
                    )
                )


async def _get_or_create_user(db: AsyncSession, push_token: str) -> tuple[User, bool]:
    """Push token からユーザーを取得。存在しなければ初期設定付きで作成する。"""
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    user = result.scalar_one_or_none()
    created = False

    if user is None:
        user = User(expo_push_token=push_token, is_active=True)
        db.add(user)
        await db.flush()
        created = True

        for player_id in PLAYER_MAP:
            db.add(UserPlayer(user_id=user.id, player_id=player_id))
        for event_type in ("home_run", "strikeout"):
            db.add(
                UserEventPref(
                    user_id=user.id,
                    event_type=event_type,
                    is_enabled=True,
                )
            )
    else:
        user.is_active = True

        existing_player_result = await db.execute(
            select(UserPlayer.player_id).where(UserPlayer.user_id == user.id)
        )
        existing_player_ids: set[int] = {
            row.player_id for row in existing_player_result
        }
        for player_id in PLAYER_MAP:
            if player_id not in existing_player_ids:
                db.add(UserPlayer(user_id=user.id, player_id=player_id))

    await _seed_player_event_prefs(db, user.id)
    return user, created


async def _get_user_by_token(db: AsyncSession, push_token: str) -> User | None:
    result = await db.execute(select(User).where(User.expo_push_token == push_token))
    return result.scalar_one_or_none()


async def _get_existing_user_or_404(db: AsyncSession, push_token: str) -> User:
    user = await _get_user_by_token(db, push_token)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _build_preferences_response(
    user: User,
    players: list[UserPlayer],
    prefs: list[UserEventPref],
    player_event_prefs_rows: list[UserPlayerEventPref],
) -> PreferencesResponse:
    player_event_prefs: dict[str, dict[str, bool]] = {}
    for row in player_event_prefs_rows:
        key = str(LEGACY_PLAYER_ID_MAP.get(row.player_id, row.player_id))
        if key not in player_event_prefs:
            player_event_prefs[key] = {}
        player_event_prefs[key][row.event_type] = row.is_enabled

    normalized_player_ids = _normalize_player_ids([p.player_id for p in players])

    return PreferencesResponse(
        expo_push_token=user.expo_push_token,
        is_active=user.is_active,
        player_ids=normalized_player_ids,
        event_prefs={p.event_type: p.is_enabled for p in prefs},
        player_event_prefs=player_event_prefs,
    )


@register_router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Expo Push Tokenを登録（既存なら更新）する"""
    logger.info("register_user called")
    try:
        user, _ = await _get_or_create_user(db, body.expo_push_token)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "register_user race detected for push token; retrying as fetch",
            exc_info=True,
        )
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


@register_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_current_user(
    push_token: PushTokenHeader,
    db: AsyncSession = Depends(get_db),
):
    """現在の push token を無効化して通知を停止する。"""
    user = await _get_existing_user_or_404(db, push_token)
    user.is_active = False
    await db.commit()


@preferences_router.get("", response_model=PreferencesResponse)
async def get_preferences(
    push_token: PushTokenHeader,
    db: AsyncSession = Depends(get_db),
):
    """ユーザー設定を取得する。未登録なら自動作成する。"""
    try:
        user, _ = await _get_or_create_user(db, push_token)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(
            "get_preferences race detected for push token; retrying as fetch",
            exc_info=True,
        )
        user = await _get_user_by_token(db, push_token)
        if user is None:
            raise HTTPException(status_code=500, detail="Failed to load preferences")
        user.is_active = True
        await _seed_player_event_prefs(db, user.id)
        await db.commit()

    await db.refresh(user)

    player_result = await db.execute(
        select(UserPlayer).where(UserPlayer.user_id == user.id)
    )
    players = player_result.scalars().all()

    pref_result = await db.execute(
        select(UserEventPref).where(UserEventPref.user_id == user.id)
    )
    prefs = pref_result.scalars().all()

    player_event_result = await db.execute(
        select(UserPlayerEventPref).where(
            UserPlayerEventPref.user_id == user.id
        )
    )
    player_event_prefs_rows = player_event_result.scalars().all()

    return _build_preferences_response(
        user=user,
        players=players,
        prefs=prefs,
        player_event_prefs_rows=player_event_prefs_rows,
    )


@preferences_router.put("/players", status_code=status.HTTP_204_NO_CONTENT)
async def update_player_prefs(
    body: PlayerPrefsUpdate,
    push_token: PushTokenHeader,
    db: AsyncSession = Depends(get_db),
):
    """購読選手を更新する"""
    user = await _get_existing_user_or_404(db, push_token)

    unique_player_ids = _normalize_player_ids(body.player_ids)
    invalid = [pid for pid in unique_player_ids if pid not in PLAYER_MAP]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Invalid player IDs: {invalid}")

    await db.execute(delete(UserPlayer).where(UserPlayer.user_id == user.id))
    for player_id in unique_player_ids:
        db.add(UserPlayer(user_id=user.id, player_id=player_id))

    await db.commit()


@preferences_router.put("/events", status_code=status.HTTP_204_NO_CONTENT)
async def update_event_prefs(
    body: EventPrefsUpdate,
    push_token: PushTokenHeader,
    db: AsyncSession = Depends(get_db),
):
    """イベント通知設定を更新する（後方互換エンドポイント）"""
    user = await _get_existing_user_or_404(db, push_token)
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
            db.add(
                UserEventPref(
                    user_id=user.id,
                    event_type=event_type,
                    is_enabled=is_enabled,
                )
            )
        else:
            pref.is_enabled = is_enabled

    await db.commit()


@preferences_router.put("/player-events", status_code=status.HTTP_204_NO_CONTENT)
async def update_player_event_prefs(
    body: PlayerEventPrefsUpdate,
    push_token: PushTokenHeader,
    db: AsyncSession = Depends(get_db),
):
    """選手ごとのイベント通知設定を更新する"""
    user = await _get_existing_user_or_404(db, push_token)

    if body.player_id not in PLAYER_MAP:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid player ID: {body.player_id}",
        )

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
            db.add(
                UserPlayerEventPref(
                    user_id=user.id,
                    player_id=body.player_id,
                    event_type=event_type,
                    is_enabled=is_enabled,
                )
            )
        else:
            pref.is_enabled = is_enabled

    await db.commit()
