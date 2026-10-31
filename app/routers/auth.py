from fastapi import APIRouter, Depends, Request

from app.controllers import AuthController
from app.models import User
from app.routers.deps import auth_controller, get_current_user
from app.schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, ctrl: AuthController = Depends(auth_controller)):
    return await ctrl.login(body, request.client.host if request.client else "?")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
