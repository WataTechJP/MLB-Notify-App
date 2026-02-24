import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from enum import Enum, auto
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.config import settings
from app.database import AsyncSessionLocal
from app.redis_client import get_redis
from app.services.event_detector import detect_events
from app.services.mlb_api import GameScheduleEntry, get_todays_schedule

logger = logging.getLogger(__name__)


class PollState(Enum):
    IDLE = auto()
    PREGAME = auto()
    LIVE = auto()
    POST_GAME = auto()


_scheduler: AsyncIOScheduler | None = None
_http_client: httpx.AsyncClient | None = None
_post_game_remaining: int = 0
_schedule_cache: list[GameScheduleEntry] = []
_schedule_cache_at: datetime | None = None
_schedule_cache_date: date | None = None
_poll_lock: asyncio.Lock | None = None

SCHEDULE_CACHE_TTL_SECONDS = 120


def _utcnow() -> datetime:
    """現在時刻（UTC）を返す。テストでモック可能にするためのラッパー。"""
    return datetime.now(timezone.utc)


def _is_night_time_et() -> bool:
    """ET 03:00〜09:00 → True（深夜帯判定）"""
    now_et = datetime.now(ZoneInfo("America/New_York"))
    return 3 <= now_et.hour < 9


def _determine_composite_state(
    entries: list[GameScheduleEntry],
) -> tuple[PollState, datetime | None]:
    """
    複数試合の状態から最も優先度の高い状態を返す。
    優先度: LIVE > PREGAME（開始15分以内） > POST_GAME（全Final） > IDLE
    返り値: (PollState, 次試合開始時刻UTC or None)
    """
    if not entries:
        return PollState.IDLE, None

    now = _utcnow()
    has_live = False
    has_preview_soon = False
    all_final = True
    next_game_time: datetime | None = None

    for entry in entries:
        state = entry.abstract_game_state

        if state == "Live":
            has_live = True
            all_final = False
        elif state == "Preview":
            all_final = False
            time_to_game_min = (entry.game_time_utc - now).total_seconds() / 60
            if 0 <= time_to_game_min <= settings.pregame_window_minutes:
                has_preview_soon = True
            if entry.game_time_utc > now:
                if next_game_time is None or entry.game_time_utc < next_game_time:
                    next_game_time = entry.game_time_utc
        elif state == "Final":
            pass  # all_final はそのまま
        else:
            # 未知状態（Postponed, Cancelled 等）は Final 扱いしない
            all_final = False
            logger.warning(
                "Unknown abstractGameState: %s (game_pk=%s)", state, entry.game_pk
            )

    if has_live:
        return PollState.LIVE, None
    if has_preview_soon:
        return PollState.PREGAME, None
    if all_final:
        return PollState.POST_GAME, None
    return PollState.IDLE, next_game_time


def _calc_next_run_time(
    state: PollState,
    next_game_time_utc: datetime | None,
) -> datetime:
    """次回ポーリング実行時刻を算出する（最低 5 秒後を保証）"""
    now = _utcnow()

    if state == PollState.LIVE:
        return now + timedelta(seconds=settings.poll_live_seconds)
    if state == PollState.PREGAME:
        return now + timedelta(seconds=settings.poll_pregame_seconds)
    if state == PollState.POST_GAME:
        return now + timedelta(seconds=settings.poll_post_game_seconds)

    # IDLE
    if _is_night_time_et():
        return now + timedelta(hours=settings.poll_idle_night_hours)
    if next_game_time_utc is not None:
        # 次試合-15分 と now+30分 の早い方（最低 5 秒後を保証）
        target = next_game_time_utc - timedelta(minutes=settings.pregame_window_minutes)
        fallback = now + timedelta(minutes=settings.poll_idle_minutes)
        return max(min(target, fallback), now + timedelta(seconds=5))
    return now + timedelta(minutes=settings.poll_idle_minutes)


