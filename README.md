# Telegram 云控

内部使用的 Telegram 运维控制台：管理自己的用户号和官方 Bot，处理这些号已经在里面的群聊与私信，
并用 Bot 把新消息转发到自己的员工群，员工回复后按同一规则送回原会话。

- 值班的人打开一个后台就能看见：哪些号在线、当前卡在哪条任务、某个群或私聊的最新消息。
- API 和长连接分开：重启页面服务不会把号全部踢下线。
- 发送默认要员工确认（用户号方向），Bot 方向可以直接回。
- 部署形态：Docker Compose（`postgres` / `redis` / `api` / `worker` / `frontend`，监控栈走 `monitoring` profile）。

配套文档：[规划.md](规划.md)（范围与口径）、[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)（架构与数据模型）、
[docs/API_CONTRACT.md](docs/API_CONTRACT.md)（接口契约）、[docs/OPERATIONS.md](docs/OPERATIONS.md)（告警处置与故障排查）、
[deploy/postgres-backup.md](deploy/postgres-backup.md)（备份与恢复）、[docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)（验收对照表）。

## 1. 范围（对齐 规划.md）

**做这些**

| 能力 | 落地方式 |
|---|---|
| 账号列表：状态、分组、心跳、当前任务、单号检测 | 账号管理页 + `POST /api/accounts/{id}/check` |
| 这个号已加入的群聊、发给它的私信 | `dialogs` / `messages`，通道 `user_account` |
| 官方 Bot 私信 + Bot 所在群能看到的消息 | Webhook → `services.inbound.ingest_message`，通道 `bot` |
| 新消息用 Bot 转发到指定员工群，员工回复送回原会话 | `relay_routes` / `relay_links` + `relay_to_staff` / `reply_to_origin` 任务 |
| 用户号上的发送由员工确认后发出 | `messages(status=pending)` + `send_message` 任务 → 持有租约的 Worker 发出 |
| 官方 Bot 按资料自动回复，身份是 Bot | `bot_reply` 任务（API 侧执行） |
| AI 草稿停在输入框，员工点发送才出去 | `reply_drafts`，发送后回填 `sent_by` / `sent_at` |
| 单个号在设置里改名称和头像 | `update_profile` 任务 |
| 批量私信 / 群发 / 素材群发 | 营销中心 `POST /api/campaigns/bulk-pm` 等，一 号一任务、batch 聚合 |
| 批量加群 / 退群 / 强拉进群 | 营销中心：邀请链接/公开群加群、退群清会话、管理员强拉成员 |
| 批量改资料 | 营销中心 `POST /api/campaigns/profile-update`（复用 `update_profile` 任务） |
| 吵群 | 营销中心：文本池 + 随机间隔连续发言，可配回复概率，可随时取消 |
| 多号拟人发言 | 营销中心：AI 按人设 + 群上下文生成话术，AI 不可用退回文本池 |

批量运营的节奏与安全：相邻两个号首发时间错峰；吵群 / 拟人有轮数、间隔、总时长硬上限；
发送只走 `healthy` 的号；素材库（`materials` 表 + 媒体落盘）供批量动作共用；批次进度可查、可取消。

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 语言 | Python 3.12 |
| API | FastAPI（无状态，可单独重启） |
| 用户号长连接 | Telethon（一个 Worker 挂一批号） |
| 官方 Bot | aiogram 3（Webhook 收、Bot API 回） |
| 主库 | PostgreSQL 16（账号、消息、任务、租约都能直接查） |
| 协调 / 推送 | Redis 7（心跳缓存、WebSocket 推送、`update_id` 去重；丢了不影响事实数据） |
| 任务队列 | Postgres `tasks` 表（`FOR UPDATE SKIP LOCKED` 领取） |
| 前端 | React + TypeScript + Vite（控制台） |
| 实时 | FastAPI WebSocket（只推当前打开的会话） |
| 部署 | Docker Compose v2 + Prometheus / Alertmanager |

## 3. 架构与进程

