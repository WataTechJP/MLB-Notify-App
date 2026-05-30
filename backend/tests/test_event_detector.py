from app.services.event_detector import _build_notification_message, _extract_home_run_metrics


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
