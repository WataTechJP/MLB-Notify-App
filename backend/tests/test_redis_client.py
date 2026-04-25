from unittest.mock import AsyncMock, patch

import pytest

from app.redis_client import ping_redis


@pytest.mark.anyio
async def test_ping_redis_uses_client_ping():
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    with patch("app.redis_client.get_redis", AsyncMock(return_value=mock_redis)):
        await ping_redis()

    mock_redis.ping.assert_awaited_once()
