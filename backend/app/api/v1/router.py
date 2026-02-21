from fastapi import APIRouter

from app.api.v1 import players, users

router = APIRouter(prefix="/api/v1")

router.include_router(players.router, prefix="/players", tags=["players"])
# POST /api/v1/users/register
router.include_router(users.register_router, prefix="/users", tags=["users"])
# GET/PUT /api/v1/preferences/{push_token}/...
router.include_router(users.preferences_router, prefix="/preferences", tags=["preferences"])
