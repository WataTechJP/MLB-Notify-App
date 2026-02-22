import logging

import httpx

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
CHUNK_SIZE = 100


def _chunk(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


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
            logger.info("Push sent to %d tokens: %s", len(chunk), result.get("data", []))
        except httpx.HTTPError as e:
            logger.error("Failed to send push notifications: %s", e)
            raise
