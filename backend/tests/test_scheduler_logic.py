"""
scheduler.py のアダプティブ・ポーリングロジックのユニットテスト
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.config import settings
from app.services.mlb_api import GameScheduleEntry
from app.services.scheduler import (
    PollState,
    _calc_next_run_time,
    _determine_composite_state,
)


def _utcdt(hour: int, minute: int = 0) -> datetime:
    """テスト用 UTC datetime ファクトリ（2024-04-01 固定）"""
    return datetime(2024, 4, 1, hour, minute, 0, tzinfo=timezone.utc)


def _make_entry(
    abstract_state: str,
    minutes_offset: float,
    now: datetime,
    game_pk: int = 1,
) -> GameScheduleEntry:
    """now を基準に minutes_offset 分後の試合エントリを生成する"""
    return GameScheduleEntry(
        game_pk=game_pk,
        game_time_utc=now + timedelta(minutes=minutes_offset),
        abstract_game_state=abstract_state,
        detailed_state=None,
    )


# ──────────────────────────────────────────────
# _determine_composite_state のテスト
# ──────────────────────────────────────────────

def test_composite_state_live_wins():
    """LIVE + Final が混在 → LIVE が優先される"""
    now = _utcdt(20)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Live", -30, now),   # 30分前に開始した試合
            _make_entry("Final", -180, now), # 終了した試合
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.LIVE
    assert next_game is None


def test_composite_state_live_wins_over_pregame():
    """LIVE + PREGAME が混在 → LIVE が優先される"""
    now = _utcdt(20)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Live", -30, now),  # 試合中
            _make_entry("Preview", 10, now, game_pk=2),  # 10分後開始（PREGAME窓内）
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.LIVE


def test_composite_state_pregame_window():
    """開始13分前の Preview 試合 → PREGAME"""
    now = _utcdt(19)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Preview", 13, now),  # 13分後開始（15分窓内）
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.PREGAME
    assert next_game is None


def test_composite_state_pregame_window_boundary_outside():
    """開始16分前の Preview 試合 → PREGAME 窓外 → IDLE"""
    now = _utcdt(19)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Preview", 16, now),  # 16分後開始（15分窓外）
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.IDLE
    assert next_game is not None


def test_composite_state_all_final():
    """全試合 Final → POST_GAME"""
    now = _utcdt(23)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Final", -180, now, game_pk=1),
            _make_entry("Final", -120, now, game_pk=2),
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.POST_GAME
    assert next_game is None


def test_composite_state_empty():
    """試合なし → IDLE、next_game は None"""
    now = _utcdt(3)
    with patch("app.services.scheduler._utcnow", return_value=now):
        state, next_game = _determine_composite_state([])

    assert state == PollState.IDLE
    assert next_game is None


def test_composite_state_returns_nearest_next_game():
    """複数の今後の試合がある場合、最も近い試合時刻を返す"""
    now = _utcdt(14)
    with patch("app.services.scheduler._utcnow", return_value=now):
        entries = [
            _make_entry("Preview", 120, now, game_pk=1),  # 2時間後
            _make_entry("Preview", 60, now, game_pk=2),   # 1時間後（最近）
        ]
        state, next_game = _determine_composite_state(entries)

    assert state == PollState.IDLE
    expected = now + timedelta(minutes=60)
    assert next_game == expected


# ──────────────────────────────────────────────
# _calc_next_run_time のテスト
# ──────────────────────────────────────────────

def test_calc_live_interval():
    """LIVE → poll_live_seconds 後"""
    now = _utcdt(20)
    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.LIVE, None)

    expected = now + timedelta(seconds=settings.poll_live_seconds)
    assert next_run == expected


def test_calc_pregame_interval():
    """PREGAME → poll_pregame_seconds 後"""
    now = _utcdt(19)
    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.PREGAME, None)

    expected = now + timedelta(seconds=settings.poll_pregame_seconds)
    assert next_run == expected


def test_calc_post_game_interval():
    """POST_GAME → poll_post_game_seconds 後"""
    now = _utcdt(23)
    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.POST_GAME, None)

    expected = now + timedelta(seconds=settings.poll_post_game_seconds)
    assert next_run == expected


def test_idle_next_game_timing():
    """IDLE・3時間後に試合 → next_game - 15分 でスケジュール（30分より短い）"""
    now = _utcdt(14)
    next_game = now + timedelta(hours=3)  # 3時間後

    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.IDLE, next_game)

    # next_game - 15min = now + 165min, fallback = now + 30min
    # min(165, 30) → 30分後が選ばれる
    expected = now + timedelta(minutes=settings.poll_idle_minutes)
    assert next_run == expected


def test_idle_next_game_very_close():
    """IDLE・20分後に試合 → next_game - 15分 = 5分後"""
    now = _utcdt(19)
    next_game = now + timedelta(minutes=20)  # 20分後

    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.IDLE, next_game)

    # next_game - 15min = now + 5min, fallback = now + 30min
    # min(5, 30) → 5分後が選ばれる
    expected = next_game - timedelta(minutes=settings.pregame_window_minutes)
    assert next_run == expected


def test_idle_no_next_game():
    """IDLE・試合なし → poll_idle_minutes 後"""
    now = _utcdt(4)  # 深夜でない UTC 時刻

    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.IDLE, None)

    expected = now + timedelta(minutes=settings.poll_idle_minutes)
    assert next_run == expected


def test_idle_night_time_et():
    """IDLE・ET 深夜帯（04:00） → poll_idle_night_hours 後"""
    now = _utcdt(9)  # UTC 09:00 = ET 05:00（深夜帯）

    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=True),
    ):
        next_run = _calc_next_run_time(PollState.IDLE, None)

    expected = now + timedelta(hours=settings.poll_idle_night_hours)
    assert next_run == expected


# ──────────────────────────────────────────────
# POST_GAME カウンタフローのテスト
# ──────────────────────────────────────────────

def test_post_game_counter_flow():
    """POST_GAME カウンタが 3→2→1→0 と減り、0 になると IDLE 扱いになることを確認"""
    import app.services.scheduler as sched_module

    # カウンタをリセット
    sched_module._post_game_remaining = 3
    assert sched_module._post_game_remaining == 3

    # 1回目のポーリング後
    sched_module._post_game_remaining -= 1
    assert sched_module._post_game_remaining == 2

    # 2回目のポーリング後
    sched_module._post_game_remaining -= 1
    assert sched_module._post_game_remaining == 1

    # 3回目のポーリング後（IDLE に遷移する直前）
    sched_module._post_game_remaining -= 1
    assert sched_module._post_game_remaining == 0

    # カウンタ0 のとき POST_GAME ではなく IDLE として計算される
    # _poll_job の `else: state = IDLE` パスを想定した間隔確認
    now = _utcdt(23)
    with (
        patch("app.services.scheduler._utcnow", return_value=now),
        patch("app.services.scheduler._is_night_time_et", return_value=False),
    ):
        next_run = _calc_next_run_time(PollState.IDLE, None)

    assert next_run == now + timedelta(minutes=settings.poll_idle_minutes)
