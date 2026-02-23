import logging
from datetime import date

import httpx
import pytz

from app.config import settings

logger = logging.getLogger(__name__)

# MLB Stats APIのフィールドを絞り込んでレスポンスを軽量化
LIVE_FEED_FIELDS = (
    "gameData,status,abstractGameState,"
    "liveData,plays,allPlays,"
    "result,event,eventType,"
    "about,atBatIndex,isComplete,"
    "matchup,batter,id,pitcher,id"
)


async def get_todays_games(client: httpx.AsyncClient, game_type: str = "R") -> list[int]:
    """今日の試合のgamePkリストを取得する"""
    today = date.today().strftime("%Y-%m-%d")
    url = f"{settings.mlb_api_base_url}/v1/schedule"
    params = {"sportId": 1, "date": today, "gameType": game_type}

    try:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.error("Failed to fetch today's schedule: %s", e)
        return []

    game_pks: list[int] = []
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pks.append(game["gamePk"])

    logger.debug("Today's games: %s", game_pks)
    return game_pks


async def get_live_feed(client: httpx.AsyncClient, game_pk: int) -> dict | None:
    """試合のライブフィードを取得する"""
    url = f"{settings.mlb_api_base_url}/v1.1/game/{game_pk}/feed/live"
    params = {"fields": LIVE_FEED_FIELDS}

    try:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch live feed for game %s: %s", game_pk, e)
        return None


def is_live_game(feed: dict) -> bool:
    """試合がライブ中かどうかを判定する"""
    try:
        state = feed["gameData"]["status"]["abstractGameState"]
        return state == "Live"
    except (KeyError, TypeError):
        return False


def extract_plays(feed: dict) -> list[dict]:
    """allPlaysを取得する"""
    try:
        return feed["liveData"]["plays"]["allPlays"]
    except (KeyError, TypeError):
        return []


def _extract_stat_total(stats: list[dict], stat_type: str, stat_key: str) -> int | None:
    """stats配列から season/career の集計値を取り出す"""
    target = stat_type.lower()
    for entry in stats:
        type_name = (
            entry.get("type", {}).get("displayName")
            or entry.get("type", {}).get("code")
            or ""
        )
        if str(type_name).lower() != target:
            continue

        splits = entry.get("splits", [])
        if not splits:
            return 0

        stat = splits[0].get("stat", {})
        raw = stat.get(stat_key)
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0
    return None


async def get_player_event_totals(
    client: httpx.AsyncClient,
    player_id: int,
    event_type: str,
) -> tuple[int | None, int | None]:
    """
    対象イベントの今季通算/MLB通算を取得する
    - home_run -> hitting.homeRuns
    - strikeout -> pitching.strikeOuts
    """
    if event_type == "home_run":
        group = "hitting"
        stat_key = "homeRuns"
    elif event_type == "strikeout":
        group = "pitching"
        stat_key = "strikeOuts"
    else:
        return None, None

    url = f"{settings.mlb_api_base_url}/v1/people/{player_id}/stats"
    params = {
        "stats": "season,career",
        "group": group,
        "season": date.today().year,
    }

    try:
        resp = await client.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        logger.warning(
            "Failed to fetch player stats: player=%s event=%s err=%s",
            player_id, event_type, e,
        )
        return None, None

    stats = data.get("stats", [])
    season_total = _extract_stat_total(stats, "season", stat_key)
    career_total = _extract_stat_total(stats, "career", stat_key)
    return season_total, career_total
