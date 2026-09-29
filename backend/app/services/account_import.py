"""账号矩阵导入：手机号清单 / Telethon StringSession / .session 文件 / Telegram Desktop tdata。

四种来源的解析都在这里，统一产出 `ParsedAccount`，再由 `import_accounts()` 落库：

| 来源 | 输入 | 说明 |
|---|---|---|
| `phone` | 文本清单（每行一个号，可带备注） | 建档后走验证码登录，不写会话 |
| `session_string` | Telethon StringSession 串 | 直接解析校验后加密入库 |
| `session_file` | `.session`（Telethon / Pyrogram SQLite） | 读 auth_key + dc_id 组装成 StringSession |
| `tdata` | Telegram Desktop 的 tdata 目录（zip） | 需要可选依赖 `opentele2`，未安装时明确报错并给替代路径 |

设备指纹：每个号在建档时随机生成一套（机型 / 系统 / 客户端版本 / 语言），
避免「几百个号用同型号同版本」这种一眼假的批量特征。
"""

from __future__ import annotations

import base64
import io
import logging
import pathlib
import random
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import security
from app.config import settings
from app.core.audit import write_audit
from app.models import AccountImport, AccountStatus, TgAccount

logger = logging.getLogger(__name__)

def _decode_auth_key(value: Any) -> bytes:
    """auth_key 可能是 BLOB（原样）、hex 串或 base64 串，都试着解一遍。"""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    text = str(value or "").strip()
    if not text:
        return b""
    try:
        return bytes.fromhex(text)
    except ValueError:
        pass
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            raw = decoder(text + "=" * (-len(text) % 4))
            if raw:
                return raw
        except Exception:  # noqa: BLE001
            continue
    return b""


#: 手机号：允许 8-15 位数字，前面可带 +，允许空格、横线分隔
PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{6,18}\d$")

#: Telegram 官方 DC 地址（IPv4:443）。Telethon 内部也维护同一份，这里内置一份避免版本差异
DC_ENDPOINTS: dict[int, tuple[str, int]] = {
    1: ("149.154.175.53", 443),
    2: ("149.154.167.51", 443),
    3: ("149.154.175.100", 443),
    4: ("149.154.167.91", 443),
    5: ("91.108.56.130", 443),
}

#: 设备指纹池：安卓与 iOS 混排，覆盖主流机型与近几个客户端版本
DEVICE_POOL: list[tuple[str, str, str]] = [
    ("Samsung Galaxy S23", "Android 14", "11.2.0"),
    ("Samsung Galaxy S22", "Android 13", "10.14.5"),
    ("Google Pixel 8", "Android 14", "11.1.1"),
    ("Google Pixel 7", "Android 13", "10.13.2"),
    ("Xiaomi 13 Pro", "Android 13", "10.9.2"),
    ("Xiaomi 12", "Android 12", "9.7.1"),
    ("HUAWEI Mate 60", "Android 12", "10.8.3"),
    ("OnePlus 11", "Android 13", "10.12.0"),
    ("OPPO Find X6", "Android 13", "10.10.1"),
    ("vivo X90", "Android 13", "10.11.0"),
    ("iPhone 15 Pro", "iOS 17.4", "10.9.1"),
    ("iPhone 14", "iOS 16.6", "10.3.2"),
    ("iPhone 13", "iOS 15.7", "9.6.3"),
    ("iPad Air (5th gen)", "iPadOS 16.4", "10.5.0"),
]

LANG_POOL: list[tuple[str, str]] = [
    ("zh", "macos"),
    ("zh", "android"),
    ("en", "ios"),
    ("en", "android"),
]


class ImportError_(RuntimeError):
    """导入解析失败：文案直接给到前端，说明「哪种格式、出了什么问题、怎么修」。"""


