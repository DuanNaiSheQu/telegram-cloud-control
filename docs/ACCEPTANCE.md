# 验收对照表

把 [规划.md](../规划.md) 的每一条落到具体产物和验证方式上。验证命令都能重跑。

## 0. 本次落地实测记录（可复跑）

| 验证 | 命令 | 结果 |
|---|---|---|
| 共享层冒烟（真实 Postgres 14 + Redis，任务队列/租约/入库/转发/去重） | `cd backend && .venv/bin/python -m tests.smoke_core` | **31/31 通过** |
| AI 服务层（未配置报错、请求形状、Bot 资料进 system、上游报错冒泡） | `cd backend && .venv/bin/python -m tests.smoke_ai` | **12/12 通过** |
| 数据库迁移（全新库升级 / 回滚 / 离线 SQL） | `alembic upgrade head` / `downgrade base` / `upgrade --sql` | 15 表建出、回滚剩版本表、离线 SQL 15 条 CREATE TABLE |
| 端到端验收（API + Worker 双进程，41 项） | `make stack-up && make e2e` | **41 通过 / 0 失败 / 0 跳过** |
| 优雅退出释放租约 | `make stack-down` | worker 日志「已释放 2 个租约，Worker 退出」，`leases` 归零 |
| 前端生产构建 | `cd frontend && npm run build` | ✓ 3066 modules，`dist/` 产出（antd chunk 1.10 MB / gzip 342 kB，零告警） |
| 部署产物静态校验（compose / 告警 / .env / nginx） | `make config-check` | **33/33 通过** |
| 语法与类型检查 | `make check` | Python 编译 + 前端 `tsc --noEmit` 通过 |

集成阶段修掉的真实问题（都有回归验证）：

1. `claim_tasks` 领取任务时 SQL 自增与 ORM 同步叠加，`attempts` 变成 2 → 改为 `synchronize_session=False` + 单点自增。
2. 会话类型被后续「默认 private」的入库调用降级（群聊变私信）→ 群聊类型改为粘性。
3. API 侧 `tgcc_tasks` 与 Worker 侧 `tgcc_tasks_total` 装进同一进程时注册表撞名 → Worker 指标改用独立 `CollectorRegistry`。
4. `PATCH /api/accounts/{id}` 过滤掉 null，导致**代理/分组无法解绑** → 改用 `exclude_unset` 语义（显式 null = 解绑）。
5. 已有账号重新登录必须重填完整手机号 → `login/start` 支持只传 `account_id`，手机号从加密存储解出。
6. 补历史消息会点亮未读角标 → `ingest_message(count_unread=False)`，补录不再算未读。
7. 登录成功后不会自动拉会话 → Worker 登录收尾自动补 `sync_dialogs` 任务。
8. `scripts/stack_local.sh` 的 `$!` 取到脚本自身 PID（`down` 会误杀自己）、macOS 无 `setsid`、bash 3.2 会把 `$VAR` 后紧跟的中文字节吞进变量名 → 三处都修好并复跑通过。
9. 转发记录列表只有 ID → `RelayLinkOut` 回填原消息正文 / 会话名 / 归属号。
10. 缺 `python-socks`（配了代理的号会退化成直连、暴露真实出口 IP）→ 加入 `requirements.txt` 并安装。

## 1. 范围（要做的）

| 规划条目 | 落地产物 | 验证方式 |
|---|---|---|
| 账号列表：状态、分组、心跳、当前任务、单号检测 | `tg_accounts` / `leases` 表，`GET /api/accounts`，`POST /api/accounts/{id}/check`，`app/worker/worker.py` 心跳与 `current_task` 维护 | `scripts/e2e_check.py` 第 3、4 节；`backend/tests/smoke_core.py` 第 1、2 节 |
| 已加入的群聊，以及发给这个号的私信 | `sync_dialogs` / `sync_messages` 任务，`dialogs`、`messages` 表，`app/worker/handlers.py` 监听 `NewMessage` | `backend/tests/smoke_core.py` 第 3 节（入库/去重/未读） |
| 官方 Bot 收到的私信，以及 Bot 所在群里能看到的消息 | `app/api/bots/webhook.py`，`services/inbound.py` | `scripts/e2e_check.py` 第 5 节（Webhook 路由可访问、去重）；真机需 Bot Token |
| 新消息用自己 Bot 转发到指定员工群，员工回复后送回原会话 | `relay_routes` / `relay_links` 表，`services/relay.py`，`app/api/bots/bot_tasks.py`（`relay_to_staff`、`reply_to_origin`） | `backend/tests/smoke_core.py` 第 3 节（命中规则、不重复转发、回复找回原会话）；真机需 Bot Token |
| 用户号上的发送由员工确认后发出 | 控制台发送 → 预写 `messages(pending)` + `send_message` 任务 → Worker 发出后回填 `tg_message_id` | `scripts/e2e_check.py` 第 4、5 节；`app/worker/task_runner.py` 里「非 healthy 不发送」分支 |
| 官方 Bot 按自己的资料自动回复，身份是 Bot | `bots.persona_text` + `bot_reply` 任务 + `services/ai.bot_auto_reply` | `backend/tests/smoke_ai.py`（资料进 system、身份是 Bot） |
| AI 草稿停在输入框，员工点发送才出去 | `reply_drafts` 表，`POST /api/dialogs/{id}/draft`、`POST /api/messages/send`（带 `draft_id`），审计记录 `sent_by` | `backend/tests/smoke_ai.py`（草稿生成）；`scripts/e2e_check.py` 第 5 节 |
| 单个号在设置里改自己的名称和头像 | `update_profile` 任务 + `app/worker/task_runner.py` | 任务载荷见 API_CONTRACT 第 10 节；真机需登录后的号 |

