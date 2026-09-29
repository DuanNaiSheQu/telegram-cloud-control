"""验证执行器：把「用真 Chrome 打开验证页」这件事做成跨平台、可自检、可复用的一层。

为什么需要它（这是踩出来的经验）：

1. **Cloudflare Turnstile 识破的是自动化协议，不是浏览器**
   Playwright / patchright 打开时一律 `Widget error`；换成系统真 Chrome 就正常。
   所以这里**不用任何自动化框架**，只做两件事：启动真 Chrome、等待结果。

2. **Turnstile 要求页面"可见"**
   窗口最小化时页面 `visibilityState=hidden`，Turnstile 直接报错。
   所以 Linux 上没有桌面时**必须给一块虚拟屏幕**（Xvfb）——Chrome 以为自己在正常显示器上。

3. **固定 user-data-dir 是稳定性的关键**
   每次新建临时 profile，Cloudflare 看到的是"全新设备"，信誉最低。
   用持久 profile 能带上 cookie、缓存、历史，成功率明显更稳。

4. **链接寿命只有 60 秒**
   所以打开动作要"拿到就开"，不要在前面堆等待。

用法：
    from app.services.verify_runner import verify_runner
    verify_runner.preflight()                    # 上线前自检
    verify_runner.ensure_display()               # Linux 自动起 Xvfb
    verify_runner.open_in_real_chrome(url)       # macOS/Linux 各自的方式
"""

from __future__ import annotations

import logging
import os
import pathlib
import platform
import shutil
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parents[3]
# 持久 profile：不要每次新建，否则 Cloudflare 会把每次访问都当成全新设备
PROFILE_DIR = ROOT / "run" / "chrome-profile"
XVFB_DISPLAY = ":99"
XVFB_SCREEN = "1280x800x24"


class VerifyRunner:
    """跨平台的「真 Chrome 打开」执行器。"""

    def __init__(self) -> None:
        self._xvfb: Optional[subprocess.Popen] = None

    # ---------------- 环境 ----------------

    @property
    def system(self) -> str:
        return platform.system()

    def chrome_path(self) -> str:
        """找真 Chrome。优先 Chrome（指纹最干净），退到 Chromium。"""
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
        ]
        for name in candidates:
            if name.startswith("/"):
                if pathlib.Path(name).exists():
                    return name
                continue
            found = shutil.which(name)
            if found:
                return found
        return ""

    def ensure_display(self) -> str:
        """确保浏览器有「屏幕」可用；Linux 无桌面时起 Xvfb。

        这一步在 Linux 上是必需的：Turnstile 要求页面可见，
        而无头/隐藏窗口都会被判定为异常。
        """
        if self.system != "Linux":
            return os.environ.get("DISPLAY", "")
        if os.environ.get("DISPLAY"):
            return os.environ["DISPLAY"]
        if self._xvfb is not None and self._xvfb.poll() is None:
            return XVFB_DISPLAY

        if shutil.which("Xvfb") is None:
            logger.warning("缺少 Xvfb，Linux 上无法提供可见页面：bash scripts/install_browser.sh")
            return ""

        self._xvfb = subprocess.Popen(
            ["Xvfb", XVFB_DISPLAY, "-screen", "0", XVFB_SCREEN],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
        os.environ["DISPLAY"] = XVFB_DISPLAY
        logger.info("已启动虚拟显示 %s（%s）", XVFB_DISPLAY, XVFB_SCREEN)
        return XVFB_DISPLAY

    def preflight(self) -> dict:
        """上线前自检：缺什么、装什么，一眼看清。"""
        chrome = self.chrome_path()
        needs_xvfb = self.system == "Linux" and not os.environ.get("DISPLAY")
        has_xvfb = bool(shutil.which("Xvfb"))
        profile_ok = True
        try:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        except BaseException:  # noqa: BLE001
            profile_ok = False

        ready = bool(chrome) and profile_ok and (not needs_xvfb or has_xvfb)
        return {
            "system": self.system,
            "chrome": chrome,
            "chrome_ok": bool(chrome),
            "profile_dir": str(PROFILE_DIR),
            "profile_ok": profile_ok,
            "needs_xvfb": needs_xvfb,
            "xvfb": shutil.which("Xvfb") or "",
            "display": os.environ.get("DISPLAY", ""),
            "ready": ready,
            "hint": "" if ready else "bash scripts/install_browser.sh",
            "note": (
                "Turnstile 要求页面可见：Linux 无桌面时靠 Xvfb 提供虚拟屏幕；"
                "固定 profile 提升信誉，别每次新建。"
            ),
        }

    # ---------------- 打开 ----------------

    def open_in_real_chrome(self, url: str, *, bring_to_front: bool = True) -> bool:
        """用系统真 Chrome 打开 URL —— **不经过任何自动化协议**。

        这是整个方案的关键：Turnstile 能识别 Playwright 的 CDP 通道，
        但对系统直接启动的 Chrome 完全正常。
        """
        chrome = self.chrome_path()
        if not chrome:
            logger.warning("找不到 Chrome，请先跑 bash scripts/install_browser.sh")
            return False

        self.ensure_display()
        env = dict(os.environ)
        if self.system == "Linux" and os.environ.get("DISPLAY"):
            env["DISPLAY"] = os.environ["DISPLAY"]

        try:
            if self.system == "Darwin":
                # macOS：必须用**独立实例 + 独立 profile**。
                # 复用已有 Chrome 的话，新链接会开在后台标签里被节流 —— Turnstile 就不跑
                # （实测第三个号就是这么失败的：链接 1.7s 拿到、3.9s 打开，却始终没通过）。
                # 先关掉占用同一 profile 的旧实例，再以新实例打开，保证是前台干净窗口。
                subprocess.run(["pkill", "-f", f"user-data-dir={PROFILE_DIR}"], check=False)
                time.sleep(1.0)
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["open", "-na", "Google Chrome", "--args",
                     f"--user-data-dir={PROFILE_DIR}",
                     "--no-first-run", "--no-default-browser-check", url],
                    check=False, timeout=25,
                )
                time.sleep(1.5)
            else:
                # Linux：直接后台起 Chrome，带上固定 profile
                PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.Popen(
                    [
                        chrome,
                        f"--user-data-dir={PROFILE_DIR}",
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-features=Translate,MediaRouter",
                        url,
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            logger.info("已用真 Chrome 打开验证页")
            return True
        except BaseException as exc:  # noqa: BLE001
            logger.warning("打开 Chrome 失败：%s", exc)
            return False

    def close_all(self) -> None:
        """收尾：Linux 上关掉本进程起的 Chrome 与 Xvfb（避免长期驻留）。"""
        if self.system == "Linux":
            subprocess.run(["pkill", "-f", f"user-data-dir={PROFILE_DIR}"], check=False)
        if self._xvfb is not None and self._xvfb.poll() is None:
            self._xvfb.terminate()
            self._xvfb = None


verify_runner = VerifyRunner()
