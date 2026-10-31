"""Routers: HTTP surface only (paths, status codes, auth dependencies). Logic lives in controllers/services."""
from fastapi import APIRouter

from app.routers import auth, books, chat, health, students

api_router = APIRouter()
for module in (health, auth, chat, books, students):
    api_router.include_router(module.router)

__all__ = ["api_router"]