@dataclass(slots=True)
class ParsedAccount:
    """一条待导入的账号（解析结果，还没落库）。"""

    source: str                      # phone / session_string / session_file / tdata
    label: str                       # 用于回执展示：脱敏手机号或来源文件名
    phone: Optional[str] = None      # 明文手机号（仅内存里流转，库里存密文）
    session: Optional[str] = None    # Telethon StringSession 串
    dc_id: Optional[int] = None
    tg_user_id: Optional[int] = None
    username: Optional[str] = None
    display_name: str = ""
    # 来源自带的设备信息（tdata 会带，其它来源用随机指纹）
    device_model: Optional[str] = None
    system_version: Optional[str] = None
    app_version: Optional[str] = None
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    two_factor: Optional[str] = None   # 2FA 云口令（可选，导入时留存给后续验证）
    remark: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ImportOutcome:
    """导入落库后的汇总。"""

    batch_id: uuid.UUID
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duplicate: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": str(self.batch_id),
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "duplicate": self.duplicate,
            "results": self.results[:200],
        }


# ---------------- 设备指纹 ----------------

def random_fingerprint(rng: Optional[random.Random] = None) -> dict[str, str]:
    """给一个号生成一套设备指纹。

    默认从**官方真实发布过的客户端版本**里取（`services/official.py` 的 OFFICIAL_CLIENTS）：
    编造出来的 app_version 在服务端看是不存在的版本，反而是异常特征。
    """
    from app.services.official import OFFICIAL_CLIENTS, pick_official_client

    rng = rng or random.Random()
    if OFFICIAL_CLIENTS:
        client = pick_official_client(rng)
        return {
            "device_model": client.device_model,
            "system_version": client.system_version,
            "app_version": client.app_version,
            "lang_code": client.system_lang_code.split("-")[0].lower() or "zh",
            "lang_pack": client.lang_pack,
        }
    model, system, app = rng.choice(DEVICE_POOL)
    lang_code, lang_pack = rng.choice(LANG_POOL)
    return {
        "device_model": model,
        "system_version": system,
        "app_version": app,
        "lang_code": lang_code,
        "lang_pack": lang_pack,
    }


# ---------------- 手机号清单 ----------------

def parse_phone_list(text: str) -> list[ParsedAccount]:
    """每行一个号码，支持 `+12025550143,备注` 或制表符分隔。"""
    accounts: list[ParsedAccount] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [chunk.strip() for chunk in re.split(r"[,\t;]", line) if chunk.strip()]
        phone_raw, remark = parts[0], (parts[1] if len(parts) > 1 else "")
        normalized = normalize_phone(phone_raw)
        if not normalized:
            accounts.append(
                ParsedAccount(source="phone", label=phone_raw[:24], remark=remark, extra={"error": "号码格式不对"})
            )
            continue
        accounts.append(
            ParsedAccount(
                source="phone",
                label=mask_phone(normalized),
                phone=normalized,
                remark=remark,
            )
        )
    if not accounts:
        raise ImportError_("手机号清单是空的：每行一个号码，可写成 `+12025550143,备注`")
    return accounts


def normalize_phone(value: str) -> Optional[str]:
    """去掉空格横线，补 + 号；非法返回 None。"""
    candidate = re.sub(r"[\s\-()]", "", (value or "").strip())
    if not candidate:
        return None
    if not candidate.startswith("+"):
        candidate = f"+{candidate}"
    return candidate if PHONE_RE.match(candidate) else None


def mask_phone(phone: str) -> str:
    """脱敏展示：+12025550143 → +1202****0143。"""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 7:
        return phone or "未知"
    return f"+{digits[:4]}****{digits[-4:]}"


# ---------------- Session 字符串 ----------------

def parse_session_string(raw: str) -> ParsedAccount:
    """校验 Telethon StringSession 串（1BVtsOK… 或 base64 变体）。"""
    value = (raw or "").strip()
    if not value:
        raise ImportError_("Session 串是空的")
    session = load_string_session(value)
    dc_id = _string_session_dc(session)
    return ParsedAccount(
        source="session_string",
        label=f"session:{value[:12]}…",
        session=value,
        dc_id=dc_id,
    )


def parse_session_strings(text: str) -> list[ParsedAccount]:
    """多行 Session 串：每行一个，支持 `session,备注` 或 `手机号,session`。"""
    accounts: list[ParsedAccount] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        value = line
        remark = ""
        phone: Optional[str] = None
        # 逗号分隔时：可能是「手机号,session」或「session,备注」
        if "," in line:
            left, right = [chunk.strip() for chunk in line.split(",", 1)]
            if PHONE_RE.match(re.sub(r"[\s\-()]", "", left)):
                phone, value = normalize_phone(left), right
            else:
                value, remark = left, right
        try:
            parsed = parse_session_string(value)
        except ImportError_ as exc:
            accounts.append(
                ParsedAccount(source="session_string", label=value[:18], extra={"error": str(exc)})
            )
            continue
        parsed.phone = phone
        parsed.remark = remark
        if phone:
            parsed.label = mask_phone(phone)
        accounts.append(parsed)
    if not accounts:
        raise ImportError_("Session 清单是空的：每行一个 StringSession 串")
    return accounts


