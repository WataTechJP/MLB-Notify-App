import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from app.services.notification import send_notifications

router = APIRouter()


class TestNotificationRequest(BaseModel):
    push_token: str = Field(pattern=r"^ExponentPushToken\[.+\]$")


class DemoNotificationRequest(BaseModel):
    push_token: str = Field(pattern=r"^ExponentPushToken\[.+\]$")
    demo_type: Literal["batter", "pitcher", "mlb_first"] = "batter"


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


@router.post("/send-demo-notification")
async def send_demo_notification(body: DemoNotificationRequest):
    """通知文面のデモを送信する（DEBUG=true のときのみルートが登録される）"""
    if body.demo_type == "batter":
        title = "⚾ 大谷翔平 ホームラン！"
        message = (
            "大谷翔平選手が本日2本目のホームランを打ちました（対 Kyle Finnegan）！"
            "これで今シーズン44本目、MLB通算280本目です。"
        )
    elif body.demo_type == "pitcher":
        title = "🔥 山本由伸 奪三振！"
        message = (
            "山本由伸選手が本日3個目の三振を奪いました（Alec Bohmから）！"
            "これで今シーズン136個目、MLB通算412個目です。"
        )
    else:
        title = "⚾ 大谷翔平 ホームラン！"
        message = (
            "大谷翔平選手が本日1本目のホームランを打ちました（対 Kyle Finnegan）！"
            "これがMLB初ホームランです。"
        )

    async with httpx.AsyncClient() as client:
        try:
            await send_notifications(
                client,
                [body.push_token],
                title=title,
                body=message,
                data={"type": "demo", "demo_type": body.demo_type},
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Expo Push APIへの送信に失敗しました: {e}") from e

    return {"status": "sent", "demo_type": body.demo_type}