```text
                         ┌──────────────── 浏览器（React 控制台）────────────────┐
                         │  HTTP /api/*            WebSocket /api/ws?token=JWT  │
                         └───────────┬──────────────────────────┬──────────────┘
                                     │                          │
                              ┌──────▼──────────────────────────▼──────┐
                              │        frontend（nginx 静态 + 反向代理） │
                              └──────────────────┬─────────────────────┘
                                                 │ /api → api:8000
   Telegram 用户号 ──MTProto──┐        ┌─────────▼──────────────────────────────┐
                              ├───────►│  api（FastAPI，无状态）                 │
   Telegram Bot ──Webhook─────┘        │  · 鉴权 / 账号 / 会话 / 任务 / Bot 转发  │
                                       │  · 写 tasks 表；Bot 任务由自己领         │
                                       │  · /health /ready /metrics             │
                                       └─────────┬──────────────────────────────┘
                                                 │ 写 tasks / messages
                                       ┌─────────▼─────────┐        ┌───────────────┐
                                       │  PostgreSQL 16    │◄───────┤ Redis 7       │
                                       │  账号/会话/消息/    │ 租约    │ 心跳/推送/去重 │
                                       │  任务/租约/审计     │ 心跳    └───────────────┘
                                       └─────────▲─────────┘
                                                 │ 只领「自己租约内账号」的任务
                              ┌──────────────────┴───────────────────────┐
                              │  worker（Telethon，可多副本，:9101/metrics）│
                              └──────────────────┬───────────────────────┘
                                                 │ 新消息入库
                                     messages 表 ─┴─► WebSocket 推页面 / relay_to_staff 任务
                                                       → Bot 转发进员工群 → 员工回复 → reply_to_origin
```

关键不变量（详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)）：

- 每个用户号同一时刻只属于一个 Worker（`leases` 表，30 秒过期，每 10 秒续租）；进程退出先释放租约。
- Bot 收发不进 Worker：Webhook 无状态，不跟某台 Worker 绑定。
- Redis 丢了只影响页面订阅与去重，事实以 Postgres 为准。
- 一个 Worker 副本约承载 100 个在线号，扩容是增加 `worker` 副本，不是一个号一个容器。

### 目录结构

```text
backend/
  app/api/             HTTP + WebSocket + Bot Webhook（FastAPI）
  app/worker/          认领租约、维持 Telethon 连接、执行本副本任务 + :9101/metrics
  app/models/          14 张表的 ORM 与枚举（含中文标签）
  app/core/            tasks（队列）/ leases（租约）/ events（推送）/ audit（审计）
  app/config.py        全部配置走环境变量（.env.example 逐项对应）
  alembic/             迁移
  Dockerfile           与 worker 共用镜像
  entrypoint.sh        统一入口：等库 → 迁移 → 可选建管理员 → exec
frontend/              React + TypeScript + Vite 控制台（Dockerfile / nginx.conf 由前端维护）
deploy/
  prometheus.yml       抓取配置（api / worker / postgres-exporter / pushgateway）
  alert.rules.yml      四条告警 + 录制规则
  alertmanager.yml     告警分流（示例 webhook，附企业微信/钉钉/Slack 改法）
  backup.sh            日备（pg_dump）+ 周备（pg_basebackup）+ 上报 pushgateway
  backup.cron          crontab 片段（每日 03:10 / 每周日 03:40）
  postgres-backup.md   恢复与演练手册
docs/OPERATIONS.md     告警处置、常见故障、扩容、恢复演练
docker-compose.yml     postgres / redis / api / worker / frontend（+ monitoring profile）
Makefile               make help 看全部命令
```

## 4. 快速开始（Docker Compose）

前置条件：Docker 24+ 与 Compose v2（`docker compose version`）、可用磁盘 ≥ 20 GB、
一个能指向本机的域名或公网地址（Telegram Webhook 要用）。

### 4.1 准备 `.env`

```bash
cp .env.example .env
```

必须填的 5 项（其余保持默认即可跑）：

