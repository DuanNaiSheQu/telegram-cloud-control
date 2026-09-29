"""批量运营 schema：批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 批量改资料 / 吵群 / 拟人发言。

这些能力从「营销中心」页面发起，按「一个号一条任务」落 `tasks` 表，
`payload.batch_id` 把同一次提交聚合成一个批次，批次进度在 `/campaigns/batches` 查。

设计约束：
- 每个请求体都带账号选择器（复用 BulkScopeRequest），operator 的 all 只覆盖分配给他的号；
- 文本 / 资料支持「一池多文」：texts 按账号序号取模分配，让不同号说的话不一样；
- 吵群 / 拟人发言的轮数与间隔有硬上限（见 config），提交时校验，不让任务无限跑。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import settings
from app.schemas.bulk import BulkScopeRequest
from app.services.username import normalize_username, validate_username
from app.schemas.common import ORMModel
from app.models.material import MaterialKind

#: 吵群 / 拟人发言的文本池上限（防 payload 无限膨胀）
MAX_TEXT_POOL = 100
#: 每个文本最长字节数（Telegram 单条上限 4096，这里留校验余量）
MAX_TEXT_LEN = 4000


# ---------------- 公共校验 ----------------

def _validate_texts(texts: Optional[List[str]]) -> List[str]:
    if not texts:
        return []
    cleaned = [str(item).strip() for item in texts[:MAX_TEXT_POOL]]
    cleaned = [item for item in cleaned if item]
    if not cleaned:
        return []
    for item in cleaned:
        if len(item.encode("utf-8")) > MAX_TEXT_LEN:
            raise ValueError(f"文本过长：单条最多 {MAX_TEXT_LEN} 字节")
    return cleaned


def _validate_targets(targets: Optional[List[str]]) -> List[str]:
    if not targets:
        return []
    cleaned = list(dict.fromkeys(str(item).strip() for item in targets if str(item).strip()))
    if len(cleaned) > 100:
        raise ValueError("目标列表最多 100 个")
    return cleaned


class _TextPoolMixin(BaseModel):
    """text（所有号同一句）或 texts（按号取模分配），至少给一个。"""

    text: Optional[str] = Field(default=None, description="所有号发送同一段文本")
    texts: Optional[List[str]] = Field(default=None, description="文本池：按账号顺序取模分配，最多 100 条")
    naturalize: bool = Field(
        default=False, description="发送前做轻度口语化（标点、语气词微调），让话更像真人"
    )

    @model_validator(mode="after")
    def _check_text(self):
        if not self.text and not self.texts:
            raise ValueError("text 与 texts 至少要给一个")
        if self.text:
            if len(str(self.text).encode("utf-8")) > MAX_TEXT_LEN:
                raise ValueError(f"文本过长：单条最多 {MAX_TEXT_LEN} 字节")
        self.texts = _validate_texts(self.texts)
        return self


# ---------------- 批量私信 ----------------

class BulkPmRequest(BulkScopeRequest, _TextPoolMixin):
    targets: List[str] = Field(default_factory=list, description="私信目标：@username / 手机号 / 数字 user_id")
    min_interval: float = Field(default=3.0, ge=1, le=60, description="同一号每两个目标之间的最小间隔（秒）")
    max_interval: float = Field(default=8.0, ge=1, le=120, description="同一号每两个目标之间的最大间隔（秒）")
    material_id: Optional[uuid.UUID] = Field(
        default=None,
        description="可选：附带素材（图片/视频/文档），文本会作为配文一起发；不填则只发文本",
    )

    @model_validator(mode="after")
    def _check_targets(self):
        self.targets = _validate_targets(self.targets)
        if not self.targets:
            raise ValueError("targets 不能为空")
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval 不能小于 min_interval")
        return self


# ---------------- 群发 / 素材群发 ----------------

class GroupBroadcastRequest(BulkScopeRequest, _TextPoolMixin):
    target_group: str = Field(description="目标群：@username / 数字 chat_id / 会话 dialog_id")
    material_id: Optional[uuid.UUID] = Field(
        default=None,
        description="可选：附带素材（图片/视频/文档），文本会作为配文一起发；不填则只发文本",
    )


class MaterialSendRequest(BulkScopeRequest):
    material_id: uuid.UUID = Field(description="素材库里的素材")
    target_group: Optional[str] = Field(default=None, description="目标群：@username / chat_id / dialog_id")
    targets: Optional[List[str]] = Field(default=None, description="私信目标列表（不给 target_group 时逐个发）")
    min_interval: float = Field(default=3.0, ge=1, le=60)
    max_interval: float = Field(default=8.0, ge=1, le=120)

    @model_validator(mode="after")
    def _check_target(self):
        self.targets = _validate_targets(self.targets)
        if not self.target_group and not self.targets:
            raise ValueError("target_group 与 targets 至少要给一个")
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval 不能小于 min_interval")
        return self


# ---------------- 加群 / 退群 / 强拉 ----------------

class JoinGroupRequest(BulkScopeRequest):
    """批量加群：一次可给多个群，群与账号之间按 dispatch 决定怎么配对。"""

    target: Optional[str] = Field(default=None, description="单个群：邀请链接（t.me/+...）或公开群 @username")
    targets: Optional[List[str]] = Field(
        default=None, description="多个群（每行一个，最多 50 个）；与 target 二选一，同时给则合并"
    )

    @model_validator(mode="after")
    def _merge_targets(self):
        merged = [str(item).strip() for item in (self.targets or []) if str(item).strip()]
        if self.target and str(self.target).strip():
            merged.insert(0, str(self.target).strip())
        merged = list(dict.fromkeys(merged))
        if not merged:
            raise ValueError("至少给一个群：邀请链接或 @公开群")
        if len(merged) > 50:
            raise ValueError("单次最多 50 个群，请分批")
        self.targets = merged
        return self


class LeaveGroupRequest(BulkScopeRequest):
    target: Optional[str] = Field(default=None, description="单个群：@username / 数字 chat_id / 会话 dialog_id")
    targets: Optional[List[str]] = Field(default=None, description="多个群（每行一个，最多 50 个）；与 target 二选一")
    delete_history: bool = Field(default=True, description="退出后同时删除该会话记录")

    @model_validator(mode="after")
    def _merge_targets(self):
        merged = [str(item).strip() for item in (self.targets or []) if str(item).strip()]
        if self.target and str(self.target).strip():
            merged.insert(0, str(self.target).strip())
        merged = list(dict.fromkeys(merged))
        if not merged:
            raise ValueError("至少给一个群")
        if len(merged) > 50:
            raise ValueError("单次最多 50 个群，请分批")
        self.targets = merged
        return self


class ForceAddRequest(BulkScopeRequest):
    group: Optional[str] = Field(
        default=None, description="单个目标群：@username / 数字 chat_id / 会话 dialog_id（执行号须为该群管理员）"
    )
    groups: Optional[List[str]] = Field(
        default=None, description="多个目标群（每行一个，最多 20 个）；与 group 二选一，同时给则合并"
    )
    members: List[str] = Field(description="要拉进群的成员：@username / 手机号 / 数字 user_id，最多 50 个")

    @model_validator(mode="after")
    def _merge_groups(self):
        merged = [str(item).strip() for item in (self.groups or []) if str(item).strip()]
        if self.group and str(self.group).strip():
            merged.insert(0, str(self.group).strip())
        merged = list(dict.fromkeys(merged))
        if not merged:
            raise ValueError("至少给一个目标群")
        if len(merged) > 20:
            raise ValueError("单次最多 20 个群，请分批")
        self.groups = merged
        return self

    @model_validator(mode="after")
    def _check_members(self):
        self.members = _validate_targets(self.members)
        if not self.members:
            raise ValueError("members 不能为空")
        if len(self.members) > 50:
            raise ValueError("单次最多强拉 50 个成员")
        return self


# ---------------- 批量改资料 ----------------

class ProfileFields(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    # 头像直接选素材库里的图片（与 photo_url 二选一）
    photo_material_id: Optional[uuid.UUID] = None

    @field_validator("username")
    @classmethod
    def _check_username(cls, value):
        """用户名先清洗再校验：`@woieduanai`、`t.me/woieduanai` 都会被整理成 `woieduanai`。

        不清洗的话会原样发给 Telegram，然后报「用户名不合法」——但其实是多了个 @，
        运营同学很难从那句话里看出来。
        """
        if value in (None, ""):
            return None
        try:
            return validate_username(str(value))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    def clean(self) -> Dict[str, Any]:
        # UUID（例如 photo_material_id）要转成字符串才能进 JSONB 载荷
        return {
            key: (str(value) if isinstance(value, uuid.UUID) else value)
            for key, value in self.model_dump().items()
            if value not in (None, "")
        }


class ProfileBulkRequest(BulkScopeRequest):
    """批量改资料：三种玩法，按需组合。

    1. **统一**：`profile` 填一份，所有号改成一样；
    2. **按号指定**：`per_account` 按账号 id 单独覆盖（谁用哪个名字说得清）；
    3. **池化随机**：`*_pool` 给一组候选，每个号按 `assign_mode` 取一个——
       一批号资料完全一致是明显的批量特征，池化能让每个号长得不一样。
    """

    profile: ProfileFields = Field(default_factory=ProfileFields, description="所有号统一的资料（留空字段不改）")
    per_account: Optional[Dict[uuid.UUID, ProfileFields]] = Field(
        default=None, description="按账号覆盖（键是账号 id），只对列出的号生效"
    )
    # ---- 池化随机 ----
    first_name_pool: Optional[List[str]] = Field(default=None, description="名字候选池，每行一个")
    last_name_pool: Optional[List[str]] = Field(default=None, description="姓氏候选池，每行一个")
    bio_pool: Optional[List[str]] = Field(default=None, description="简介候选池，每行一个")
    assign_mode: str = Field(
        default="sequence",
        description="池化取值方式：sequence=按账号顺序轮流取（同批不重复）；random=每个号随机取一个",
    )
    # ---- 用户名批量：@username 全局唯一，用「前缀 + 随机数字」更实际 ----
    username_prefix: Optional[str] = Field(default=None, description="用户名前缀；实际写入 前缀+随机数字")
    username_random_digits: int = Field(default=4, ge=2, le=8, description="用户名后缀随机数字位数")

    @field_validator("per_account")
    @classmethod
    def _cap_per_account(cls, value):
        if value is None:
            return value
        if len(value) > 200:
            raise ValueError("per_account 最多 200 个条目")
        return value


# ---------------- 吵群 / 拟人发言 ----------------

class _ChatLoopBase(BulkScopeRequest):
    """吵群与拟人发言的公共参数：目标会话 + 轮数 + 间隔（有硬上限）。"""

    dialog_id: Optional[uuid.UUID] = Field(default=None, description="会话 id（已同步的群）")
    group: Optional[str] = Field(default=None, description="或直接给群：@username / 数字 chat_id")
    rounds: int = Field(default=5, ge=1, le=settings.campaign_max_rounds)
    min_interval: float = Field(default=8.0, ge=settings.campaign_min_interval_seconds,
                                le=settings.campaign_max_interval_seconds)
    max_interval: float = Field(default=30.0, ge=settings.campaign_min_interval_seconds,
                                le=settings.campaign_max_interval_seconds)

    @model_validator(mode="after")
    def _check(self):
        if not self.dialog_id and not self.group:
            raise ValueError("dialog_id 与 group 至少要给一个")
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval 不能小于 min_interval")
        # 总时长上限：任务执行太久会被 Worker 的僵尸回收误伤
        if self.rounds * self.max_interval > settings.campaign_max_duration_seconds:
            raise ValueError(
                f"总时长超限：rounds × max_interval 不能超过 {settings.campaign_max_duration_seconds} 秒"
            )
        return self


class StormRequest(_ChatLoopBase):
    texts: List[str] = Field(description="吵群文本池：每轮随机挑一条，最多 100 条")
    reply_probability: float = Field(
        default=0.0, ge=0, le=1, description="每轮对群内最近一条消息进行回复的概率（更像对话）"
    )

    @model_validator(mode="after")
    def _check_texts(self):
        self.texts = _validate_texts(self.texts)
        if not self.texts:
            raise ValueError("吵群文本池不能为空")
        return self


class PersonaRequest(_ChatLoopBase):
    persona: str = Field(description="人设：给 AI 的角色设定（语气、身份、说话习惯）")
    topic: Optional[str] = Field(default=None, description="发言围绕的话题；不给则由 AI 看群里在聊什么")
    use_ai: bool = Field(default=True, description="true 用 AI 生成话术；false 或 AI 未配置时退回 texts 池")
    texts: Optional[List[str]] = Field(default=None, description="AI 不可用时的备用文本池")

    @model_validator(mode="after")
    def _check_texts(self):
        self.texts = _validate_texts(self.texts)
        return self


# ---------------- 批次聚合 ----------------

class CampaignBatchItem(BaseModel):
    account_id: Optional[uuid.UUID] = None
    account_label: str = ""
    task_id: uuid.UUID
    type: str
    type_label: str = ""
    status: str
    status_label: str = ""
    attempts: int = 0
    error: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class CampaignBatchOut(BaseModel):
    batch_id: uuid.UUID
    created_at: Optional[datetime] = None
    created_by_name: Optional[str] = None
    total: int = 0
    counts: Dict[str, int] = Field(default_factory=dict)
    items: List[CampaignBatchItem] = Field(default_factory=list)


class CampaignBatchListResponse(BaseModel):
    items: List[CampaignBatchOut]
    total: int
    page: int = 1
    page_size: int = 20


# ---------------- 素材 ----------------

class MaterialCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="素材名（便于识别，例如：八月活动话术）")
    kind: MaterialKind = MaterialKind.text
    text: Optional[str] = Field(default=None, description="文字内容；媒体素材可作为 caption")
    file_name: Optional[str] = Field(default=None, description="已上传文件的存储名（由上传接口回填）")

    @model_validator(mode="after")
    def _check(self):
        if self.kind == MaterialKind.text and not (self.text or "").strip():
            raise ValueError("文字素材必须给 text")
        return self


class MaterialOut(ORMModel):
    id: uuid.UUID
    name: str
    kind: MaterialKind
    kind_label: str = ""
    text: str = ""
    file_name: Optional[str] = None
    original_name: Optional[str] = None
    size_bytes: int = 0
    mime_type: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None


class MaterialListResponse(BaseModel):
    items: List[MaterialOut]
    total: int
    page: int = 1
    page_size: int = 20
