from fastapi import APIRouter

from app.constants.japanese_players import JAPANESE_PLAYERS

router = APIRouter()


@router.get("")
async def list_players():
    """日本人選手一覧を返す"""
    return [
        {
            "id": p.id,
            "name_ja": p.name_ja,
            "name_en": p.name_en,
            "position": p.position,
            "team": p.team,
        }
        for p in JAPANESE_PLAYERS
    ]
