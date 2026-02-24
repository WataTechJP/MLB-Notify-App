import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.japanese_players import BATTER_IDS, PITCHER_IDS, PLAYER_MAP
from app.models.user import User, UserPlayer, UserPlayerEventPref
from app.services.mlb_api import (
    extract_plays,
    get_live_feed,
    get_player_event_totals,
    get_todays_games,
    is_live_game,
)
from app.services.notification import send_notifications

logger = logging.getLogger(__name__)

# fire-and-forget タスクをGCされないよう保持するセット
_background_tasks: set[asyncio.Task] = set()


def _handle_notification_task_error(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
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


async def _increment_and_get_daily_event_count(
    redis: Redis,
    player_id: int,
    event_type: str,
) -> int:
    """当日中の選手別イベント数をインクリメントして返す"""
    jst_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    key = f"daily_event_count:{jst_date}:{player_id}:{event_type}"
    count = await redis.incr(key)
    # 日付を跨いだ遅延処理も吸収できるよう2日保持
    if count == 1:
        await redis.expire(key, 172800)
    return int(count)


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
            UserPlayerEventPref,
            (UserPlayerEventPref.user_id == User.id)
            & (UserPlayerEventPref.player_id == UserPlayer.player_id)
            & (UserPlayerEventPref.event_type == event_type),
        )
        .where(
            UserPlayer.player_id == player_id,
            UserPlayerEventPref.is_enabled == True,  # noqa: E712
            User.is_active == True,  # noqa: E712
        )
    )
    return list(result.scalars().all())


def _build_notification_message(
    player_id: int,
    event_type: str,
    today_count: int | None = None,
    season_total: int | None = None,
    career_total: int | None = None,
) -> tuple[str, str]:
    """通知タイトルと本文を生成する"""
    player = PLAYER_MAP.get(player_id)
    name = player.name_ja if player else f"Player {player_id}"

    if event_type == "home_run":
        title = f"⚾ {name} ホームラン！"
        if today_count is not None and career_total == 1:
            body = (
                f"{name}選手が本日{today_count}本目のホームランを打ちました！"
                "これがMLB初ホームランです。"
            )
            return title, body
        # season_total > 0 のときのみシーズン成績を表示（Spring Training等でNone/0の場合は省略）
        if today_count is not None and season_total and (career_total is not None):
            body = (
                f"{name}選手が本日{today_count}本目のホームランを打ちました！"
                f"これで今シーズン{season_total}本目、MLB通算{career_total}本目です。"
            )
            return title, body
        if today_count is not None:
            return title, f"{name}選手が本日{today_count}本目のホームランを打ちました！"
        return title, f"{name}選手がホームランを打ちました！"
    elif event_type == "strikeout":
        title = f"🔥 {name} 奪三振！"
        if today_count is not None and career_total == 1:
            body = (
                f"{name}選手が本日{today_count}個目の三振を奪いました！"
                "これがMLB初奪三振です。"
            )
            return title, body
        # season_total > 0 のときのみシーズン成績を表示（Spring Training等でNone/0の場合は省略）
        if today_count is not None and season_total and (career_total is not None):
            body = (
                f"{name}選手が本日{today_count}個目の三振を奪いました！"
                f"これで今シーズン{season_total}個目、MLB通算{career_total}個目です。"
            )
            return title, body
        if today_count is not None:
            return title, f"{name}選手が本日{today_count}個目の三振を奪いました！"
        return title, f"{name}選手が三振を奪いました！"
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

        today_count = await _increment_and_get_daily_event_count(redis, player_id, event_type)
        season_total, career_total = await get_player_event_totals(
            http_client,
            player_id,
            event_type,
        )

        title, body = _build_notification_message(
            player_id,
            event_type,
            today_count=today_count,
            season_total=season_total,
            career_total=career_total,
        )
        task = asyncio.create_task(send_notifications(http_client, tokens, title, body))
        _background_tasks.add(task)
        task.add_done_callback(_handle_notification_task_error)

    except Exception as e:
        logger.error("Error processing play: %s", e, exc_info=True)


async def detect_events(
    redis: Redis,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    game_type: str = "R",
    include_final: bool = False,
    game_pks: list[int] | None = None,
) -> None:
    """
    メインのイベント検知処理 (LIVE時およびPOST_GAME追い込み時に呼ばれる)。

    Args:
        include_final: True の場合、Final 状態の試合フィードも処理する（POST_GAME用）。
        game_pks: 処理対象の gamePk リスト。None の場合はスケジュールAPIから取得する。
    """
    if game_pks is None:
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
        if not is_live_game(feed) and not include_final:
            continue

        plays = extract_plays(feed)
        for play in plays:
            await _process_play(play, game_pk, redis, db, http_client)
