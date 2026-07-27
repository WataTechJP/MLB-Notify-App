import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

import app.services.event_detector as ed_module
from app.services.event_detector import (
    _adjust_total_for_pending_events,
    _build_notification_message,
    _count_pending_new_events,
    _extract_home_run_metrics,
    _process_play,
)


@pytest.fixture(autouse=True)
def clear_background_tasks():
    ed_module._background_tasks.clear()
    yield
    ed_module._background_tasks.clear()


def test_extract_home_run_metrics_formats_metric_values():
    play = {
        "playEvents": [
            {"details": {"description": "Ball"}},
            {
                "hitData": {
                    "totalDistance": 443.2,
                    "launchSpeed": 112.4,
                    "launchAngle": 28.6,
                }
            },
        ]
    }

    assert _extract_home_run_metrics(play) == " 飛距離 135m / 打球速度 181km/h / 角度 29°。"


def test_extract_home_run_metrics_uses_play_level_hit_data():
    play = {
        "hitData": {
            "totalDistance": "400",
            "launchSpeed": "100",
            "launchAngle": "30",
        },
        "playEvents": [],
    }

    assert _extract_home_run_metrics(play) == " 飛距離 122m / 打球速度 161km/h / 角度 30°。"


def test_build_notification_message_appends_home_run_metrics():
    title, body = _build_notification_message(
        660271,
        "home_run",
        today_count=2,
        season_total=10,
        career_total=200,
        opponent_name="山本由伸",
        home_run_metrics=" 飛距離 135m / 打球速度 181km/h / 角度 29°。",
    )

    assert title == "⚾ 大谷翔平 ホームラン！"
    assert "本日2本目" in body
    assert "今シーズン10本目、MLB通算200本目です。" in body
    assert body.endswith("飛距離 135m / 打球速度 181km/h / 角度 29°。")


def test_build_notification_message_strikeout_with_season_and_career_total():
    title, body = _build_notification_message(
        808967,
        "strikeout",
        today_count=2,
        season_total=50,
        career_total=200,
        opponent_name="Mike Trout",
    )

    assert title == "🔥 山本由伸 奪三振！"
    assert "本日2個目" in body
    assert "今シーズン50個目" in body
    assert "MLB通算200個目" in body


def test_adjust_total_for_pending_events_counts_forward_from_current_total():
    assert _adjust_total_for_pending_events(700, 2) == 699
    assert _adjust_total_for_pending_events(700, 1) == 700
    assert _adjust_total_for_pending_events(None, 2) is None


class _FakeRedis:
    def __init__(self, values: dict[str, int | None]):
        self.values = values

    async def get(self, key: str) -> int | None:
        return self.values.get(key)


class _FakeRedisWithIncr:
    """incr / expire / set / get をサポートする FakeRedis"""

    def __init__(self, values: dict | None = None):
        self.values: dict[str, int] = values or {}

    async def get(self, key: str) -> int | None:
        return self.values.get(key)

    async def set(self, key: str, value: int, ex: int | None = None) -> None:
        self.values[key] = value

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        pass  # TTL は無視


def _make_strikeout_play(at_bat_index: int, batter_id: int, pitcher_id: int = 808967) -> dict:
    return {
        "result": {"event": "Strikeout"},
        "about": {"atBatIndex": at_bat_index, "isComplete": True},
        "matchup": {
            "pitcher": {"id": pitcher_id, "fullName": "Yoshinobu Yamamoto"},
            "batter": {"id": batter_id, "fullName": f"Batter {batter_id}"},
        },
    }


@pytest.mark.anyio
async def test_count_pending_new_events_ignores_already_processed_plays():
    game_pk = 12345
    redis = _FakeRedis({f"last_event:808967:{game_pk}": 6})
    plays = [
        {
            "result": {"event": "Strikeout"},
            "about": {"atBatIndex": 5, "isComplete": True},
            "matchup": {
                "pitcher": {"id": 808967, "fullName": "Yoshinobu Yamamoto"},
                "batter": {"id": 111, "fullName": "Batter One"},
            },
        },
        {
            "result": {"event": "Strikeout"},
            "about": {"atBatIndex": 7, "isComplete": True},
            "matchup": {
                "pitcher": {"id": 808967, "fullName": "Yoshinobu Yamamoto"},
                "batter": {"id": 222, "fullName": "Batter Two"},
            },
        },
        {
            "result": {"event": "Strikeout"},
            "about": {"atBatIndex": 8, "isComplete": True},
            "matchup": {
                "pitcher": {"id": 808967, "fullName": "Yoshinobu Yamamoto"},
                "batter": {"id": 333, "fullName": "Batter Three"},
            },
        },
    ]

    assert await _count_pending_new_events(plays, game_pk, redis) == {
        (808967, "strikeout"): 2,
    }


