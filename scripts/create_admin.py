"""创建 / 重置控制台管理员。

用法：
    cd backend && .venv/bin/python ../scripts/create_admin.py --username admin --password 'xxx'
不带参数时读取 BOOTSTRAP_ADMIN_USERNAME / BOOTSTRAP_ADMIN_PASSWORD。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import dispose_engine, session_scope  # noqa: E402
from app.models import User, UserRole  # noqa: E402
from app.security import hash_password  # noqa: E402


async def upsert_admin(username: str, password: str, display_name: str = "管理员") -> None:
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                display_name=display_name,
                password_hash=hash_password(password),
                role=UserRole.admin,
                is_active=True,
            )
            session.add(user)
            print(f"[create_admin] 已创建管理员 {username}")
        else:
            user.password_hash = hash_password(password)
            user.role = UserRole.admin
            user.is_active = True
            print(f"[create_admin] 已重置管理员 {username} 的口令")


async def main() -> None:
    parser = argparse.ArgumentParser(description="创建或重置控制台管理员")
    parser.add_argument("--username", default=settings.bootstrap_admin_username)
    parser.add_argument("--password", default=settings.bootstrap_admin_password)
    parser.add_argument("--display-name", default="管理员")
    args = parser.parse_args()

    if not args.password:
        print("错误：请通过 --password 或 BOOTSTRAP_ADMIN_PASSWORD 提供口令", file=sys.stderr)
        raise SystemExit(2)

    try:
        await upsert_admin(args.username, args.password, args.display_name)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