def load_string_session(value: str):
    """用 Telethon 的 StringSession 解析，失败时给出人话错误。"""
    from telethon.sessions import StringSession

    try:
        return StringSession(value)
    except Exception as exc:  # noqa: BLE001 - Telethon 抛的异常类型不稳定
        raise ImportError_(
            f"Session 串解析失败（{type(exc).__name__}）：请确认是 Telethon StringSession（通常以 1 开头），"
            "或改用 .session 文件导入"
        ) from exc


def _string_session_dc(session: Any) -> Optional[int]:
    """尽力从 StringSession 里拿到 dc_id（拿不到不算错）。"""
    try:
        return int(getattr(session, "dc_id", 0) or 0) or None
    except Exception:  # noqa: BLE001
        return None


# ---------------- .session 文件（Telethon / Pyrogram SQLite） ----------------

def parse_session_file(data: bytes, filename: str = "session") -> ParsedAccount:
    """读 SQLite 会话文件里的 auth_key + dc_id，组装成 Telethon StringSession。"""
    if not data:
        raise ImportError_("会话文件是空的")
    if data[:16].startswith(b"SQLite format 3") is False:
        raise ImportError_("这不是 SQLite 会话文件：.session 应该是 SQLite 数据库（也可能是 tdata 目录，请换对应入口）")

    with tempfile.NamedTemporaryFile(suffix=".session", delete=False) as handle:
        handle.write(data)
        tmp_path = handle.name
    try:
        conn = sqlite3.connect(tmp_path)
        try:
            conn.row_factory = sqlite3.Row
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "sessions" not in tables:
                raise ImportError_("会话文件里没有 sessions 表：确认是 Telethon / Pyrogram 导出的 .session")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
            row = conn.execute("SELECT * FROM sessions ORDER BY rowid DESC LIMIT 1").fetchone()
            if row is None:
                raise ImportError_("会话文件里没有已登录会话")
            auth_key_b64 = row["auth_key"] if "auth_key" in columns else None
            dc_id = int(row["dc_id"]) if ("dc_id" in columns and row["dc_id"] is not None) else 2
            user_id = int(row["user_id"]) if ("user_id" in columns and "user_id" in row.keys()) else None
            api_id = int(row["api_id"]) if ("api_id" in columns and row["api_id"] is not None) else None
            # Telethon 存 BLOB，Pyrogram v1 / 手工导出常见 hex 或 base64
            auth_key = _decode_auth_key(auth_key_b64)
            if len(auth_key) < 8:
                raise ImportError_("会话文件里的 auth_key 无效（长度不对）")
        finally:
            conn.close()
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)

    session_str = build_string_session(auth_key, dc_id)
    return ParsedAccount(
        source="session_file",
        label=f"{pathlib.Path(filename).name}",
        session=session_str,
        dc_id=dc_id,
        tg_user_id=user_id,
        api_id=api_id,
    )


def build_string_session(auth_key: bytes, dc_id: int) -> str:
    """auth_key + dc_id → Telethon StringSession 串。"""
    from telethon.sessions import StringSession

    session = StringSession()
    server_address, port = DC_ENDPOINTS.get(int(dc_id), DC_ENDPOINTS[2])
    session.set_dc(int(dc_id), server_address, port)
    session.auth_key = auth_key
    return session.save()


# ---------------- tdata（Telegram Desktop 目录） ----------------

TDATA_HINT = (
    "导入 tdata 需要可选依赖 opentele2（tdata ⇄ Telethon 会话互转）："
    "`pip install opentele2`（需要能编译 C++ 扩展）。"
    "装不上时的兜底路径：用 Telegram Desktop 导出会话后走「.session 文件」导入，或在手机端用验证码登录。"
)


