from unittest.mock import AsyncMock, patch

import pytest

from app.services.notification import send_notifications


class _FakeResponse:
    def __init__(self, data: list[dict]):
        self._data = {"data": data}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


@pytest.mark.anyio
async def test_send_notifications_deactivates_invalid_tokens():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_FakeResponse([
        {"status": "ok", "id": "ok-1"},
        {
            "status": "error",
            "details": {
                "error": "DeviceNotRegistered",
                "expoPushToken": "ExponentPushToken[invalid-1]",
            },
        },
    ]))

    with patch(
        "app.services.notification._deactivate_push_tokens",
        AsyncMock(),
    ) as deactivate_mock:
        await send_notifications(
            client,
            ["ExponentPushToken[valid-1]", "ExponentPushToken[invalid-1]"],
            "title",
            "body",
        )

    deactivate_mock.assert_awaited_once_with(["ExponentPushToken[invalid-1]"])


@pytest.mark.anyio
async def test_send_notifications_skips_deactivation_when_all_ok():
    client = AsyncMock()
    client.post = AsyncMock(return_value=_FakeResponse([
        {"status": "ok", "id": "ok-1"},
        {"status": "ok", "id": "ok-2"},
    ]))

    with patch(
        "app.services.notification._deactivate_push_tokens",
        AsyncMock(),
    ) as deactivate_mock:
        await send_notifications(
            client,
            ["ExponentPushToken[valid-1]", "ExponentPushToken[valid-2]"],
            "title",
            "body",
        )

    deactivate_mock.assert_not_awaited()
