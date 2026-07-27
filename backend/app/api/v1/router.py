from fastapi import APIRouter

from app.api.v1 import players, test as test_module, users

router = APIRouter(prefix="/api/v1")

router.include_router(players.router, prefix="/players", tags=["players"])
# POST /api/v1/users/register
router.include_router(users.register_router, prefix="/users", tags=["users"])
# GET/PUT /api/v1/preferences with X-Push-Token header
router.include_router(users.preferences_router, prefix="/preferences", tags=["preferences"])

# POST /api/v1/test/send-notification
# POST /api/v1/test/send-demo-notification
router.include_router(test_module.router, prefix="/test", tags=["test"])
