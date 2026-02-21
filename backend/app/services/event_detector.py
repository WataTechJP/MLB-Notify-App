import asyncio
import logging

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.japanese_players import BATTER_IDS, PITCHER_IDS, PLAYER_MAP
from app.models.user import User, UserEventPref, UserPlayer
from app.services.mlb_api import extract_plays, get_live_feed, get_todays_games, is_live_game
from app.services.notification import send_notifications

logger = logging.getLogger(__name__)


def _handle_notification_task_error(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception():
        logger.error("Notification task failed: %s", task.exception(), exc_info=task.exception())


# MLB Stats API のイベント名 → 内部イベントタイプのマッピング
EVENT_MAP = {
    "Home Run": "home_run",
    "Strikeout": "strikeout",
}

REDIS_TTL = 86400  # 24時間


async def _get_last_at_bat_index(redis: Redis, player_id: int, game_pk: int) -> int:
    key = f"last_event:{player_id}:{game_pk}"
    val = await redis.get(key)
    return int(val) if val is not None else -1


async def _set_last_at_bat_index(redis: Redis, player_id: int, game_pk: int, at_bat_index: int) -> None:
    key = f"last_event:{player_id}:{game_pk}"
    await redis.set(key, at_bat_index, ex=REDIS_TTL)


async def _get_target_users(
    db: AsyncSession,
    player_id: int,
    event_type: str,
) -> list[str]:
    """指定選手・イベントをONにしているユーザーのpush tokenリストを返す"""
    result = await db.execute(
        select(User.expo_push_token)
        .join(UserPlayer, UserPlayer.user_id == User.id)
        .join(
            UserEventPref,
            (UserEventPref.user_id == User.id) & (UserEventPref.event_type == event_type),
        )
        .where(
            UserPlayer.player_id == player_id,
            UserEventPref.is_enabled == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


def _build_notification_message(player_id: int, event_type: str) -> tuple[str, str]:
    """通知タイトルと本文を生成する"""
    player = PLAYER_MAP.get(player_id)
    name = player.name_ja if player else f"Player {player_id}"

    if event_type == "home_run":
        return f"⚾ {name} ホームラン！", f"{name} がホームランを打ちました！"
    elif event_type == "strikeout":
        return f"🔥 {name} 奪三振！", f"{name} が三振を奪いました！"
    else:
        return f"{name} イベント発生", f"{name} にイベントが発生しました"


async def _process_play(
    play: dict,
    game_pk: int,
    redis: Redis,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
) -> None:
    """1プレイを解析してイベント検知・通知を行う"""
    try:
        result = play.get("result", {})
        about = play.get("about", {})
        matchup = play.get("matchup", {})

        event_name = result.get("event", "")
        event_type = EVENT_MAP.get(event_name)
        if not event_type:
            return

        at_bat_index: int = about.get("atBatIndex", -1)
        if not about.get("isComplete", False):
            return

        batter_id: int = matchup.get("batter", {}).get("id", 0)
        pitcher_id: int = matchup.get("pitcher", {}).get("id", 0)

        # 日本人選手かどうか判定
        if event_type == "home_run" and batter_id in BATTER_IDS:
            player_id = batter_id
        elif event_type == "strikeout" and pitcher_id in PITCHER_IDS:
            player_id = pitcher_id
        else:
            return

        # Redis重複チェック
        last_index = await _get_last_at_bat_index(redis, player_id, game_pk)
        if at_bat_index <= last_index:
            return

        # 新規イベント: Redis更新
        await _set_last_at_bat_index(redis, player_id, game_pk, at_bat_index)

        logger.info(
            "New event detected: player=%s event=%s game=%s at_bat=%s",
            player_id, event_type, game_pk, at_bat_index,
        )

        # 通知対象ユーザー取得
        tokens = await _get_target_users(db, player_id, event_type)
        if not tokens:
            logger.debug("No subscribers for player=%s event=%s", player_id, event_type)
            return

        title, body = _build_notification_message(player_id, event_type)
        task = asyncio.create_task(send_notifications(http_client, tokens, title, body))
        task.add_done_callback(_handle_notification_task_error)

    except Exception as e:
        logger.error("Error processing play: %s", e, exc_info=True)


async def detect_events(
    redis: Redis,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    game_type: str = "R",
) -> None:
    """メインのイベント検知処理 (スケジューラーから20秒ごとに呼ばれる)"""
    game_pks = await get_todays_games(http_client, game_type=game_type)
    if not game_pks:
        logger.debug("No games today")
        return

    feeds = await asyncio.gather(
        *[get_live_feed(http_client, gp) for gp in game_pks],
        return_exceptions=True,
    )

    for game_pk, feed in zip(game_pks, feeds):
        if isinstance(feed, Exception) or feed is None:
            continue
        if not is_live_game(feed):
            continue

        plays = extract_plays(feed)
        for play in plays:
            await _process_play(play, game_pk, redis, db, http_client)
