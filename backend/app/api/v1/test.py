import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.notification import send_notifications

router = APIRouter()


class TestNotificationRequest(BaseModel):
    push_token: str = Field(pattern=r"^ExponentPushToken\[.+\]$")


@router.post("/send-notification")
async def send_test_notification(body: TestNotificationRequest):
    """テスト通知を送信する（DEBUG=true のときのみルートが登録される）"""
    async with httpx.AsyncClient() as client:
        try:
            await send_notifications(
                client,
                [body.push_token],
                title="🧪 テスト通知",
                body="通知が正常に届いています！",
                data={"type": "test"},
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Expo Push APIへの送信に失敗しました: {e}") from e

    return {"status": "sent"}
