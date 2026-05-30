import pytest

from app.services.event_detector import (
    _adjust_total_for_pending_events,
    _build_notification_message,
    _count_pending_new_events,
    _extract_home_run_metrics,
)


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


def test_adjust_total_for_pending_events_counts_forward_from_current_total():
    assert _adjust_total_for_pending_events(700, 2) == 699
    assert _adjust_total_for_pending_events(700, 1) == 700
    assert _adjust_total_for_pending_events(None, 2) is None


class _FakeRedis:
    def __init__(self, values: dict[str, int | None]):
        self.values = values

    async def get(self, key: str) -> int | None:
        return self.values.get(key)


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
