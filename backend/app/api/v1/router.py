from fastapi import APIRouter

from app.api.v1 import players, users
from app.config import settings

router = APIRouter(prefix="/api/v1")

router.include_router(players.router, prefix="/players", tags=["players"])
# POST /api/v1/users/register
router.include_router(users.register_router, prefix="/users", tags=["users"])
# GET/PUT /api/v1/preferences/{push_token}/...
router.include_router(users.preferences_router, prefix="/preferences", tags=["preferences"])

# POST /api/v1/test/send-notification
# DEBUG=true または ENABLE_TEST_ENDPOINTS=true の時に登録
if settings.debug or settings.enable_test_endpoints:
    from app.api.v1 import test as test_module
    router.include_router(test_module.router, prefix="/test", tags=["test"])
