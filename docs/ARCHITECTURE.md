# 架构说明

本文说明这套「Telegram 云控」控制台的结构、数据流与关键不变量。产品范围见 [规划.md](../规划.md)，
接口细节见 [API_CONTRACT.md](API_CONTRACT.md)。

## 1. 进程与职责

```text
                      ┌─────────────────────────────┐
   页面 (React) ──WS──▶│  api (FastAPI, 无状态)        │──POST /api/webhook/{bot_id}/{secret}◀── Telegram
        │             │  · HTTP / WebSocket          │
        │             │  · 官方 Bot 收发（aiogram 3）  │
        └──HTTP──────▶│  · Bot 任务执行器              │
                      └───────┬──────────────┬───────┘
                              │ 写 tasks      │ 写 messages
                              ▼              ▼
                      ┌─────────────────────────────┐
                      │ postgres（唯一事实来源）      │
                      │ users/tg_accounts/dialogs/   │
                      │ messages/tasks/leases/...    │
                      └───────┬──────────────┬───────┘
                              │ 领任务（SKIP LOCKED）│ 心跳/推送
                      ┌───────▼──────────────▼───────┐
                      │ worker (Telethon, 可多副本)   │
                      │  · 认领账号租约、维持长连接    │
                      │  · 执行该号的任务             │
                      │  · 新消息入库                 │
                      └──────────────┬───────────────┘
                                     │ 只读缓存 / 发布订阅
                              ┌──────▼───────┐
                              │   redis      │
                              └──────────────┘
```

关键取舍：

- **API 与长连接分开**：重启页面服务不会把号全部踢下线。用户号连接只在 Worker 进程里。
- **Bot 收发不进 Worker**：Webhook 无状态，不跟某台 Worker 绑定；Bot 任务（转发、自动回复）由 API 侧的
  轮询器领取执行。
- **Redis 可以丢**：心跳缓存、页面推送、Webhook 去重、登录临时态放 Redis；消息、任务、租约的事实都在
  Postgres，Redis 重启只影响正在打开的页面的实时推送。

## 2. 数据模型（14 张表）

| 表 | 作用 | 关键约束 |
|---|---|---|
| `users` | 登录控制台的人，`role` = admin / operator | `username` 唯一 |
| `account_groups` | 自定义标签，用来把号分给同事 | `name` 唯一 |
| `proxies` | 账号固定出站地址，用户名/密码加密 | `name` 唯一 |
| `tg_accounts` | 用户号：脱敏手机号、状态、分组、代理、加密会话串 | `tg_user_id` 唯一；`session_enc` 只存密文 |
| `account_assignments` | 谁可以操作哪个号 | `(user_id, account_id)` 唯一 |
| `bots` | 自己的官方 Bot，Token 加密；转发目标与自动回复资料分开存 | `name` 唯一 |
| `dialogs` | 会话：群聊 / 私信；通道是 `user_account` 或 `bot` | `(account_id, tg_chat_id)`、`(bot_id, tg_chat_id)` 唯一 |
| `messages` | 方向、正文、Telegram 消息 ID、发送人 | 部分唯一索引 `(dialog_id, tg_message_id) WHERE tg_message_id IS NOT NULL` |
| `tasks` | 状态、下次执行时间、重试次数、错误、`worker_id` | `dedupe_key` 唯一（防重复转发） |
| `leases` | 账号租约：`worker_id` / `lease_until` / `last_heartbeat` | 主键 `account_id` |
| `relay_routes` | 用哪个 Bot、转发到哪个员工聊天，可按号/会话过滤 | — |
| `relay_links` | 原消息 ↔ 员工群里那条转发 | `(staff_chat_id, staff_message_id)` 唯一、`message_id` 唯一 |
| `reply_drafts` | 未发送的 AI 草稿 | — |
| `audit_logs` | 谁在什么时间对哪个号做了什么 | 按 `created_at, action` 建索引 |

业务表都带操作者归属（`created_by` / `user_id`），方便按人查审计。

> 租户：当前按单租户使用，不拆商户字段。以后平台侧有多个使用方时再加 `tenant_id`，
> 不要提前把单租户工具做成对外售卖的商户系统。

## 3. 任务队列

`tasks` 表就是队列，不用额外中间件：

- **入队**：页面动作、Webhook、转发表都只写 `tasks`（`core.tasks.enqueue_task`）；
  带 `dedupe_key` 的入队用 SAVEPOINT 包裹，去重命中不会把同一事务里刚写入的消息一起回滚。
- **领取**：`SELECT ... FOR UPDATE SKIP LOCKED`（`core.tasks.claim_tasks`），
  Worker 只领「账号租约属于自己」的任务，API 只领带 `bot_id` 的任务。
- **重试**：失败写 `error` 与 `next_run_at`（指数退避 + 抖动），超过 `max_attempts` 记 `failed`；
  页面上的「重试」把 `attempts` 归零放回 `pending`。
- **僵尸任务**：进程重启时把自己名下超时仍 `running` 的任务放回队列（`reclaim_stale_running`）。

任务类型与载荷见 [API_CONTRACT.md 第 10 节](API_CONTRACT.md)。

## 4. 租约与心跳

