from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///./data/mlb_app.db"
    poll_interval_seconds: int = 20
    mlb_api_base_url: str = "https://statsapi.mlb.com/api"
    debug: bool = False
    # R=レギュラーシーズン, S=Spring Training, P=ポストシーズン
    # ※ MLB Stats API は単一値のみ対応。シーズンタイプを変更する場合は
    #   この値を書き換えてサーバーを再起動してください。
    game_type: str = "S"


settings = Settings()