| 键 | 从哪来 |
|---|---|
| `POSTGRES_PASSWORD` | 自己生成：`python -c "import secrets; print(secrets.token_urlsafe(24))"`，改完同步改 `DATABASE_URL` 里的口令 |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SESSION_ENCRYPTION_KEY` | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`，会话串与 Bot Token 用它加密 |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | 用你要挂的号登录 <https://my.telegram.org> → **API development tools** 申请 |
| `BOOTSTRAP_ADMIN_PASSWORD` | 控制台 `admin` 的口令（不给就在 `make admin` 时用 `ADMIN_PASSWORD=` 传） |

另外把 `PUBLIC_BASE_URL` 改成 Telegram 能访问到的地址（例如 `https://tg.example.com`）：
Webhook 注册到 `<PUBLIC_BASE_URL>/api/webhook/{bot_id}/{WEBHOOK_SECRET}`，写 `localhost` 会注册失败。

> Bot Token 不写在 `.env` 里：登录控制台后在「Bot 管理」页填（BotFather 拿 Token），库里加密保存。
> 密钥一旦有号登录过就不要再改：`SESSION_ENCRYPTION_KEY` 变了，已入库的会话解不开，所有号都要重新登录。

### 4.2 起基础服务并迁移

```bash
docker compose up -d postgres redis     # Postgres 16（带 WAL 归档）+ Redis 7
make migrate                            # api 没起也能跑：自动改用一次性容器执行 alembic upgrade head
make admin ADMIN_PASSWORD='你的口令'      # 创建/重置管理员；不传口令则读 .env 的 BOOTSTRAP_ADMIN_PASSWORD
```

### 4.3 起应用

```bash
docker compose up -d api worker frontend
docker compose ps                       # 五个服务都应是 healthy / running
curl -fsS http://127.0.0.1:8000/health  # {"status":"ok",...}
curl -fsS http://127.0.0.1:8000/ready   # {"status":"ready","database":true,"redis":true}
```

控制台：<http://localhost:8080>（端口由 `WEB_PORT` 控制；前端 nginx 把 `/api` 与 `/api/ws` 反代到 `api:8000`）。
API 直连端口：<http://localhost:8000>。

> `api` 容器启动时会自己跑一次 `alembic upgrade head`（entrypoint 里），并按需补建管理员，重复执行是幂等的。

### 4.4 监控（可选，profile 方式）

```bash
make monitoring        # = docker compose --profile monitoring up -d
```

| 页面 | 地址 | 说明 |
|---|---|---|
| Prometheus | <http://localhost:9090> | Targets 里应有 `api` / `worker` / `postgres-exporter` / `pushgateway` / `alertmanager` |
| Alertmanager | <http://localhost:9093> | 默认接收人是占位 webhook，改 `deploy/alertmanager.yml` 后 `curl -X POST localhost:9093/-/reload` |
| Pushgateway | <http://localhost:9091> | 备份脚本上报「最近一次成功备份时间」 |
| 告警规则 | <http://localhost:9090/rules> | 四条告警的实时状态 |

装备份定时任务（宿主 cron）：

```bash
crontab -l 2>/dev/null > /tmp/tgcc.cron
cat deploy/backup.cron >> /tmp/tgcc.cron     # 先按文件里的说明改 TGCC_HOME
crontab /tmp/tgcc.cron && crontab -l
```

### 4.5 首次登录与单号登录流程

1. 打开 <http://localhost:8080>，用 `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` 登录。
2. **账号分组**（可选）：先建一个分组，方便把号分给同事。
3. **网络**（可选）：这个号固定的出站代理先建好（用户名/密码加密保存，页面只显示有没有）。
4. **账号管理 → 登录**：填手机号（可带分组和代理）→ `POST /api/accounts/login/start` 发验证码；
   输入收到的验证码 → `login_code`；如果这个号开了两步验证，再输一次密码 → `login_password`。
   全部通过后会话串加密写入 `tg_accounts.session_enc`，状态变 `healthy`。
