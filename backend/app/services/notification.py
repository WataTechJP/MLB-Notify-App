import logging

import httpx
from sqlalchemy import update

from app.database import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
CHUNK_SIZE = 100


def _chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def _extract_device_not_registered_tokens(results: list[dict]) -> list[str]:
    invalid_tokens: list[str] = []
    for item in results:
        if item.get("status") != "error":
            continue
        details = item.get("details") or {}
        if details.get("error") != "DeviceNotRegistered":
            continue
        token = details.get("expoPushToken")
        if isinstance(token, str) and token:
            invalid_tokens.append(token)
    return invalid_tokens


async def _deactivate_push_tokens(tokens: list[str]) -> None:
    unique_tokens = list(dict.fromkeys(tokens))
    if not unique_tokens:
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(User)
            .where(User.expo_push_token.in_(unique_tokens))
            .values(is_active=False)
        )
        await db.commit()


async def send_notifications(
    client: httpx.AsyncClient,
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
) -> None:
    """Expo Push APIへ通知を送信する (100件チャンク)"""
    for chunk in _chunk(tokens, CHUNK_SIZE):
        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": data or {},
                "sound": "default",
            }
            for token in chunk
        ]
        try:
            resp = await client.post(
                EXPO_PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json"},
                timeout=15.0,
            )
            resp.raise_for_status()
            result = resp.json()
            result_data = result.get("data", [])
            invalid_tokens = _extract_device_not_registered_tokens(result_data)
            if invalid_tokens:
                await _deactivate_push_tokens(invalid_tokens)

            ok_count = sum(1 for item in result_data if item.get("status") == "ok")
            error_count = sum(1 for item in result_data if item.get("status") == "error")
            logger.info(
                "Push sent to %d tokens: ok=%d error=%d device_not_registered=%d",
                len(chunk),
                ok_count,
                error_count,
                len(invalid_tokens),
            )
        except httpx.HTTPError as e:
            logger.error("Failed to send push notifications: %s", e)
            raise
