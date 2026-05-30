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


def _parse_optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_hit_data(play: dict) -> dict | None:
    """MLB feed variants may expose hitData on the play or on a playEvent."""
    candidate = play.get("hitData")
    if isinstance(candidate, dict) and candidate:
        return candidate

    play_events = play.get("playEvents", [])
    if not isinstance(play_events, list):
        return None

    for play_event in reversed(play_events):
        candidate = play_event.get("hitData")
        if isinstance(candidate, dict) and candidate:
            return candidate
    return None


def _extract_home_run_metrics(play: dict) -> str:
    """ホームラン通知に付与する打球データを整形する。"""
    hit_data = _find_hit_data(play)
    if not hit_data:
        return ""

    distance_ft = _parse_optional_float(hit_data.get("totalDistance"))
    launch_speed_mph = _parse_optional_float(hit_data.get("launchSpeed"))
    launch_angle = _parse_optional_float(hit_data.get("launchAngle"))

    metrics: list[str] = []
    if distance_ft is not None:
        metrics.append(f"飛距離 {round(distance_ft * 0.3048)}m")
    if launch_speed_mph is not None:
        metrics.append(f"打球速度 {round(launch_speed_mph * 1.60934)}km/h")
    if launch_angle is not None:
        metrics.append(f"角度 {round(launch_angle)}°")

    if not metrics:
        return ""
    return " " + " / ".join(metrics) + "。"


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
    opponent_name: str = "",
    home_run_metrics: str = "",
) -> tuple[str, str]:
    """通知タイトルと本文を生成する"""
    player = PLAYER_MAP.get(player_id)
    name = player.name_ja if player else f"Player {player_id}"

    if event_type == "home_run":
        title = f"⚾ {name} ホームラン！"
        pitcher_suffix = f"（対 {opponent_name}）" if opponent_name else ""
        if today_count is not None and career_total == 1:
            body = (
                f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！"
                f"これがMLB初ホームランです。{home_run_metrics}"
            )
            return title, body
        # season_total > 0 のときのみシーズン成績を表示（Spring Training等でNone/0の場合は省略）
        if today_count is not None and season_total and (career_total is not None):
            body = (
                f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！"
                f"これで今シーズン{season_total}本目、MLB通算{career_total}本目です。{home_run_metrics}"
            )
            return title, body
        if today_count is not None:
            return (
                title,
                f"{name}選手が本日{today_count}本目のホームランを打ちました{pitcher_suffix}！{home_run_metrics}",
            )
        return title, f"{name}選手がホームランを打ちました！{home_run_metrics}"
    elif event_type == "strikeout":
        title = f"🔥 {name} 奪三振！"
        batter_suffix = f"（{opponent_name}から）" if opponent_name else ""
        if today_count is not None and career_total == 1:
            body = (
                f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"
                "これがMLB初奪三振です。"
            )
            return title, body
        # season_total > 0 のときのみシーズン成績を表示（Spring Training等でNone/0の場合は省略）
        if today_count is not None and season_total and (career_total is not None):
            body = (
                f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"
                f"これで今シーズン{season_total}個目、MLB通算{career_total}個目です。"
            )
            return title, body
        if today_count is not None:
            return title, f"{name}選手が本日{today_count}個目の三振を奪いました{batter_suffix}！"
        return title, f"{name}選手が三振を奪いました！"
    else:
        return f"{name} イベント発生", f"{name} にイベントが発生しました"


def _identify_target_event(play: dict) -> tuple[str, int, str, int] | None:
    result = play.get("result", {})
    about = play.get("about", {})
    matchup = play.get("matchup", {})

    event_name = result.get("event", "")
    event_type = EVENT_MAP.get(event_name)
    if not event_type:
        return None

    if not about.get("isComplete", False):
        return None

    at_bat_index = about.get("atBatIndex", -1)
    batter_id = matchup.get("batter", {}).get("id", 0)
    batter_name = matchup.get("batter", {}).get("fullName", "")
    pitcher_id = matchup.get("pitcher", {}).get("id", 0)
    pitcher_name = matchup.get("pitcher", {}).get("fullName", "")

    if event_type == "home_run" and batter_id in BATTER_IDS:
        return event_type, batter_id, pitcher_name, at_bat_index
    if event_type == "strikeout" and pitcher_id in PITCHER_IDS:
        return event_type, pitcher_id, batter_name, at_bat_index
    return None


def _adjust_total_for_pending_events(total: int | None, remaining_pending_count: int) -> int | None:
    if total is None:
        return None
    return max(total - max(remaining_pending_count - 1, 0), 0)


async def _count_pending_new_events(
    plays: list[dict],
    game_pk: int,
    redis: Redis,
) -> dict[tuple[int, str], int]:
    counts: dict[tuple[int, str], int] = {}
    last_indexes: dict[int, int] = {}

    for play in plays:
        identified = _identify_target_event(play)
        if identified is None:
            continue

        event_type, player_id, _, at_bat_index = identified
        if player_id not in last_indexes:
            last_indexes[player_id] = await _get_last_at_bat_index(redis, player_id, game_pk)
        if at_bat_index <= last_indexes[player_id]:
            continue

        key = (player_id, event_type)
        counts[key] = counts.get(key, 0) + 1

    return counts


async def _process_play(
    play: dict,
    game_pk: int,
    redis: Redis,
    db: AsyncSession,
    http_client: httpx.AsyncClient,
    pending_event_counts: dict[tuple[int, str], int] | None = None,
) -> None:
    """1プレイを解析してイベント検知・通知を行う"""
    try:
        identified = _identify_target_event(play)
        if identified is None:
            return
        event_type, player_id, opponent_name, at_bat_index = identified

        # Redis重複チェック
        last_index = await _get_last_at_bat_index(redis, player_id, game_pk)
        if at_bat_index <= last_index:
            return

        pending_key = (player_id, event_type)
        remaining_pending_count = 1
        if pending_event_counts is not None:
            remaining_pending_count = max(pending_event_counts.get(pending_key, 1), 1)
            pending_event_counts[pending_key] = max(remaining_pending_count - 1, 0)

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
        season_total = _adjust_total_for_pending_events(season_total, remaining_pending_count)
        career_total = _adjust_total_for_pending_events(career_total, remaining_pending_count)

        home_run_metrics = _extract_home_run_metrics(play) if event_type == "home_run" else ""
        title, body = _build_notification_message(
            player_id,
            event_type,
            today_count=today_count,
            season_total=season_total,
            career_total=career_total,
            opponent_name=opponent_name,
            home_run_metrics=home_run_metrics,
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
        pending_event_counts = await _count_pending_new_events(plays, game_pk, redis)
        for play in plays:
            await _process_play(play, game_pk, redis, db, http_client, pending_event_counts)
