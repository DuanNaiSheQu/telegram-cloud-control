# 快速开始

> 文档索引：[docs/README.md](README.md) · 相邻：功能地图 [FEATURES.md](FEATURES.md) · 部署上线 [DEPLOYMENT.md](DEPLOYMENT.md)

从零到「一个账号上线并发出第一条消息」。全程本地即可，不需要公网域名。

## 0. 你需要准备什么

| 项目 | 要求 | 说明 |
|---|---|---|
| 系统 | macOS / Linux | Windows 走 WSL2 |
| Python | 3.12+ | 后端与 Worker |
| Node.js | 20+ | 前端 |
| Postgres | 15+ | 本地默认端口 `55432` |
| Redis | 7+ | 本地默认端口 `56379` |
| Telegram API 凭据 | `api_id` / `api_hash` | 在 <https://my.telegram.org> 申请，**每个部署一套** |

> 没有 Postgres / Redis？用 `docker compose up -d postgres redis` 也行，端口按 `docker-compose.yml`，
> 与本地默认值一致即可（见 [DEPLOYMENT.md](DEPLOYMENT.md)）。

## 1. 起本地栈

```bash
git clone <你的仓库地址> telegram-cloud-control && cd telegram-cloud-control

make stack-up        # 起 Postgres/Redis（若未起）、跑迁移、起 API:8000 与 Worker
make stack-status    # 看三个进程与端口占用
```

产物与日志：

| 路径 | 内容 |
|---|---|
| `run/api.pid` / `run/worker.pid` / `run/web.pid` | 进程号 |
| `run/api.log` / `run/worker.log` / `run/web.log` | 日志（JSON 一行一条，便于 grep） |

前端单独起（开发模式，`/api` 反代到 `:8000`）：

```bash
cd frontend && npm install && npm run dev     # http://127.0.0.1:5173
```

## 2. 填配置

复制模板并填最少的三项：

```bash
cp .env.example backend/.env
```

```ini
TELEGRAM_API_ID=1234567          # my.telegram.org 拿
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
SESSION_ENCRYPTION_KEY=          # 留空则首次启动自动生成；一旦有号就用它加密会话，别丢
```

其它常用项（都可不填，走默认）：

| 变量 | 默认 | 作用 |
|---|---|---|
| `THROTTLE_ACTIVE_HOURS` | `8-24` | 允许动作的活跃时段，避开凌晨批量操作 |
| `THROTTLE_DAILY_DEFAULT` | `200` | 号龄足够后的每日发送上限 |
| `IMPORT_MAX_ACCOUNTS` | `500` | 单次批量导入上限 |
| `CAMPAIGN_STAGGER_SECONDS` | 见 `.env.example` | 批量任务错峰起始 |

> `TELEGRAM_API_ID=0` 时 Worker 只认领租约与发心跳、不连 Telegram，账号不会显示在线——这是**预期行为**，
> 用来在没凭据时跑通链路。

## 3. 建管理员并登录

```bash
make create-admin     # 交互式创建首个管理员
```

打开 <http://127.0.0.1:5173>，用刚建的账号登录。没有账号时工作台会显示引导条，点「去建号」直接进登录向导。

## 4. 把第一个号搞上线

三条路，按你手上的材料选：

| 你手上有什么 | 走哪条路 |
|---|---|
| 手机号（要收验证码） | 账号管理 → **登录向导**：填号码 → 收码 → 若开了两步验证再填密码 |
| StringSession 串 / `.session` 文件 / tdata 目录 | 账号管理 → **批量导入**（详见 [ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md) 第 1 节） |
| 已有一个能用的会话串 | 同上，直接导入即可 |

登录成功后账号状态会变成**正常**，Worker 建立连接，侧栏右上角显示「实时连接正常」。

## 5. 发出第一条消息

1. **账号管理 → 批量同步会话**：把这个号加入的群/私信拉到会话列表（没有这一步，页面里看不到群）。
2. **会话收件箱 → 选一个会话 → 发消息**：消息由 Worker 通过该号的连接发出。
3. 想看批量能力（私信/群发/加群/采集…）：**触达中心** 与 **群情报**，见 [FEATURES.md](FEATURES.md)。

## 6. 验证一切正常

```bash
make smoke            # 健康检查 + 关键接口冒烟
backend/.venv/bin/python scripts/e2e_check.py    # 41 项既有回归
```

界面截图（可选）：`cd frontend && npm run screenshots`。

## 7. 常见坑

| 现象 | 原因与处理 |
|---|---|
| 账号一直显示「待登录」 | 没走完登录向导；或 `TELEGRAM_API_ID` 没配，Worker 不连 |
| 任务一直 `pending` | Worker 没起或 `TELEGRAM_API_ID=0`；`make stack-status` 看 worker 是否在跑 |
| 页面打开是空白/接口 401 | 登录态过期：退出重登；`localStorage` 里的 `tgcc_token` 被清过 |
| 发送报「节流拦下：不在活跃时段」 | 正常保护，见 [ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md) 第 3 节；改 `THROTTLE_ACTIVE_HOURS` 可调 |
| 批量导入说「重复」 | 按手机号确定性哈希去重，说明这个号已经建档过了 |
| Postgres 连不上 | `make stack-status` 看 55432 是否被别的实例占用；确认 `backend/.env` 里的 `DATABASE_URL` |
| 多个 worker 抢租约 | 本地只能跑一个 Worker，见 [AGENTS.md](../AGENTS.md) |

## 下一步

- 功能地图：[FEATURES.md](FEATURES.md)
- 账号运营（导入/验活/防封/采集）：[ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md)
- 上线部署：[DEPLOYMENT.md](DEPLOYMENT.md)
- 出问题：[OPERATIONS.md](OPERATIONS.md)
