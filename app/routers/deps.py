"""FastAPI dependencies: DB session, auth, and per-request controller construction (the wiring of
router -> controller -> service -> repository happens here, from the Container)."""
import uuid
from typing import AsyncIterator

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers import (AuthController, BookController, ChatController, HealthController,
                             StudentController)
from app.core.container import Container
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_token
from app.models import User
from app.repositories import BookRepository, ChatRepository, UserRepository
from app.services.auth_service import AuthService
from app.services.book_service import BookService
from app.services.chat_service import ChatService
from app.services.student_service import StudentService

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_session(c: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with c.sessionmaker() as s:
        yield s


async def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                           s: AsyncSession = Depends(get_session)) -> User:
    if creds is None:
        raise Unauthorized("Missing bearer token")
    try:
        uid = uuid.UUID(decode_token(creds.credentials)["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise Unauthorized("Invalid or expired token")
    user = await UserRepository(s).get(uid)
    if user is None or not user.is_active:  # deactivated users lose access immediately, even with a valid token
        raise Unauthorized("Account not found or disabled")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise Forbidden("Admin only")
    return user


async def require_student(user: User = Depends(get_current_user)) -> User:
    if user.role != "student" or not user.grade:
        raise Forbidden("Students only")
    return user


def auth_controller(s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)) -> AuthController:
    return AuthController(AuthService(UserRepository(s), c.redis))


def book_controller(s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)) -> BookController:
    return BookController(BookService(BookRepository(s), c.providers.vectors, c.jobs))


def student_controller(s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)) -> StudentController:
    return StudentController(StudentService(UserRepository(s), ChatRepository(s), c.quota))


def chat_controller(s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)) -> ChatController:
    return ChatController(ChatService(ChatRepository(s), BookRepository(s), c.quota, c.rag))


def health_controller(s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)) -> HealthController:
    return HealthController(s, c.redis, c.providers)
