"""清理测试数据：把整套控制台恢复成「刚部署完、只有管理员账号」的状态。

用途：验收脚本、开发调试会往库里塞大量假账号 / 假任务 / 假审计，
准备导入真实账号之前用它清一遍。

用法：

    cd backend
    .venv/bin/python -m scripts.purge_test_data            # 只看会删什么（dry-run）
    .venv/bin/python -m scripts.purge_test_data --yes      # 真的删

保留：`users`（登录账号）默认保留，加 `--purge-users` 连用户一起清（会连管理员一起删，慎用）。
顺带清 Redis 里本项目的键（心跳 / 节流计数 / 任务事件流），否则页面会显示不存在的号的心跳。

注意：这是**不可回滚**的删除。执行前建议先备份：
`make backup` 或 `pg_dump`（见 deploy/postgres-backup.md）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.db import SessionFactory
from app.redis_client import get_redis

#: 按删除顺序排列（先删有外键引用的子表）
TABLES = (
    "messages",
    "dialogs",
    "leases",
    "tasks",
    "account_assignments",
    "account_imports",
    "group_members",
    "group_events",
    "group_profiles",
    "materials",
    "notifications",
    "reply_drafts",
    "relay_links",
    "relay_routes",
    "bots",
    "metrics_samples",
    "audit_logs",
    "tg_accounts",
    "proxies",
    "account_groups",
)
USER_TABLE = "users"
REDIS_PATTERN = "tgcc:*"


async def count_rows(session, table: str) -> int:
    return int((await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar() or 0)


async def main() -> int:
    parser = argparse.ArgumentParser(description="清理测试数据，保留管理员账号")
    parser.add_argument("--yes", action="store_true", help="确认执行（不加只做 dry-run）")
    parser.add_argument("--purge-users", action="store_true", help="连登录用户一起清（慎用）")
    args = parser.parse_args()

    async with SessionFactory() as session:
        before = {table: await count_rows(session, table) for table in TABLES}
        users_before = await count_rows(session, USER_TABLE)

        print("将清理的表：")
        total = 0
        for table, count in before.items():
            if count:
                print(f"  {table:<22} {count:>7}")
                total += count
        print(f"  {'合计':<20} {total:>7}")
        print(f"  保留 {USER_TABLE:<17} {users_before:>7}" + ("（--purge-users 会一起清）" if args.purge_users else ""))

        if not args.yes:
            print("\n这是 dry-run。确认无误后加 --yes 执行；建议先 `make backup`。")
            return 0

        if total == 0 and not args.purge_users:
            print("\n没有需要清理的数据。")
            return 0

        # 用 TRUNCATE ... CASCADE 一次清干净，并重置自增（没有自增列，但保持语义一致）
        targets = ", ".join(TABLES)
        await session.execute(text(f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE"))
        if args.purge_users:
            await session.execute(text(f"TRUNCATE TABLE {USER_TABLE} RESTART IDENTITY CASCADE"))
        await session.commit()

        after = {table: await count_rows(session, table) for table in TABLES}
        remaining = sum(after.values())
        print(f"\n已清理 {total} 行；剩余业务数据 {remaining} 行")
        if args.purge_users:
            print(f"登录用户已清空（{users_before} 个）——记得用 make create-admin 重建管理员")
        else:
            print(f"登录用户保留 {await count_rows(session, USER_TABLE)} 个")

    # Redis：本项目自己的键（心跳 / 节流计数 / 任务事件流）
    try:
        redis = get_redis()
        removed = 0
        async for key in redis.scan_iter(match=REDIS_PATTERN, count=500):
            await redis.delete(key)
            removed += 1
        print(f"已清理 Redis 键（{REDIS_PATTERN}）{removed} 个")
    except Exception as exc:  # noqa: BLE001 - Redis 不可用不影响库清理结果
        print(f"Redis 清理跳过：{exc}")

    print("\n完成。下一步：账号管理 → 批量导入（或登录向导）导入真实账号。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
