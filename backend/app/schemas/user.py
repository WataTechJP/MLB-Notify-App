import re

from pydantic import BaseModel, Field, field_validator

_EXPO_TOKEN_RE = re.compile(r"^ExponentPushToken\[.+\]$")


class RegisterRequest(BaseModel):
    expo_push_token: str = Field(..., max_length=255, description="Expo Push Token (ExponentPushToken[xxx])")

    @field_validator("expo_push_token")
    @classmethod
    def validate_expo_token(cls, v: str) -> str:
        if not _EXPO_TOKEN_RE.match(v):
            raise ValueError("Invalid Expo Push Token format. Expected: ExponentPushToken[xxx]")
        return v


class RegisterResponse(BaseModel):
    id: int
    expo_push_token: str
    is_active: bool

    model_config = {"from_attributes": True}


class PlayerPrefsUpdate(BaseModel):
    player_ids: list[int] = Field(..., max_length=50, description="購読する選手IDのリスト")


class EventPrefsUpdate(BaseModel):
    home_run: bool = True
    strikeout: bool = True


class PreferencesResponse(BaseModel):
    expo_push_token: str
    is_active: bool
    player_ids: list[int]
    event_prefs: dict[str, bool]

    model_config = {"from_attributes": True}