async def parse_tdata(blob: bytes, filename: str = "tdata.zip") -> list[ParsedAccount]:
    """把 tdata 目录（zip 打包）转成 Telethon 会话。依赖缺失时抛出带指引的错误。"""
    try:
        from opentele.api import UseCurrentSession  # type: ignore
        from opentele.td import TDesktop  # type: ignore
        from opentele.tl import TelegramClient as OpenTeleClient  # type: ignore
    except Exception as exc:  # noqa: BLE001 - 依赖缺失或平台不支持
        raise ImportError_(f"{TDATA_HINT}（当前环境加载失败：{type(exc).__name__}）") from exc

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="tgcc-tdata-"))
    try:
        archive = workdir / "upload.zip"
        archive.write_bytes(blob)
        extract_dir = workdir / "tdata"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive) as zf:
            # tdata 的 zip 可能多包一层目录，统一压平到 extract_dir
            for member in zf.namelist():
                target = extract_dir / pathlib.PurePosixPath(member).name
                if member.endswith("/"):
                    continue
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        tdesk = TDesktop(str(extract_dir))
        if not tdesk.isLoaded():
            raise ImportError_("tdata 加载失败：确认 zip 里是 Telegram Desktop 的 tdata 目录内容（key_datas 与 D877F783D5D3EF8C 之类）")

        accounts: list[ParsedAccount] = []
        # 一个 tdata 可能含多个账号：opentele 的 accounts 列表逐个转
        raw_accounts = list(getattr(tdesk, "accounts", []) or [None])
        for index, account in enumerate(raw_accounts):
            session_path = workdir / f"converted-{index}.session"
            try:
                if account is not None:
                    try:
                        client = await tdesk.ToTelethon(
                            account=account, session=str(session_path), flag=UseCurrentSession
                        )
                    except TypeError:
                        # 老版本 opentele 的 ToTelethon 不接 account 参数：退回单账号转换
                        client = await tdesk.ToTelethon(session=str(session_path), flag=UseCurrentSession)
                else:
                    client = await tdesk.ToTelethon(session=str(session_path), flag=UseCurrentSession)
            except Exception as exc:  # noqa: BLE001 - opentele 的异常类型不稳定
                accounts.append(
                    ParsedAccount(
                        source="tdata",
                        label=f"{pathlib.Path(filename).name}#{index}",
                        extra={"error": f"转换失败：{type(exc).__name__}: {exc}"},
                    )
                )
                continue

            session_str = None
            try:
                session_obj = getattr(client, "session", None)
                if hasattr(session_obj, "save"):
                    session_str = session_obj.save()
            except Exception:  # noqa: BLE001
                session_str = None
            if not session_str and session_path.exists():
                session_str = parse_session_file(session_path.read_bytes(), session_path.name).session

            accounts.append(
                ParsedAccount(
                    source="tdata",
                    label=f"{pathlib.Path(filename).name}#{index}",
                    session=session_str,
                    dc_id=_string_session_dc(getattr(client, "session", None)),
                    extra={"note": "tdata 已转换为 Telethon 会话"},
                )
            )
        if not accounts:
            raise ImportError_("tdata 里没有可转换的已登录账号")
        return accounts
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------- 落库 ----------------

