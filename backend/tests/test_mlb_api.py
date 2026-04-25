from datetime import datetime
from unittest.mock import patch

from app.services import mlb_api


def test_mlb_today_uses_eastern_time_date():
    mocked_now = datetime(2026, 4, 24, 20, 12, 0, tzinfo=mlb_api.MLB_TIMEZONE)

    with patch("app.services.mlb_api._mlb_now", return_value=mocked_now):
        assert mlb_api._mlb_today_str() == "2026-04-24"


def test_mlb_season_year_uses_eastern_time_year():
    mocked_now = datetime(2026, 12, 31, 23, 59, 0, tzinfo=mlb_api.MLB_TIMEZONE)

    with patch("app.services.mlb_api._mlb_now", return_value=mocked_now):
        assert mlb_api._mlb_season_year() == 2026