- Worker 启动后认领无有效租约的账号（`status` 属于可认领集合），写入 `leases`。
- 每 10 秒续租（TTL 30 秒），同时写 `tg_accounts.last_heartbeat` 和 Redis 心跳键。
- 退出时先 `delete from leases where worker_id=...` 再断开连接（SIGTERM 亦然），其他副本立刻可接管。
- 单个号异常只清它的租约（`release_account`）或标停用，**不重启全部连接**。
- 扩容 = 增加 `worker` 副本（一副本约 100 个在线号），不是一个号一个容器。
- 发布顺序：**先滚动 Worker，再重启 API**。

## 5. 两条连接进同一张收件箱

| 来源 | 谁在听 | 能看到什么 |
|---|---|---|
| 用户号 | 持有租约的 Worker（Telethon `NewMessage`） | 已加入的群，以及发给这个号的私信 |
| 官方 Bot | API 上的 Webhook | 发给 Bot 的私信，以及 Bot 所在群里它能收到的消息 |

两者都通过 `services.inbound.ingest_message` 落库：按 `(通道, 归属, tg_chat_id)` 找或建会话，
按 `tg_message_id` 去重，更新未读与预览，然后推 Redis 给页面。

Bot 要看群里全部消息，需要把它设为该群管理员或关闭隐私模式；系统不补它收不到的消息。

## 6. 转发与回复

```text
新消息入库 ──▶ 命中 relay_routes ──▶ 写 relay_to_staff 任务（带 dedupe_key）
                                          │
                              API 侧 Bot 轮询器执行
                                          ▼
                          Bot 发到员工群（正文带来源：哪个号/群还是私信/对方是谁）
                                          ▼
                          写 relay_links（原消息 ↔ 员工群那条）
```

员工在员工群里回复那条转发时：

- Webhook 命中 `relay_links` → 写 `reply_to_origin` 任务；
- 原会话是 **Bot** → API 直接用 Bot API 发回原聊天；
- 原会话是 **用户号** → 写 `send_message` 任务，由持有该号租约的 Worker 发出。

控制台里回复也一样：来自 Bot 的对话用 Bot API 发回；来自用户号的对话写成待发送任务，员工点发送才由 Worker 发出。

Webhook 一律用 `update_id` 去重（Redis `SETNX`，TTL 24 小时），避免 Telegram 重试造成两次转发。

## 7. 状态口径

| 账号状态 | 含义 | 是否认领 | 是否替它发送 |
|---|---|---|---|
| `pending` 待登录 | 已建档，还没拿到会话 | 是（等登录任务） | 否 |
| `healthy` 正常 | 租约有效、心跳在 | 是 | 是 |
| `needs_code` 要验证码 | 会话存在但需重新验证 | 是 | 否 |
| `frozen` 冻结 | Telegram 限制了这个号 | 是（只监控） | 否 |
| `invalid` 失效 | 会话打不开 | 是（可重新登录） | 否 |
| `dead` 永久双向 | 双向不可用，只留记录 | 否 | 否 |
| `disabled` 停用 | 人工下线 | 否 | 否 |

`tg_accounts.current_task` 只有四种：空闲、同步会话、等待确认发送、转发到员工群。

## 8. 安全

- 会话串、Bot Token、代理口令全部用 Fernet 对称加密后入库；密钥来自 `SESSION_ENCRYPTION_KEY`
  环境变量（未配置时由 `SECRET_KEY` 派生，仅限开发），不进镜像。
- 控制台用 JWT（HS256）+ bcrypt 口令；operator 只能看被分配到的号。
- Webhook 路径带 `WEBHOOK_SECRET`，用常量时间比较校验。
- 登录只用这个号自己的验证码，或自己创建的 Bot Token；不导入别人的会话文件。
- 所有会改状态的动作写 `audit_logs`。

## 9. 可观测性

- 日志：JSON 一行一条，带 `component`，业务日志带 `account_id` / `worker_id` / `task_id`。
- `GET /health` 进程活着；`GET /ready` 数据库与 Redis 都通（否则 503）。
- Worker 暴露 `:9101/metrics`：在线号数量、重连次数、任务成功与失败、租约续期失败。
- API 暴露 `/metrics`：任务积压（pending/running/failed/overdue/stuck）、账号按状态计数、未读会话数。
- 四条告警见 `deploy/alert.rules.yml`：Worker 心跳超 60 秒、在线号比例骤降、失败/到期任务持续增长、
  数据库磁盘或备份失败。

## 10. 目录

```text
backend/
  app/config.py            配置（全部走环境变量）
  app/db.py                engine / session
  app/redis_client.py      Redis 客户端
  app/security.py          口令、JWT、会话加密、脱敏
  app/logging_conf.py      JSON 日志
  app/models/              14 张表的 ORM 定义与枚举（含中文标签）
  app/core/                tasks（队列）/ leases（租约）/ events（推送）/ audit（审计）
  app/services/            inbound（统一入库）/ relay（转发）/ ai（草稿与 Bot 自动回复）
  app/schemas/             Pydantic 契约
  app/api/                 HTTP + WebSocket + Bot Webhook（FastAPI）
  app/worker/              Telethon 连接、租约心跳、任务执行、Prometheus
  alembic/                 迁移
  tests/                   冒烟验证（真实 Postgres + Redis）
frontend/                  React + TypeScript + Vite 控制台
deploy/                    Prometheus / Alertmanager / 备份
docker-compose.yml         api、worker、postgres、redis（+ monitoring profile）
```
