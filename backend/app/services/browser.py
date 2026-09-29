"""内置浏览器：跑真实 Chrome 完成网页人机验证（有窗口但不可见）。

为什么不用 headless：
    佩奇用的 Cap 验证带 `instrumentation` 协议，会识别无头环境——实测
    `headless: true` 时页面里的 cap-widget 不产出 captcha_token，验证直接卡住。
    所以必须跑「真实窗口」：浏览器以为自己在正常显示器上，指纹完整。

窗口怎么藏：
    通过 CDP 的 `Browser.setWindowBounds { windowState: 'minimized' }` 把窗口收起来。
    （试过屏幕外坐标 --window-position=-32000，会让 Chrome 挂起渲染进程，页面被关掉。）

服务器没有桌面怎么办：
    Linux 且没有 DISPLAY 时，用 Xvfb 造一块虚拟屏幕，Chrome 照样有屏幕可用。
    macOS/Windows 本身有显示，跳过这一步。

与前端的配合：
    CPU 密集的是浏览器本身，所以这里的 Node 脚本负责页面内解题与提交；
    Python 侧只做环境准备、并发控制与结果解析。
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import time
from typing import Any, Optional

import logging

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parents[3]
SOLVER_SCRIPT = ROOT / "frontend" / "scripts" / "peiqi_web_solve.mjs"
XVFB_DISPLAY = ":99"


class BrowserService:
    """内置浏览器的唯一入口：环境自检 + 打开 URL 完成验证。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._display: Optional[subprocess.Popen] = None

    # ---------------- 环境 ----------------

    def environment(self) -> dict:
        """自检浏览器环境。装机后先看这里，比盲目跑一次省时间。"""
        chromium_present = self._playwright_chromium()
        return {
            "os": platform.system(),
            "node": shutil.which("node") or "",
            "chrome": shutil.which("google-chrome")
            or shutil.which("google-chrome-stable")
            or shutil.which("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            or "",
            "xvfb": shutil.which("Xvfb") or "",
            "display": os.environ.get("DISPLAY", ""),
            "need_xvfb": platform.system() == "Linux" and not os.environ.get("DISPLAY"),
            "playwright_chromium": chromium_present,
            "solver_script": str(SOLVER_SCRIPT) if SOLVER_SCRIPT.exists() else "",
            "headless_capable": False,
            "ready": bool(
                shutil.which("node")
                and SOLVER_SCRIPT.exists()
                and (
                    shutil.which("google-chrome")
                    or shutil.which("google-chrome-stable")
                    or chromium_present
                    or platform.system() == "Darwin"
                )
            ),
            "install_hint": "bash scripts/install_browser.sh",
            "note": "真实窗口 + 最小化；Linux 无桌面时自动用 Xvfb。纯无头会被 Cap 拦掉。",
        }

    @staticmethod
    def _playwright_chromium() -> str:
        """Playwright 自带 Chromium 的路径（作为系统 Chrome 的兜底）。"""
        candidates = [
            pathlib.Path.home() / "Library/Caches/ms-playwright",
            pathlib.Path.home() / ".cache/ms-playwright",
        ]
        for base in candidates:
            if base.exists():
                for child in base.iterdir():
                    if child.name.startswith("chromium"):
                        return str(child)
        return ""

    def ensure_display(self) -> str:
        """确保浏览器有「屏幕」可用；Linux 无桌面时起 Xvfb 并返回 DISPLAY。"""
        if platform.system() != "Linux":
            return os.environ.get("DISPLAY", "")
        if os.environ.get("DISPLAY"):
            return os.environ["DISPLAY"]
        if self._display is not None and self._display.poll() is None:
            return XVFB_DISPLAY
        if shutil.which("Xvfb") is None:
            logger.warning("浏览器环境缺少 Xvfb，网页验证会在打开阶段失败：bash scripts/install_browser.sh")
            return ""
        self._display = subprocess.Popen(
            ["Xvfb", XVFB_DISPLAY, "-screen", "0", "1280x800x24"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
        os.environ["DISPLAY"] = XVFB_DISPLAY
        logger.info("内置浏览器已启动虚拟显示 %s（服务器无桌面）", XVFB_DISPLAY)
        return XVFB_DISPLAY

    # ---------------- 解题 ----------------

    async def solve(self, url: str, *, timeout: int = 240, visible: bool = False) -> dict[str, Any]:
        """打开 URL，让页面里的 widget 自动完成验证，返回结构化结果。

        串行执行：一个浏览器实例同时只服务一个验证请求——并发开多个只会互相抢内存，
        而且验证本身有 180 秒时限，排队比抢占更稳。
        """
        if not SOLVER_SCRIPT.exists():
            return {"ok": False, "error": f"缺少浏览器脚本：{SOLVER_SCRIPT}"}
        if not shutil.which("node"):
            return {"ok": False, "error": "缺少 node，请先跑 bash scripts/install_browser.sh"}

        async with self._lock:
            display = await asyncio.to_thread(self.ensure_display)
            env = dict(os.environ)
            if display:
                env["DISPLAY"] = display
            url_file = pathlib.Path("/tmp/peiqi_solve_url.txt")
            url_file.write_text(url, encoding="utf-8")

            command = ["node", str(SOLVER_SCRIPT), str(url_file)]
            if visible:
                command.append("--visible")
            working_dir = str(SOLVER_SCRIPT.parent.parent)

            started = time.monotonic()
            try:
                completed = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": f"浏览器阶段超时（{timeout}s）", "elapsed": timeout}

            output = completed.stdout or ""
            verify_body = ""
            for line in output.splitlines():
                if "[验证响应]" in line or "[主动提交]" in line:
                    match = re.search(r"(\{.*\})", line)
                    if match:
                        verify_body = match.group(1)
            passed = "PASSED" in output or '"ok":true' in verify_body.replace(" ", "")

            return {
                "ok": passed,
                "elapsed": round(time.monotonic() - started, 1),
                "verify_response": verify_body or None,
                "browser": next(
                    (line.split("]", 1)[1].strip() for line in output.splitlines() if line.startswith("[浏览器]")),
                    "",
                ),
                "window": next(
                    (line.split("]", 1)[1].strip() for line in output.splitlines() if line.startswith("[窗口]")),
                    "",
                ),
                "log": output.splitlines()[-6:],
                "error": None if passed else (verify_body or "验证未通过，详见 log"),
            }

    def shutdown(self) -> None:
        if self._display is not None and self._display.poll() is None:
            self._display.terminate()
            self._display = None


browser_service = BrowserService()
