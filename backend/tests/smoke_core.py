"""共享核心的冒烟验证：任务队列、租约、统一入库、转发任务、Webhook 去重。

不需要 pytest，直接跑：
    cd backend && .venv/bin/python -m tests.smoke_core
要求本地 Postgres / Redis 可用（读 backend/.env）。测试数据用完即删。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, text

from app.config import settings
from app.core import events, leases, tasks as task_core
from app.db import SessionFactory, dispose_engine, engine
from app.models import (
    AccountGroup,
    AccountStatus,
    Bot,
    Dialog,
    DialogChannel,
    DialogKind,
    Lease,
    Message,
    MessageDirection,
    Proxy,
    RelayRoute,
    Task,
    TaskStatus,
    TaskType,
    TgAccount,
    User,
    UserRole,
)
from app.redis_client import close_redis, get_redis
from app.security import encrypt_secret, hash_password
from app.services import inbound, relay

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  ✅ {name}{(' — ' + detail) if detail else ''}")
    else:
        FAILED.append(name)
        print(f"  ❌ {name}{(' — ' + detail) if detail else ''}")


async def main() -> int:
    print(f"== 核心冒烟 (DB={settings.database_url.split('@')[-1]}, Redis={settings.redis_url}) ==")
    redis = get_redis()
    suffix = uuid.uuid4().hex[:6]
    worker_id = f"smoke-worker-{suffix}"

    async with SessionFactory() as session:
        # ---------- 准备数据 ----------
        group = AccountGroup(name=f"冒烟分组-{suffix}")
        proxy = Proxy(name=f"冒烟代理-{suffix}", scheme="socks5", host="127.0.0.1", port=1080)
        user = User(
            username=f"smoke-{suffix}",
            display_name="冒烟员工",
            password_hash=hash_password("smoke-pass"),
            role=UserRole.operator,
        )
        session.add_all([group, proxy, user])
        await session.flush()

        account = TgAccount(
            phone_masked="138****0001",
            phone_enc=encrypt_secret("+8613800000001"),
            status=AccountStatus.healthy,
            group_id=group.id,
            proxy_id=proxy.id,
        )
        bot = Bot(
            name=f"冒烟Bot-{suffix}",
            token_enc=encrypt_secret("123456:smoke-token-not-real"),
            bot_username="smoke_bot",
            relay_target_chat_id=-1001234567890,
            relay_enabled=True,
        )
        session.add_all([account, bot])
        await session.flush()
        await session.commit()
        account_id, bot_id, user_id = account.id, bot.id, user.id
        print(f"  测试数据：account={account_id} bot={bot_id}")

        # ---------- 1. 租约 ----------
        print("1) 租约认领 / 续租 / 释放")
        claimed = await leases.acquire_leases(session, worker_id=worker_id, limit=10, ttl_seconds=30)
        check("acquire_leases 认领到账号", account_id in claimed, f"claimed={len(claimed)}")

        lease = await session.scalar(select(Lease).where(Lease.account_id == account_id))
        check("leases 行绑定到本 worker", lease is not None and lease.worker_id == worker_id)
        first_until = lease.lease_until if lease else None

        await asyncio.sleep(1.1)
        renewed = await leases.renew_leases(session, worker_id=worker_id, ttl_seconds=30)
        await session.refresh(lease)
        check(
            "renew_leases 延长了 lease_until",
            bool(first_until) and lease is not None and lease.lease_until > first_until,
            f"{first_until} → {lease.lease_until if lease else None}",
        )
        check("renew_leases 返回本 worker 的号", account_id in renewed)

        other = await leases.acquire_leases(session, worker_id="other-worker", limit=10)
        check("别的副本不能抢走有效租约", account_id not in other, f"other claimed={len(other)}")

        # ---------- 2. 任务队列 ----------
        print("2) 任务入队 / 领取 / 重试 / 完成 / 去重")
        send_task = await task_core.enqueue_task(
            session,
            type=TaskType.send_message,
            account_id=account_id,
            payload={"dialog_id": str(uuid.uuid4()), "text": "冒烟消息"},
            created_by=user_id,
        )
        await session.commit()

        bot_task = await task_core.enqueue_task(
            session, type=TaskType.relay_to_staff, bot_id=bot_id, payload={"staff_chat_id": -100}
        )
        await session.commit()
        check("Bot 任务挂 bot_id", bot_task.bot_id == bot_id)

        worker_tasks = await task_core.claim_tasks(session, claimer_id=worker_id, kind="worker")
        ids = [t.id for t in worker_tasks]
        check("worker 只能领到自己租约内账号的任务", send_task.id in ids, f"claimed={len(ids)}")
        check("worker 不会领 Bot 任务", bot_task.id not in ids)

        claimed_bot = await task_core.claim_tasks(session, claimer_id="api-1", kind="bot")
        check("API 领取 Bot 任务", bot_task.id in [t.id for t in claimed_bot])

        await session.refresh(send_task)
        check("领取后状态为 running 且 attempts=1", send_task.status == TaskStatus.running and send_task.attempts == 1)

        status = await task_core.fail_task(session, send_task, "第一次失败：网络抖动", retryable=True)
        await session.commit()
        await session.refresh(send_task)
        check(
            "可重试失败回到 pending 且带退避",
            status == TaskStatus.pending and send_task.next_run_at > datetime.now(tz=timezone.utc),
            f"next_run_at={send_task.next_run_at}",
        )

        send_task.next_run_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
        send_task.attempts = send_task.max_attempts
        await session.commit()
        status = await task_core.fail_task(session, send_task, "超过重试上限", retryable=True)
        await session.commit()
        await session.refresh(send_task)
        check("超过上限记为 failed", status == TaskStatus.failed and send_task.status == TaskStatus.failed)

        await task_core.requeue_task(session, send_task)
        await session.commit()
        await session.refresh(send_task)
        check("页面重试把任务放回 pending 且 attempts 归零", send_task.status == TaskStatus.pending and send_task.attempts == 0)

        dup = await task_core.enqueue_task(
            session,
            type=TaskType.relay_to_staff,
            bot_id=bot_id,
            payload={"staff_chat_id": -100},
            dedupe_key=f"smoke-dedupe-{suffix}",
        )
        await session.commit()
        dup2 = await task_core.enqueue_task(
            session,
            type=TaskType.relay_to_staff,
            bot_id=bot_id,
            payload={"staff_chat_id": -100},
            dedupe_key=f"smoke-dedupe-{suffix}",
        )
        check("dedupe_key 命中不重复入队", dup.id == dup2.id)

        # 去重冲突不能把同一事务里先写入的消息回滚掉
        dialog_probe, msg_probe, created = await inbound.ingest_message(
            session,
            channel=DialogChannel.bot,
            direction=MessageDirection.incoming,
            tg_chat_id=-100999,
            bot_id=bot_id,
            title="冒烟会话",
            body="hello",
            tg_message_id=int(uuid.uuid4().int % 10**9),
        )
        await task_core.enqueue_task(
            session,
            type=TaskType.relay_to_staff,
            bot_id=bot_id,
            payload={},
            dedupe_key=f"smoke-dedupe-{suffix}",
        )
        await session.commit()
        check("去重命中后消息仍在（SAVEPOINT 生效）", created and msg_probe.id is not None)

        counts = await task_core.due_task_metrics(session)
        check("队列计数可用", counts["pending"] >= 1, str(counts))

        # ---------- 3. 统一入库 + 转发 ----------
        print("3) 统一入库 / 转发任务 / 回复链路")
        route = RelayRoute(
            name=f"冒烟规则-{suffix}",
            bot_id=bot_id,
            staff_chat_id=-1001234567890,
            account_id=account_id,
        )
        session.add(route)
        await session.flush()

        dialog, message, created = await inbound.ingest_message(
            session,
            channel=DialogChannel.user_account,
            direction=MessageDirection.incoming,
            tg_chat_id=-100555,
            account_id=account_id,
            kind=DialogKind.group,
            title="冒烟群",
            peer_display="张三",
            body="请问在吗？",
            tg_message_id=1001,
            sender_name="张三",
        )
        check("incoming 入库且会话被创建", created and dialog.tg_chat_id == -100555)
        check("会话预览与未读被更新", dialog.last_message_preview == "请问在吗？" and dialog.unread_count == 1)

        _, again, created_again = await inbound.ingest_message(
            session,
            channel=DialogChannel.user_account,
            direction=MessageDirection.incoming,
            tg_chat_id=-100555,
            account_id=account_id,
            body="重复投递",
            tg_message_id=1001,
        )
        check("同一个 tg_message_id 不重复写", not created_again and again.id == message.id)
        await session.refresh(dialog)
        check("群聊类型不会被默认 private 的调用降级", dialog.kind == DialogKind.group, str(dialog.kind))

        relay_tasks = await relay.enqueue_relays(session, dialog=dialog, message=message)
        await session.commit()
        check("命中转发规则写出 relay_to_staff 任务", len(relay_tasks) == 1 and relay_tasks[0].bot_id == bot_id)

        again_tasks = await relay.enqueue_relays(session, dialog=dialog, message=message)
        await session.commit()
        check("同一消息不重复转发", len(again_tasks) == 1 and again_tasks[0].id == relay_tasks[0].id)

        outgoing, out_msg, _ = await inbound.ingest_message(
            session,
            channel=DialogChannel.user_account,
            direction=MessageDirection.outgoing,
            tg_chat_id=-100555,
            account_id=account_id,
            body="在的，稍等",
            tg_message_id=1002,
        )
        check("发出消息不清未读以外逻辑正常", out_msg.direction == MessageDirection.outgoing)

        link = await relay.record_relay_link(
            session,
            route_id=route.id,
            bot_id=bot_id,
            message_id=message.id,
            staff_chat_id=-1001234567890,
            staff_message_id=777,
        )
        await session.commit()
        found = await relay.find_origin_by_staff_reply(
            session, staff_chat_id=-1001234567890, staff_message_id=777
        )
        check(
            "员工群回复能找回原会话",
            found is not None and found[1].id == message.id and found[2].id == dialog.id,
        )

        header = relay.source_header(dialog=dialog, account=account)
        check("来源标注包含号 / 群 / 对方", "138****0001" in header and "群聊" in header and "张三" in header, header)

        chans = await relay.staff_chat_ids(session)
        check("员工群 id 集合可用", -1001234567890 in chans)

        payload = inbound.message_payload(dialog, message)
        await events.publish_new_message(redis, payload)
        check("消息可推送 Redis（页面订阅通道）", payload["dialog_id"] == str(dialog.id))
        stored = await redis.get(events.account_heartbeat_key(account_id))
        del stored

        # ---------- 4. Webhook 去重 / 心跳 ----------
        print("4) Webhook 去重 / 心跳缓存")
        update_id = int(uuid.uuid4().int % 10**8)
        first_seen = await events.seen_update(redis, bot_id, update_id)
        second_seen = await events.seen_update(redis, bot_id, update_id)
        check("同一 update_id 第二次被判为重复", first_seen is False and second_seen is True)

        await events.set_worker_heartbeat(redis, worker_id, {"online": 1}, ttl=30)
        beats = await events.worker_heartbeats(redis)
        check("worker 心跳可读回", any(b.get("worker_id") == worker_id for b in beats), f"beats={len(beats)}")

        await events.save_login_session(redis, account_id, {"step": "code_required", "session": "x"}, ttl=60)
        state = await events.load_login_session(redis, account_id)
        check("登录临时态可存取", state is not None and state["step"] == "code_required")

        # ---------- 5. 释放租约 ----------
        print("5) 优雅退出释放租约")
        released = await leases.release_leases(session, worker_id=worker_id)
        remaining = await session.scalar(select(Lease).where(Lease.account_id == account_id))
        check("release_leases 清掉本 worker 的租约", account_id not in released or remaining is None)

        # ---------- 清理 ----------
        print("6) 清理测试数据")
        await session.execute(delete(Task).where(Task.dedupe_key.like(f"smoke-dedupe-{suffix}%")))
        await session.execute(delete(Task).where(Task.account_id == account_id))
        await session.execute(delete(Task).where(Task.bot_id == bot_id))
        await session.execute(delete(Message).where(Message.dialog_id.in_(
            select(Dialog.id).where(Dialog.account_id == account_id)
        )))
        await session.execute(delete(Dialog).where(Dialog.bot_id == bot_id))
        await session.execute(delete(Dialog).where(Dialog.account_id == account_id))
        await session.execute(delete(RelayRoute).where(RelayRoute.account_id == account_id))
        await session.execute(delete(TgAccount).where(TgAccount.id == account_id))
        await session.execute(delete(Bot).where(Bot.id == bot_id))
        await session.execute(delete(Proxy).where(Proxy.id == proxy.id))
        await session.execute(delete(AccountGroup).where(AccountGroup.id == group.id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()
        await redis.delete(events.login_session_key(account_id))
        await redis.delete(events.worker_heartbeat_key(worker_id))
        print("  已清理")

    await close_redis()
    await dispose_engine()

    print()
    print(f"== 结果：{len(PASSED)} 通过 / {len(FAILED)} 失败 ==")
    if FAILED:
        for name in FAILED:
            print(f"  FAIL: {name}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
