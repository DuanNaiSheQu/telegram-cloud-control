# 部署

> 文档索引：[docs/README.md](README.md) · 相邻：快速开始 [GETTING_STARTED.md](GETTING_STARTED.md) · 线上运维 [OPERATIONS.md](OPERATIONS.md)

两种部署形态：**本地直跑**（开发与自用）和 **Compose**（服务器常驻）。生产要点集中在「清单」一节。

## 1. 形态一：本地直跑（推荐自用）

```bash
make stack-up        # Postgres + Redis（若未起）→ 跑迁移 → API:8000 + Worker
make stack-status    # 核对进程与端口
make stack-down      # 停
```

- 进程号在 `run/{api,worker,web}.pid`，日志在 `run/*.log`（JSON 一行一条）。
- 本地只能跑**一个** Worker；多个 Worker 会互相抢账号租约，日志会刷「租约已不属于本进程」。
- 前端开发：`cd frontend && npm run dev` → <http://127.0.0.1:5173>（`/api` 反代到 `:8000`）。

## 2. 形态二：Docker Compose

```bash
cp .env.example .env          # 填 TELEGRAM_API_ID / API_HASH / 数据库口令等
docker compose up -d --build
docker compose ps
```

`docker-compose.yml` 里的服务：`postgres`、`redis`、`api`、`worker`、`web`，以及素材卷
`materials-data:/app/materials`（素材文件必须持久化，否则重建容器会丢）。

- 数据库与 Redis **只绑定 `127.0.0.1`**，对外只暴露前端 80 端口。
- 迁移在 `api` 启动入口执行；升级后先看 `docker compose logs -f api` 有没有迁移报错。
- 备份脚本见 [../deploy/postgres-backup.md](../deploy/postgres-backup.md)。

## 3. 生产清单（逐项打勾）

### 3.1 凭据与密钥

- [ ] `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`：**每套部署单独申请**，不要与他人共用。
- [ ] `SESSION_ENCRYPTION_KEY`：首次生成后**立即备份**。丢了等于所有会话串作废，只能逐号重登。
- [ ] `SECRET_KEY`（签发 JWT）：换成随机长串，不要用模板默认值。
- [ ] 数据库口令、Redis 口令（若开了鉴权）不要复用。
- [ ] `.env` 不进版本库（`.gitignore` 已含），生产上权限设成 `600`。

### 3.2 网络与入口

- [ ] 前端对外只开 443，前面放一层 HTTPS 反代（Nginx / Caddy）。
- [ ] `/api` 反代到 API 进程；WebSocket 路径要带 `Upgrade` / `Connection` 头透传。
- [ ] Bot Webhook 必须**公网可达且 HTTPS**，否则收不到 Bot 消息（可用反代 + 证书自动续签）。
- [ ] 数据库与 Redis 不要暴露公网；只允许内网或本机访问。

反向代理要点（Nginx 片段）：

```nginx
location / {
    proxy_pass http://127.0.0.1:5173;   # 生产换成前端静态目录或 web 容器
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location /api/ws/ {                      # WebSocket
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
}
```

### 3.3 资源与稳定性

- [ ] 账号数量决定 Worker 副本数：一个 Worker 能稳定带的号有限，号多了要加副本（租约机制保证不重复）。
- [ ] `restart: unless-stopped`（Compose 已配），进程挂了自动拉起。
- [ ] 磁盘留够：素材文件 + Postgres 数据 + 日志轮转（`run/*.log` 会增长）。
- [ ] 打开 `/health`（存活）与 `/ready`（依赖就绪，包含数据库与 Redis）做探针——注意这两个**没有 `/api` 前缀**。

### 3.4 代理

- [ ] 每个用户号走固定出口：在「网络」页建代理，导入账号时直接绑定。
- [ ] 同一出口不要挂太多号（页面会对同代理多账号给出提示）；风控关联主要看出口与设备指纹。
- [ ] 海外号优先用稳定出口（eSIM / 专用代理），公共代理池更容易撞风控。

## 4. 备份与恢复

数据库备份脚本与演练步骤：[../deploy/postgres-backup.md](../deploy/postgres-backup.md)。

要点：

- **必须备份**：Postgres 全库（会话串是加密的，但密钥在 `.env`，两者要一起备份且分开保存）、`.env`、素材卷。
- **建议频率**：库每日一次 + 变更前一次；素材卷每周一次（新增素材后增量）。
- **恢复演练**：至少走一次「空机器 → 恢复库 + 密钥 + 素材 → 起栈 → 账号仍在线」的完整流程，
  否则备份等于没有。演练环境见 [OPERATIONS.md](OPERATIONS.md) 第 3 节。

## 5. 升级与回滚

```bash
git pull                 # 或切到目标 tag，例如 git checkout v0.3.1
make stack-down
make stack-up            # 启动时自动跑 alembic upgrade head
make smoke               # 冒烟
```

- **迁移是加法为主**：本项目的历史迁移只做 `ADD COLUMN` / `CREATE TABLE` / `ALTER TYPE ADD VALUE`，
  回滚用 `make stack-down && git checkout <上一个 tag> && make stack-up` 通常安全。
- **回滚前先看 CHANGELOG**：如果新版本删过列或改过语义，回滚需要恢复备份。
- 每次升级对照 [../CHANGELOG.md](../CHANGELOG.md) 的对应版本条目，确认有无需要手动做的事（例如新增环境变量）。
- 版本号真源是 [`../VERSION`](../VERSION)：后端 `/health` 返回它，前端侧栏左下角显示它。

## 6. 多环境建议

| 环境 | 用途 | 数据 |
|---|---|---|
| 本地 | 开发与试跑 | 可随时清库重建 |
| 预发 | 演练迁移与回滚 | 从生产脱敏导入 |
| 生产 | 真实账号运营 | 唯一真源，定期备份 |

不要把「生产库」直接给开发环境用；改动前先在预发跑一遍迁移与验收。

## 7. 相关文档

- 起栈与首次登录：[GETTING_STARTED.md](GETTING_STARTED.md)
- 故障处置与巡检：[OPERATIONS.md](OPERATIONS.md)
- 密钥、权限与边界：[SECURITY.md](SECURITY.md)
- 验收命令：[ACCEPTANCE.md](ACCEPTANCE.md)
