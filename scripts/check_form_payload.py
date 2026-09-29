#!/usr/bin/env python3
"""检查前端表单控件是否都会提交（防止「填了不生效」）。

背景：页面上控件（`name="xxx"`）如果没被 `buildPayload` 读取（`values.xxx`），
用户填了也不会进 payload，任务按默认值跑——这类缺陷只靠点页面很难发现，
但静态交叉比对一眼就能揪出来（v0.3.88 就是这么发现两处问题的）。

    python3 scripts/check_form_payload.py            # 检查触达中心表单
    python3 scripts/check_form_payload.py --all      # 扫描所有页面

退出码：0 = 全部对上；1 = 存在「有控件但没提交」的字段。
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

#: 这些是范围/分页字段，由 scopePayload 统一处理，不算漏
SKIP = {"account_ids", "scope", "limit", "group_id", "page", "page_size"}


def check_file(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    # 有些弹窗用 payload[key] 遍历构造（如改资料弹窗），模式不同但字段确实提交了，
    # 这类写法直接放行，避免误报
    if "payload[" in text or "Object.keys(payload)" in text:
        return []
    names = {n for n in re.findall(r'name="([a-z_]+)"', text)}
    reads = set(re.findall(r"values\.([a-z_]+)", text))
    return sorted((names - reads) - SKIP)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查表单控件是否都会提交")
    parser.add_argument("--all", action="store_true", help="扫描 frontend/src 下所有页面与组件")
    args = parser.parse_args()

    root = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src"
    if args.all:
        targets = sorted(list(root.rglob("*.tsx")))
    else:
        targets = [root / "pages" / "Campaigns.tsx"]

    problems = 0
    for target in targets:
        if not target.is_file():
            continue
        missing = check_file(target)
        if missing:
            problems += 1
            print(f"❌ {target.relative_to(root)}：有控件但没提交 → {missing}")
    if problems:
        print(f"\n共 {problems} 个文件存在「填了不生效」的字段。")
        return 1
    print("✅ 所有表单控件的字段都进了 payload。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