def _reschedule(next_run: datetime) -> None:
    """ジョブの次回実行時刻を DateTrigger で更新する"""
    if _scheduler is None or not _scheduler.running:
        return
    # 過去時刻への設定を防止（最低 5 秒後）
    now = _utcnow()
    if next_run < now + timedelta(seconds=5):
        next_run = now + timedelta(seconds=5)
    _scheduler.reschedule_job(
        "mlb_poll",
        trigger=DateTrigger(run_date=next_run),
    )
    delay = (next_run - _utcnow()).total_seconds()
    logger.info(
        "Next poll scheduled at %s UTC (in %.0fs)",
        next_run.strftime("%H:%M:%S"),
        delay,
    )


async def _get_schedule_with_cache() -> list[GameScheduleEntry]:
    """スケジュールをキャッシュ付きで取得する（TTL=120秒、日付またぎで自動無効化）"""
    global _schedule_cache, _schedule_cache_at, _schedule_cache_date

    now = _utcnow()
    today = now.date()

    if (
        _schedule_cache_at is not None
        and _schedule_cache_date == today
        and (now - _schedule_cache_at).total_seconds() < SCHEDULE_CACHE_TTL_SECONDS
    ):
        return _schedule_cache

    if _http_client is None:
        return []

    entries = await get_todays_schedule(_http_client, game_type=settings.game_type)
    _schedule_cache = entries
    _schedule_cache_at = now
    _schedule_cache_date = today
    return entries


async def _poll_job() -> None:
    """APSchedulerから実行されるアダプティブ・ポーリングジョブ"""
    global _post_game_remaining

    if _http_client is None:
        logger.warning("HTTP client not initialized, skipping poll")
        return

    # 明示的ロックで再入を防止
    if _poll_lock is None:
        logger.warning("Poll lock not initialized, skipping poll")
        return
    if _poll_lock.locked():
        logger.warning("Previous poll still running, skipping")
        return

    async with _poll_lock:
        try:
            entries = await _get_schedule_with_cache()
            state, next_game_time = _determine_composite_state(entries)
            logger.debug("Poll state: %s", state.name)

            game_pks = [e.game_pk for e in entries]

            if state == PollState.LIVE:
                _post_game_remaining = settings.poll_post_game_count
                redis = await get_redis()
                async with AsyncSessionLocal() as db:
                    await detect_events(
                        redis, db, _http_client,
                        game_type=settings.game_type,
                        game_pks=game_pks,
                    )

            elif state == PollState.POST_GAME:
                if _post_game_remaining > 0:
                    redis = await get_redis()
                    async with AsyncSessionLocal() as db:
                        await detect_events(
                            redis, db, _http_client,
                            game_type=settings.game_type,
                            include_final=True,
                            game_pks=game_pks,
                        )
                    _post_game_remaining -= 1
                    logger.debug("POST_GAME poll (%d remaining)", _post_game_remaining)
                    if _post_game_remaining == 0:
                        state = PollState.IDLE
                else:
                    state = PollState.IDLE

            # PREGAME / IDLE: detect_events は実行しない

            _reschedule(_calc_next_run_time(state, next_game_time))

        except Exception as e:
            logger.error("Poll job error: %s", e, exc_info=True)
            # エラー時は安全のためデフォルトIDLE間隔で再スケジュール
            _reschedule(_utcnow() + timedelta(minutes=settings.poll_idle_minutes))


def start_scheduler() -> None:
    global _scheduler, _http_client, _post_game_remaining, _poll_lock

    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
    )
    _post_game_remaining = 0
    _poll_lock = asyncio.Lock()

    first_run = _utcnow() + timedelta(seconds=5)
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _poll_job,
        trigger=DateTrigger(run_date=first_run),
        id="mlb_poll",
        name="MLB event polling",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    _scheduler.start()
    logger.info("Scheduler started (adaptive polling, game_type=%s)", settings.game_type)


async def stop_scheduler() -> None:
    global _scheduler, _http_client

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")

    if _http_client:
        await _http_client.aclose()
        _http_client = None
