"""ORM 模型统一出口。业务表都带操作者归属，方便按人查审计。"""

from __future__ import annotations

from app.models.account import AccountAssignment, AccountGroup, AccountImport, Proxy, TgAccount
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.bot import Bot
from app.models.dialog import Dialog
from app.models.enums import (
    ACCOUNT_STATUS_LABELS,
    CLAIMABLE_STATUSES,
    CURRENT_TASK_LABELS,
    SENDABLE_STATUSES,
    TASK_STATUS_LABELS,
    TASK_TYPE_LABELS,
    AccountStatus,
    CurrentTask,
    DialogChannel,
    DialogKind,
    DraftStatus,
    MessageDirection,
    MessageStatus,
    RelayTargetKind,
    TaskStatus,
    TaskType,
    UserRole,
)
from app.models.group_intel import (
    COLLECT_SOURCE_LABELS,
    COLLECT_SOURCES,
    GROUP_EVENT_LABELS,
    GROUP_EVENT_TYPES,
    GroupEvent,
    GroupMember,
    GroupProfile,
    KeywordWatch,
)
from app.models.message import Message
from app.models.material import MATERIAL_KIND_LABELS, Material, MaterialKind
from app.models.metrics_sample import MetricsSample
from app.models.notification import (
    NOTIFICATION_KIND_LABELS,
    NOTIFICATION_KIND_LEVELS,
    NOTIFICATION_LEVELS,
    Notification,
)
from app.models.relay import RelayLink, RelayRoute, ReplyDraft
from app.models.task import Lease, Task
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "UserRole",
    "TgAccount",
    "AccountGroup",
    "Proxy",
    "AccountAssignment",
    "AccountImport",
    "AccountStatus",
    "ACCOUNT_STATUS_LABELS",
    "CLAIMABLE_STATUSES",
    "SENDABLE_STATUSES",
    "CurrentTask",
    "CURRENT_TASK_LABELS",
    "Bot",
    "Dialog",
    "DialogChannel",
    "DialogKind",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "Task",
    "TaskType",
    "TaskStatus",
    "TASK_TYPE_LABELS",
    "TASK_STATUS_LABELS",
    "Lease",
    "RelayRoute",
    "RelayLink",
    "ReplyDraft",
    "DraftStatus",
    "RelayTargetKind",
    "AuditLog",
    "MetricsSample",
    "Notification",
    "NOTIFICATION_KIND_LABELS",
    "NOTIFICATION_KIND_LEVELS",
    "NOTIFICATION_LEVELS",
    "GroupProfile",
    "GroupMember",
    "GroupEvent",
    "COLLECT_SOURCES",
    "COLLECT_SOURCE_LABELS",
    "GROUP_EVENT_TYPES",
    "GROUP_EVENT_LABELS",
    "Material",
    "MaterialKind",
    "MATERIAL_KIND_LABELS",
]