## 2. 技术栈与进程

| 规划条目 | 落地产物 | 验证方式 |
|---|---|---|
| Python 3.12 + FastAPI + Telethon + aiogram 3 | `backend/requirements.txt`、`backend/Dockerfile`（python:3.12-slim） | `backend/.venv/bin/python -m compileall`；容器构建 |
| PostgreSQL 16 + Redis | `docker-compose.yml` 的 `postgres` / `redis` 服务 | `docker compose config`（需有 docker 的机器） |
| React + TypeScript + Vite | `frontend/` | `npm run build`（含 `tsc --noEmit`） |
| FastAPI WebSocket 推当前会话 | `app/api/routers/ws.py` | `scripts/e2e_check.py` 第 8 节（hello / ping-pong / subscribe） |
| Docker Compose：api、worker、postgres、redis | `docker-compose.yml` | 见「上线前 checklist」 |
| Bot 收发不进 Worker | Bot 路由与任务执行在 `app/api/bots/`，Worker 只处理 `account_id` 任务 | `claim_tasks(kind="worker")` 只领账号任务；`backend/tests/smoke_core.py` 第 2 节 |

## 3. 关键不变量（已用真实 Postgres 验证）

| 不变量 | 验证结果 |
|---|---|
| Worker 只领「自己租约内账号」的任务 | ✅ `smoke_core`：「worker 只能领到自己租约内账号的任务」「worker 不会领 Bot 任务」 |
| 同一账号同一时刻只有一个 Worker | ✅ `smoke_core`：「别的副本不能抢走有效租约」 |
| 续租延长 `lease_until` | ✅ `smoke_core`：「renew_leases 延长了 lease_until」 |
| 退出时先释放租约 | ✅ `smoke_core`：「release_leases 清掉本 worker 的租约」 |
| 任务重试退避、超限记 failed、可手工重试 | ✅ `smoke_core` 第 2 节 5 项 |
| 同一 Telegram 消息不重复入库 | ✅ `smoke_core`：「同一个 tg_message_id 不重复写」 |
| 同一消息不重复转发（`dedupe_key`） | ✅ `smoke_core`：「同一消息不重复转发」「dedupe_key 命中不重复入队」 |
| 去重冲突不回滚同一事务里刚写的消息 | ✅ `smoke_core`：「去重命中后消息仍在（SAVEPOINT 生效）」 |
| Webhook 重复投递只处理一次 | ✅ `smoke_core`：「同一 update_id 第二次被判为重复」 |
| 员工群回复能找回原会话 | ✅ `smoke_core`：「员工群回复能找回原会话」 |
| 群聊不会被默认 `private` 的调用降级 | ✅ `smoke_core`：「群聊类型不会被默认 private 的调用降级」 |
| 会话/Bot Token 加密存放 | ✅ `smoke_core` 建号用 `encrypt_secret`；`security.decrypt_secret` 往返通过 |
| 迁移可升级（14 表 + 11 枚举 + 部分唯一索引） | ✅ `alembic upgrade head` 在真实 PG 上跑通，`pg_indexes` 复核 |

## 4. 运维

| 规划条目 | 落地产物 | 验证方式 |
|---|---|---|
| `/health` 与 `/ready` | `app/api/routers/health.py` | `scripts/e2e_check.py` 第 1 节 |
| Worker Prometheus 指标（在线号、重连、任务成败、租约续期失败） | `app/worker/metrics.py` + `:9101/metrics` | `curl 127.0.0.1:9101/metrics \| grep tgcc_` |
| 告警 1：Worker 超过 60 秒没心跳 | `deploy/alert.rules.yml` | 规则表达式复核（见 OPERATIONS.md） |
| 告警 2：在线号比例突然下降 | `deploy/alert.rules.yml` | 同上 |
| 告警 3：失败/到期任务持续增加 | `deploy/alert.rules.yml` + API `/metrics` 的积压指标 | 同上 |
| 告警 4：数据库磁盘或备份失败 | `deploy/alert.rules.yml` + `deploy/backup.sh` 推 pushgateway | `bash -n deploy/backup.sh`；有 docker 时跑一次备份 |
| JSON 日志带 `account_id` / `worker_id` | `app/logging_conf.py` | 跑 worker 看日志行 |
| 备份可按时间点恢复 | `deploy/backup.sh`（`pg_basebackup` + `pg_dump`）+ postgres `archive_mode` | 见 OPERATIONS.md 恢复演练步骤 |
| 配置全走环境变量 | `app/config.py` + `.env.example` | `.env.example` 与 config 字段逐项对照 |

## 5. 需要真机才能验证的部分（本地无凭证）

以下必须用**你自己的** Telegram `api_id` / `api_hash`、真实号与 Bot Token 才能验证，
代码路径已实现并有任务级测试，但真机连通性未验证：

1. 用户号验证码登录（`login_start` → `login_code` → 可选 `login_password`）拿到会话串。
2. `sync_dialogs` 拉出真实群聊与私信。
3. 员工确认后由 Worker 真发出，并在会话页看到「收回一条」。
4. Bot Webhook 真收消息 → 转发到员工群 → 员工回复送回原会话。
5. `update_profile` 改本号的名称与头像。

上线前按 README 的「首次登录流程」逐条跑一遍即可。
