"""Usage:
  python -m app.cli init-db
  python -m app.cli create-admin --email a@b.com --password '...' --name 'Admin'
  python -m app.cli providers          # show the active models + every provider you can switch to from .env
"""
import argparse
import asyncio
import json

from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import Base, User
from app.providers import Providers, available
from app.repositories import UserRepository


async def init_db():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    print("tables ready")


async def create_admin(email: str, password: str, name: str):
    if len(password) < 10:
        raise SystemExit("password must be at least 10 characters")
    async with SessionLocal() as s:
        repo = UserRepository(s)
        if await repo.email_exists(email):
            raise SystemExit("user already exists")
        await repo.add(User(email=email.lower(), password_hash=hash_password(password), full_name=name, role="admin",
                            daily_request_limit=10**6, daily_token_limit=10**9))
    print("admin created")


def show_providers():
    print("ACTIVE:", json.dumps(Providers(settings).describe(), indent=2))
    print("AVAILABLE:", json.dumps({k: available(k) for k in ("llm", "vlm", "embedding", "reranker", "vectorstore", "ocr")},
                                   indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    sub.add_parser("providers")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--password", required=True)
    a.add_argument("--name", default="Admin")
    args = p.parse_args()
    if args.cmd == "init-db":
        asyncio.run(init_db())
    elif args.cmd == "providers":
        show_providers()
    else:
        asyncio.run(create_admin(args.email, args.password, args.name))


if __name__ == "__main__":
    main()
