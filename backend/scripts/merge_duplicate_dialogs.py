"""合并重复会话：把「同一个群两条记录」并成一条。

背景：频道/超级群的 id 有两种形态（原始 `4337589332` 与完整 `-1004337589332`），
不同同步路径拿到的不一样，历史上会落成两条会话，页面上看起来是「一个群两个对话」。
入库侧已经规范化（`services/chat_id.normalize_chat_id`），这个脚本负责**清理历史数据**。

    cd backend
    .venv/bin/python -m scripts.merge_duplicate_dialogs            # 只看会合并什么（dry-run）
    .venv/bin/python -m scripts.merge_duplicate_dialogs --yes      # 真的合并

合并规则：

- 按「规范化后的 id + 归属（账号 / Bot）」分组，同组只留一条；
- **保留消息更多的那条**（消息一样多时保留会话更新的）；
- 另一条的消息改挂到保留的那条上（`dialog_id` 改写），重复消息（同 `tg_message_id`）直接删；
- 保留记录会补齐缺失的字段（成员数、用户名、标题、最后消息时间与预览）；
- 最后删除多余的会话行。删除不可回滚，执行前建议 `make backup`。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from typing import Optional

from sqlalchemy import func, select, update

from app.db import SessionFactory
from app.models import Dialog, Message
from app.services.chat_id import normalize_chat_id


async def main() -> int:
    parser = argparse.ArgumentParser(description="合并重复会话")
    parser.add_argument("--yes", action="store_true", help="确认执行（不加只做 dry-run）")
    args = parser.parse_args()

    async with SessionFactory() as session:
        dialogs = list((await session.scalars(select(Dialog))).all())
        groups: dict[tuple, list[Dialog]] = defaultdict(list)
        for dialog in dialogs:
            kind = dialog.kind.value if hasattr(dialog.kind, "value") else str(dialog.kind)
            key = (
                normalize_chat_id(dialog.tg_chat_id, kind),
                dialog.channel.value if hasattr(dialog.channel, "value") else str(dialog.channel),
                str(dialog.account_id),
                str(dialog.bot_id),
            )
            groups[key].append(dialog)

        duplicates = {key: rows for key, rows in groups.items() if len(rows) > 1}
        # 顺手把「id 形态不统一」的记录也归一：同一个群只应存在一种 id 写法
        to_fix = [
            row
            for row in dialogs
            if normalize_chat_id(row.tg_chat_id, row.kind.value if hasattr(row.kind, "value") else str(row.kind))
            != row.tg_chat_id
        ]
        if not duplicates:
            if not to_fix:
                print(f"没有重复会话，id 形态也都一致（共 {len(dialogs)} 条）。")
                return 0
            print(f"没有重复会话，但有 {len(to_fix)} 条 id 形态不统一，将归一。")
            if not args.yes:
                for row in to_fix:
                    kind = row.kind.value if hasattr(row.kind, "value") else str(row.kind)
                    print(f"  {str(row.title)[:22]!r}：{row.tg_chat_id} → {normalize_chat_id(row.tg_chat_id, kind)}")
                print("这是 dry-run。确认无误后加 --yes。")
                return 0
            for row in to_fix:
                kind = row.kind.value if hasattr(row.kind, "value") else str(row.kind)
                row.tg_chat_id = normalize_chat_id(row.tg_chat_id, kind)
            await session.commit()
            print(f"完成：归一 {len(to_fix)} 条会话 id。")
            return 0

        plan: list[tuple[Dialog, list[Dialog]]] = []
        total_extra = 0
        for key, rows in duplicates.items():
            counts = {}
            for row in rows:
                counts[row.id] = int(
                    await session.scalar(select(func.count()).select_from(Message).where(Message.dialog_id == row.id)) or 0
                )
            rows.sort(key=lambda row: (counts[row.id], row.last_message_at or row.created_at), reverse=True)
            keep, *drop = rows
            keep_tg_chat_id = key[0]  # 规范化后的 id，合并时统一写回
            plan.append((keep, drop))
            total_extra += len(drop)
            print(
                f"  合并 {key[0]}（{key[1]}）：保留 {str(keep.title)[:22]!r}"
                f"（{counts[keep.id]} 条消息），并入 {len(drop)} 条"
            )

        print(f"\n将合并 {len(plan)} 组，删除 {total_extra} 条重复会话。")
        if not args.yes:
            print("这是 dry-run。确认无误后加 --yes；建议先 make backup。")
            return 0

        moved = removed = 0
        for keep, drop in plan:
            for row in drop:
                # 消息先改挂到保留的会话上；重复消息（同 tg_message_id）删掉
                existing_ids = {
                    value
                    for value in (
                        await session.scalars(
                            select(Message.tg_message_id).where(
                                Message.dialog_id == keep.id, Message.tg_message_id.is_not(None)
                            )
                        )
                    ).all()
                }
                await session.execute(
                    update(Message)
                    .where(Message.dialog_id == row.id, Message.tg_message_id.is_(None))
                    .values(dialog_id=keep.id)
                )
                rows_to_move = list((await session.scalars(select(Message).where(Message.dialog_id == row.id))).all())
                for message in rows_to_move:
                    if message.tg_message_id is not None and message.tg_message_id in existing_ids:
                        await session.delete(message)
                        removed += 1
                    else:
                        message.dialog_id = keep.id
                        moved += 1
                # 补齐保留记录的缺失字段
                keep.tg_chat_id = keep_tg_chat_id
                keep.member_count = keep.member_count or row.member_count
                keep.username = keep.username or row.username
                keep.title = keep.title or row.title
                keep.peer_display = keep.peer_display or row.peer_display
                if (row.last_message_at or row.created_at) and (
                    keep.last_message_at is None or (row.last_message_at or row.created_at) > keep.last_message_at
                ):
                    keep.last_message_at = row.last_message_at
                    keep.last_message_preview = row.last_message_preview or keep.last_message_preview
                await session.delete(row)
        await session.commit()
        print(f"完成：迁移 {moved} 条消息、删除重复消息 {removed} 条、删除多余会话 {total_extra} 条。")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