@pytest.mark.anyio
async def test_process_play_increments_daily_count_even_when_no_subscribers():
    """subscribers がいなくても today_count がインクリメントされることを確認する回帰テスト。

    修正前（today_count のインクリメントが _get_target_users の後にあった場合）は
    このテストが失敗する。今回の修正でインクリメント位置を前に移動したことを検証する。
    """
    fake_redis = _FakeRedisWithIncr()
    play = _make_strikeout_play(at_bat_index=10, batter_id=111)

    with (
        patch("app.services.event_detector._get_target_users", return_value=[]),
        patch("app.services.event_detector._get_last_at_bat_index", return_value=-1),
        patch("app.services.event_detector._set_last_at_bat_index"),
    ):
        await _process_play(
            play,
            game_pk=99999,
            redis=fake_redis,
            db=AsyncMock(),
            http_client=AsyncMock(),
        )

    jst_date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    key = f"daily_event_count:{jst_date}:808967:strikeout"
    assert fake_redis.values.get(key) == 1


@pytest.mark.anyio
async def test_process_play_multiple_pending_events_increment_n_and_m_correctly():
    """3つの未処理奪三振イベントを順に処理したとき、n=1,2,3 と season/career が正しく出ること。

    pending_event_counts による _adjust_total_for_pending_events の補正と
    today_count の連番インクリメントが正しく連携していることを確認する。

    get_player_event_totals が (50, 200) を返すとき:
    - play1: remaining=3 → season=48, career=198
    - play2: remaining=2 → season=49, career=199
    - play3: remaining=1 → season=50, career=200
    """
    fake_redis = _FakeRedisWithIncr()
    game_pk = 99999
    player_id = 808967

    plays = [
        _make_strikeout_play(at_bat_index=5, batter_id=111),
        _make_strikeout_play(at_bat_index=7, batter_id=222),
        _make_strikeout_play(at_bat_index=8, batter_id=333),
    ]

    captured_bodies: list[str] = []

    async def fake_send_notifications(client, tokens, title, body, data=None):
        captured_bodies.append(body)

    pending_event_counts = {(player_id, "strikeout"): 3}

    with (
        patch("app.services.event_detector._get_target_users", return_value=["token1"]),
        patch("app.services.event_detector._get_last_at_bat_index", return_value=-1),
        patch("app.services.event_detector._set_last_at_bat_index"),
        patch("app.services.event_detector.get_player_event_totals", return_value=(50, 200)),
        patch("app.services.event_detector.send_notifications", side_effect=fake_send_notifications),
    ):
        for play in plays:
            await _process_play(
                play,
                game_pk=game_pk,
                redis=fake_redis,
                db=AsyncMock(),
                http_client=AsyncMock(),
                pending_event_counts=pending_event_counts,
            )
        # このテストで作成した fire-and-forget タスクのみ flush する
        created_tasks = list(ed_module._background_tasks)
        if created_tasks:
            await asyncio.gather(*created_tasks, return_exceptions=True)

    assert len(captured_bodies) == 3
    assert "本日1個目" in captured_bodies[0]
    assert "本日2個目" in captured_bodies[1]
    assert "本日3個目" in captured_bodies[2]
    assert "今シーズン48個目" in captured_bodies[0]
    assert "今シーズン49個目" in captured_bodies[1]
    assert "今シーズン50個目" in captured_bodies[2]
    assert "MLB通算198個目" in captured_bodies[0]
    assert "MLB通算199個目" in captured_bodies[1]
    assert "MLB通算200個目" in captured_bodies[2]