5. **账号检测**：点「检测」立刻续一次租约并读一次状态，结果写回该行（连得上 / 要验证码 / 会话失效）。
6. **同步会话**：在账号管理里点「同步会话」→ 写 `sync_dialogs` 任务 → 持有该号租约的 Worker 拉出
   已加入的群聊和私信，落进 `dialogs` / `messages`。
7. **会话页**：选一个会话就能看到历史消息；发送时用户号方向走「等待确认发送」——
   写一条 `pending` 的 `messages` 和 `send_message` 任务，Worker 发出后回填 `tg_message_id`、状态变 `sent`。
8. **Bot 转发**：BotFather 拿 Token → 「Bot 管理」页新增（会调 `getMe` 校验并注册 Webhook）→
   「Bot 转发」页配好「用哪个 Bot、转发到哪个员工群」→ 之后新消息会自动转发，员工在群里回复那条转发即送回原会话。

常见卡点：Webhook 注册失败基本都是 `PUBLIC_BASE_URL` 不是公网可达地址；验证码登录失败先看 Worker 日志里
`login_*` 任务的 `error`。

## 5. 常用命令

`make help` 是唯一权威清单，下面是摘要：

| 命令 | 作用 |
|---|---|
| `make up` / `make down` | 起/停全部服务（`down` 会连监控一起停；数据卷保留） |
| `make ps` / `make logs S=worker` | 看状态 / 跟踪日志 |
| `make migrate` / `make revision M="描述"` | 跑迁移 / 生成迁移脚本 |
| `make admin ADMIN_PASSWORD='xxx'` | 创建或重置管理员 |
| `make monitoring` | 带 `monitoring` profile 起 Prometheus + Alertmanager + Pushgateway + postgres-exporter |
| `make backup` / `make restore` | 立刻备份一次 / 打印恢复入口（细则见 [deploy/postgres-backup.md](deploy/postgres-backup.md)） |
| `make psql` | 进 psql 排查 |
| `make dev-api` / `make dev-worker` / `make dev-web` | 本机直接跑进程（不用 docker） |
| `make check` | Python 编译检查 + 前端 `npm run typecheck` |

## 6. 本地开发（不用 Docker）

```bash
# 1) 后端依赖
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..

# 2) 本地 Postgres 与 Redis（本仓库用 .pgdata / .redisdata，端口见 backend/.env：55432 / 56379）
pg_ctl -D .pgdata -l run/pg.log -o "-p 55432 -k /tmp" start
redis-server --port 56379 --dir .redisdata --daemonize yes

# 3) 配置：本地用 backend/.env（已存在；数据库/Redis 指到 127.0.0.1 的上面两个端口）

# 4) 一键起 API + Worker（含迁移、建管理员、日志落在 run/）
./scripts/stack_local.sh up        # down / status / logs 见脚本头部说明

# 或者手动分别起：
cd backend && .venv/bin/uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
cd backend && .venv/bin/python -m app.worker.main          # :9101/metrics

# 5) 前端 dev server（http://127.0.0.1:5173，/api 自动反代到 127.0.0.1:8000）
cd frontend && npm ci && npm run dev
```

也可以只把数据库交给容器：`docker compose up -d postgres redis`，
再把 `backend/.env` 的 `DATABASE_URL` / `REDIS_URL` 改成 `127.0.0.1:5432` / `127.0.0.1:6379`。

端到端自检：`backend/.venv/bin/python scripts/e2e_check.py`（探测 `/health`、`/ready`、`/metrics`、WebSocket 等）。

## 7. 运维手册摘要

完整的告警处置与故障排查在 [docs/OPERATIONS.md](docs/OPERATIONS.md)，恢复演练在
[deploy/postgres-backup.md](deploy/postgres-backup.md)。这里只放最常查的四块。

### 7.1 四条告警

