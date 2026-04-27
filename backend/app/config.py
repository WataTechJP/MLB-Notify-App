from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# MLB Stats API で有効な gameType 値
_VALID_GAME_TYPES = {"R", "S", "P", "E", "D", "L", "W"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/mlb_app.db",
        validation_alias="DATABASE_URL",
    )
    mlb_api_base_url: str = "https://statsapi.mlb.com/api"
    debug: bool = Field(default=False, validation_alias="DEBUG")
    app_env: Literal["development", "preview", "production"] = Field(
        default="development",
        validation_alias="APP_ENV",
    )
    # R=レギュラーシーズン, S=Spring Training, P=ポストシーズン
    # ※ MLB Stats API は単一値のみ対応。シーズンタイプを変更する場合は
    #   この値を書き換えてサーバーを再起動してください。
    game_type: str = "R"

    # アダプティブ・ポーリング設定
    poll_live_seconds: int = 20          # LIVE状態の間隔
    poll_pregame_seconds: int = 60       # PREGAME状態の間隔
    poll_post_game_seconds: int = 120    # POST_GAME状態の間隔
    poll_post_game_count: int = 3        # POST_GAME追い込み回数
    poll_idle_minutes: int = 30          # IDLE状態の間隔（デフォルト）
    poll_idle_night_hours: int = 1       # ET 深夜帯の間隔
    pregame_window_minutes: int = 15     # PREGAME判定ウィンドウ

    @field_validator("poll_live_seconds", "poll_pregame_seconds", "poll_post_game_seconds")
    @classmethod
    def validate_min_poll_interval(cls, v: int) -> int:
        if v < 5:
            raise ValueError("Polling interval must be at least 5 seconds")
        return v

    @field_validator("poll_idle_minutes")
    @classmethod
    def validate_idle_minutes(cls, v: int) -> int:
        if v < 1:
            raise ValueError("poll_idle_minutes must be at least 1")
        return v

    @field_validator("game_type")
    @classmethod
    def validate_game_type(cls, v: str) -> str:
        if v not in _VALID_GAME_TYPES:
            raise ValueError(f"Invalid game_type '{v}'. Must be one of {_VALID_GAME_TYPES}")
        return v

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        if self.app_env != "production":
            return self
        if self.debug:
            raise ValueError("DEBUG must be false when APP_ENV=production")
        if self.database_url.startswith("sqlite"):
            raise ValueError("SQLite is not allowed when APP_ENV=production")
        return self


settings = Settings()
