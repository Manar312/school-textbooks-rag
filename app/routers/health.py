from fastapi import APIRouter, Depends, Request, Response

from app.controllers import HealthController
from app.routers.deps import health_controller

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def live():
    return {"status": "ok"}


@router.get("/ready")
async def ready(response: Response, ctrl: HealthController = Depends(health_controller)):
    ok, body = await ctrl.ready()
    if not ok:
        response.status_code = 503
    return body