| # | 告警名（severity） | 判据 | 先做什么 |
|---|---|---|---|
| 1 | `TgccWorkerHeartbeatStale`（critical） | `tgcc_worker_heartbeat_age_seconds > 60` 持续 1 分钟 | `docker compose ps worker`；`docker compose logs --tail=200 worker`；`docker compose restart worker`。另有 `TgccWorkerTargetDown`（`up{job="worker"}==0`）与 `TgccWorkerTargetsMissing`（`absent(up{job="worker"})`）覆盖「进程没了/指标没起来/一个副本都没有」 |
| 2 | `TgccOnlineAccountsDrop`（critical） | 在线号总量近 5 分钟均值相对近 1 小时均值下降 > 30%，持续 5 分钟（`TgccOnlineAccountsDropEarly` 是 15% 的 warning；`TgccAllAccountsOffline` 兜住基线也是 0 的情况） | 看工作台在线/异常数；`SELECT status, count(*) FROM tg_accounts GROUP BY 1;`；同时看 Worker 心跳告警是不是一起响（一起响说明是 Worker 侧问题，只有在线数掉说明是号被限制/代理挂了） |
| 3 | `TgccTasksFailedIncreasing`（warning）、`TgccTasksOverdue`（warning）、`TgccTasksStuck`（critical） | 失败任务 30 分钟净增 > 5；`tgcc_tasks{status="overdue"} > 20`；`tgcc_tasks{status="stuck"} > 5` | 任务中心按失败筛查看 `error`；`SELECT type, error, count(*) FROM tasks WHERE status='failed' GROUP BY 1,2;`。到期堆积先看 Worker 副本数与租约占用，再考虑 `--scale worker=N` |
| 4 | `TgccBackupFailed`/`TgccBackupOverdue`（critical）、`TgccDatabaseSizeLarge`/`TgccDatabaseGrowthFast`/`TgccBaseBackupOverdue`（warning） | 备份脚本推的 `tgcc_last_successful_backup_timestamp_seconds` 为 0 或超过 24 小时没更新；`pg_database_size_bytes` 超 20 GiB 或按 6 小时趋势 7 天内会超 40 GiB | 看 `/var/log/tgcc-backup.log`；手动 `make backup` 复现；确认 `BACKUP_DIR` 可写、磁盘没满、pushgateway 在跑；数据库涨得快就先查 `messages` / `audit_logs` |

监控自身的两条：`TgccApiDown`（API 不可达）、`TgccExporterDown` / `TgccAlertmanagerDown`（采集或告警链路挂了，
不修就会出现「没人告警」的静默故障）。

### 7.2 备份与恢复

- 每天 03:10 `pg_dump -Fc` 逻辑备份（保留 7 份）；每周日 03:40 `pg_basebackup` 基础备份（保留 4 份）；
  Postgres 全程 `archive_mode=on`，WAL 归档在 `pg_wal_archive` 卷。
- **按时间点恢复（PITR）= 基础备份 + WAL 归档**，两者缺一不可，都要一起离线保存。
  完整步骤（含临时实例验证、权限与坑）在 [deploy/postgres-backup.md](deploy/postgres-backup.md)，摘要：

```bash
# 日常误删：逻辑恢复（最快，先停写入）
docker compose stop api worker frontend
docker compose exec -T postgres psql -U cloudctl -d postgres -c 'DROP DATABASE cloudctl WITH (FORCE);'
docker compose exec -T postgres psql -U cloudctl -d postgres -c 'CREATE DATABASE cloudctl OWNER cloudctl;'
docker compose exec -T postgres pg_restore -U cloudctl -d cloudctl --no-owner < backups/daily-<TS>.dump
docker compose start api worker frontend && curl -fsS http://127.0.0.1:8000/ready

# 按时间点恢复：解基础备份 → 拷 WAL 归档 → 写 recovery.signal → 临时实例验证 → 搬回生产卷
docker compose stop api worker frontend postgres
mkdir -p restore/pgdata restore/wal
tar -xzf backups/base-<TS>.tar.gz -C restore/pgdata
docker run --rm -v tgcc_pg_wal_archive:/wal:ro -v "$PWD/restore/wal":/out alpine sh -c 'cp -a /wal/. /out/'
touch restore/pgdata/recovery.signal
TARGET='2026-09-28 20:00:00+08'        # 想恢复到的时间点（要晚于基础备份时间）
cat >> restore/pgdata/postgresql.auto.conf <<EOF
restore_command = 'cp /wal-archive/%f %p'
recovery_target_time = '$TARGET'
recovery_target_action = 'promote'
EOF
docker run --rm -v "$PWD/restore/pgdata":/data alpine chown -R 70:70 /data && chmod 700 restore/pgdata
docker run --rm --name tgcc-restore -e PGDATA=/var/lib/postgresql/data/pgdata \
  -v "$PWD/restore/pgdata":/var/lib/postgresql/data/pgdata -v "$PWD/restore/wal":/wal-archive:ro \
  -p 127.0.0.1:55433:5432 postgres:16-alpine     # 验证没问题后再把数据搬回 tgcc_pgdata 卷
```

