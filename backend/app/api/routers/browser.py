"""内置浏览器：环境自检 + 用真实窗口完成网页人机验证。

存在意义：佩奇的 Cap 验证会识别无头浏览器（实测 headless 时 captcha_token 不产出），
所以需要一个「跑真实窗口、但窗口不可见」的浏览器能力。服务器无桌面时它自动用 Xvfb。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.models import User
from app.services.browser import browser_service

router = APIRouter(prefix="/api/browser", tags=["browser"])


class SolveRequest(BaseModel):
    url: str = Field(min_length=10, max_length=2000, description="要打开并完成验证的网页地址")
    visible: bool = Field(default=False, description="调试用：让浏览器窗口显示出来")


@router.get("/status", summary="内置浏览器环境自检")
async def browser_status(user: User = Depends(get_current_user)) -> dict:
    """检查 Chrome / Xvfb / Node / Playwright 是否就绪，以及是否需要安装。"""
    return browser_service.environment()


@router.post("/solve", summary="打开 URL 并自动完成网页人机验证")
async def browser_solve(
    payload: SolveRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """真实窗口（不可见）打开页面，让页面里的 widget 自动解完验证并提交。

    典型用途：佩奇（PeiQiBot）入群验证 —— 拿到 webview 地址后交给它跑完，
    返回 `ok` 与页面的原始响应，便于判断是「验证通过」还是「token 过期」。
    """
    result = await browser_service.solve(payload.url, visible=payload.visible)
    if not result.get("ok") and result.get("error", "").startswith("缺少"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result["error"])
    return result