async def import_accounts(
    session: AsyncSession,
    *,
    user_id: Optional[uuid.UUID],
    items: Iterable[ParsedAccount],
    source_kind: str,
    proxy_id: Optional[uuid.UUID] = None,
    group_id: Optional[uuid.UUID] = None,
    remark: str = "",
    start_warmup: bool = True,
) -> ImportOutcome:
    """把解析结果写库：建档 + 设备指纹 + 可选绑定代理/分组，并记录导入批次。"""
    outcome = ImportOutcome(batch_id=uuid.uuid4())
    accounts = list(items)
    outcome.total = len(accounts)
    now = datetime.now(tz=timezone.utc)
    seen_phones: set[str] = set()

    for index, item in enumerate(accounts):
        label = item.label or f"#{index + 1}"
        if item.extra.get("error"):
            outcome.failed += 1
            outcome.results.append(
                {"index": index, "source": item.source, "label": label, "ok": False, "message": item.extra["error"]}
            )
            continue

        # 同批次去重
        if item.phone and item.phone in seen_phones:
            outcome.duplicate += 1
            outcome.results.append(
                {"index": index, "source": item.source, "label": label, "ok": False, "message": "同一批次里重复的号码"}
            )
            continue
        if item.phone:
            seen_phones.add(item.phone)

        # 库里去重：手机号密文可直接比对（同一密钥加密结果一致）
        existing = await _find_existing(session, item)
        if existing is not None:
            outcome.duplicate += 1
            outcome.results.append(
                {
                    "index": index,
                    "source": item.source,
                    "label": label,
                    "ok": False,
                    "message": f"账号已存在（{existing.phone_masked}）",
                    "account_id": str(existing.id),
                }
            )
            continue

        fingerprint = random_fingerprint()
        account = TgAccount(
            phone_enc=security.encrypt_secret(item.phone) if item.phone else None,
            phone_hash=security.short_hash(item.phone) if item.phone else None,
            phone_masked=mask_phone(item.phone) if item.phone else label[:32],
            tg_user_id=item.tg_user_id,
            api_id=item.api_id or (settings.telegram_api_id or None),
            username=item.username,
            display_name=item.display_name or "",
            status=AccountStatus.healthy if item.session else AccountStatus.pending,
            status_reason="" if item.session else "等待验证码登录",
            session_enc=security.encrypt_secret(item.session) if item.session else None,
            authorized_at=now if item.session else None,
            group_id=group_id,
            proxy_id=proxy_id,
            remark=item.remark or remark,
            import_source=item.source,
            import_batch_id=outcome.batch_id,
            device_model=item.device_model or fingerprint["device_model"],
            system_version=item.system_version or fingerprint["system_version"],
            app_version=item.app_version or fingerprint["app_version"],
            lang_code=fingerprint["lang_code"],
            lang_pack=fingerprint["lang_pack"],
            health_score=100 if item.session else 60,
            warmup_started_at=now if start_warmup else None,
        )
        async with session.begin_nested():
            session.add(account)
            await session.flush()
        outcome.succeeded += 1
        outcome.results.append(
            {
                "index": index,
                "source": item.source,
                "label": account.phone_masked,
                "ok": True,
                "message": "已导入并加密保存会话" if item.session else "已建档，等待验证码登录",
                "account_id": str(account.id),
            }
        )

    batch = AccountImport(
        id=outcome.batch_id,
        created_by=user_id,
        source_kind=source_kind,
        total=outcome.total,
        succeeded=outcome.succeeded,
        failed=outcome.failed,
        duplicate=outcome.duplicate,
        proxy_id=proxy_id,
        group_id=group_id,
        results=outcome.results[:500],
        remark=remark[:255],
    )
    session.add(batch)
    await write_audit(
        session,
        action="account.bulk_import",
        user_id=user_id,
        target_type="account_batch",
        target_id=str(outcome.batch_id),
        detail={
            "source_kind": source_kind,
            "total": outcome.total,
            "succeeded": outcome.succeeded,
            "failed": outcome.failed,
            "duplicate": outcome.duplicate,
        },
    )
    await session.flush()
    logger.info(
        "账号导入完成 batch=%s source=%s 成功=%s 失败=%s 重复=%s",
        outcome.batch_id,
        source_kind,
        outcome.succeeded,
        outcome.failed,
        outcome.duplicate,
    )
    return outcome


async def _find_existing(session: AsyncSession, item: ParsedAccount) -> Optional[TgAccount]:
    """去重：优先按 tg_user_id，其次按手机号密文。"""
    if item.tg_user_id:
        found = await session.scalar(select(TgAccount).where(TgAccount.tg_user_id == item.tg_user_id))
        if found is not None:
            return found
    if item.phone:
        # 用确定性哈希比对：密文带随机 IV，拿密文查永远是空
        digest = security.short_hash(item.phone)
        return await session.scalar(select(TgAccount).where(TgAccount.phone_hash == digest))
    return None


__all__ = [
    "DC_ENDPOINTS",
    "DEVICE_POOL",
    "ImportError_",
    "ImportOutcome",
    "ParsedAccount",
    "TDATA_HINT",
    "build_string_session",
    "import_accounts",
    "load_string_session",
    "mask_phone",
    "normalize_phone",
    "parse_phone_list",
    "parse_session_file",
    "parse_session_string",
    "parse_session_strings",
    "parse_tdata",
    "random_fingerprint",
]