- 恢复后只要 `.env` 里的 `SESSION_ENCRYPTION_KEY` 没变，库里加密的会话与 Bot Token 仍可解密，号不用重登；
  **换过密钥就必须重新登录所有号**。
- 建议每季度按 [deploy/postgres-backup.md](deploy/postgres-backup.md) 第 6 节演练一次。

### 7.3 发布顺序

1. 需要改表就先跑迁移：`make migrate`（向后兼容的迁移才允许先上线）。
2. **先滚 Worker**：`docker compose up -d --no-deps --build worker`；
   多副本想少掉线就先 `--scale worker=N+1` 让新副本认领一部分号，稳定后再缩回 `N`。
   Worker 收到 SIGTERM 会先释放租约再退出（`stop_grace_period: 60s`），期间它持有的号短暂掉线，随后被其他副本接管。
3. **最后重启 API**：`docker compose up -d --no-deps api`。API 无状态，页面 WebSocket 会重连，号不受影响。
4. 前端：`docker compose up -d --no-deps --build frontend`。
5. **单个号异常**（会话失效、要验证码、发不出去）：只清这个号的租约 ——
   控制台账号管理页点「释放租约」（`POST /api/accounts/{id}/release-lease`），或
   `DELETE FROM leases WHERE account_id='...';`，**不要重启全部连接**。

### 7.4 扩容与日志

- 扩容：`docker compose up -d --scale worker=3`（一副本约 100 个在线号，`ACCOUNTS_PER_REPLICA`）。
  注意 `WORKER_METRICS_PORT_RANGE` 要覆盖副本数（默认 `9101-9110` 支持 10 个副本），
  数据库连接数按 `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × 进程数 < POSTGRES_MAX_CONNECTIONS` 估。
- 日志是 JSON 一行一条，带 `component`，业务日志带 `account_id` / `worker_id` / `task_id`：

```bash
docker compose logs -f --no-log-prefix worker | jq -c 'select(.account_id=="<uuid>")'
docker compose logs --no-log-prefix api | jq -c 'select(.level!="INFO")'
```

## 8. 安全

- **会话串、Bot Token、代理口令**用 Fernet 加密后入库（密钥 `SESSION_ENCRYPTION_KEY`），
  库里不存明文；`BotOut.token_masked` 只回 `123456...abcd`。
- **密钥只在环境变量**：`.env` 已被 `.gitignore` 与 `backend/.dockerignore` 排除，不进版本库、不进镜像；
  镜像里没有任何密钥文件，配置全部由 Compose 在运行时注入。
- `ENVIRONMENT=production` 时 `entrypoint.sh` 会强制要求 `SECRET_KEY`、`SESSION_ENCRYPTION_KEY` 非空，缺一个就拒绝启动。
- 控制台鉴权：JWT（HS256）+ bcrypt 口令；`operator` 只能看/操作分配给自己的号；Webhook 路径带
  `WEBHOOK_SECRET` 且用常量时间比较；所有改状态的动作写 `audit_logs`。
- Postgres / Redis 默认只绑定宿主 `127.0.0.1`（`POSTGRES_PUBLISH` / `REDIS_PUBLISH`），不要直接对公网开放；
  对外只用 `frontend` 的 80 端口（前面应再放一层 HTTPS 反代）。
- 登录只用这个号自己的验证码或自己创建的 Bot Token，不导入别人的会话文件。
