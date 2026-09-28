# 运维手册

> 文档索引：[docs/README.md](README.md) · 相邻：部署 [DEPLOYMENT.md](DEPLOYMENT.md) · 安全 [SECURITY.md](SECURITY.md)

面向值班的人：告警响了先看第 1 节，页面出问题先看第 2 节，要动数据先看第 3 节。
快速开始与命令清单在 [../README.md](../README.md#5-常用命令)，备份恢复细则在
[../deploy/postgres-backup.md](../deploy/postgres-backup.md)。

- 服务组成：`postgres` / `redis` / `api` / `worker` / `frontend`，监控栈在 `monitoring` profile 下。
- 探测：`GET /health`（进程活着）、`GET /ready`（数据库与 Redis 都通，否则 503）、
  `GET /metrics`（API 指标）、`worker:9101/metrics`（Worker 指标）。
- 日志：JSON 一行一条，业务日志带 `account_id` / `worker_id` / `task_id`。

## 0. 故障速查表

| 现象 | 先看 | 常见原因 |
|---|---|---|
| 控制台打不开 | `docker compose ps`；`curl -fsS localhost:8000/ready` | api 挂了 / 数据库或 Redis 不通 / 前端 nginx 与 api 网络不通 |
| 一批号同时掉线 | 告警 1 与告警 2 是否一起响；`SELECT status, count(*) FROM tg_accounts GROUP BY 1;` | Worker 全挂（一起响）／号被 Telegram 限制、代理挂了（只有在线数掉） |
| 某个号发不出消息 | 账号状态与会话页提示；Worker 日志按 `account_id` 过滤 | 会话失效（要重新验证码）／号被冻结／代理不通 |
| 任务一直「待执行」 | `SELECT status, count(*) FROM tasks GROUP BY 1;` | Worker 副本不足／任务挂在不可认领的号上（停用、永久双向）／账号没有租约 |
| 任务「执行中」不结束 | 任务中心看 `started_at`；Worker 日志 | Telegram 调用卡住／Worker 被 SIGKILL／租约被抢 |
| 员工群收不到转发 | Bot 管理页「检查」；`/api/webhook/...` 能否 200 | `PUBLIC_BASE_URL` 不可达／`WEBHOOK_SECRET` 不一致／Bot 不在群里或没关隐私模式 |
| 备份告警 | `/var/log/tgcc-backup.log`；`make backup` | 磁盘满／`BACKUP_DIR` 不可写／cron 没装／pushgateway 没起 |

## 1. 告警处置

规则文件 `deploy/alert.rules.yml`，改完热加载：

```bash
docker compose --profile monitoring exec prometheus promtool check rules /etc/prometheus/alert.rules.yml
docker compose --profile monitoring exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload          # compose 里已开 --web.enable-lifecycle
docker compose --profile monitoring exec alertmanager amtool check-config /etc/alertmanager/alertmanager.yml
```

### 1.1 告警 1：Worker 超过 60 秒没有心跳

规则：`TgccWorkerHeartbeatStale`（`tgcc_worker_heartbeat_age_seconds > 60`，1 分钟）、
`TgccWorkerTargetDown`（`up{job="worker"} == 0`，1 分钟）、
`TgccWorkerTargetsMissing`（`absent(up{job="worker"})`，2 分钟）。

含义：这个 Worker 进程卡死或与 Postgres 断连，它持有的号不会续租；30 秒后租约过期，其他副本会接管。

处置顺序：

```bash
docker compose ps worker                                   # 是不是在反复重启
docker compose logs --tail=200 worker | jq -c 'select(.level!="INFO")'
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT worker_id, count(*) AS accounts, min(lease_until), max(last_heartbeat) FROM leases GROUP BY 1;"
docker compose restart worker                              # 兜底重启（会先释放租约再退出）
docker compose up -d --scale worker=<N>                    # 副本不够就加
```

`worker_id` 形如 `<容器主机名>-<进程号>`。Worker 已额外暴露 `tgcc_worker_info{worker_id="..."} = 1`，
所以可以直接按 `worker_id` 定位副本：

```promql
tgcc_worker_info{worker_id="<host>-<pid>"}
# 告警里要把心跳年龄和 worker_id 一起看：
tgcc_worker_heartbeat_age_seconds * on(instance) group_left(worker_id) tgcc_worker_info
```

没有 worker_info 时也可以用 `instance`（容器 IP:9101）反查容器名：

```bash
docker compose ps -q worker | xargs docker inspect \
  -f '{{.Name}} hostname={{.Config.Hostname}} ip={{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

如果只是某一个号异常，别重启 Worker：在控制台账号管理页点「释放租约」，或
`DELETE FROM leases WHERE account_id='<uuid>';`，让别的副本接管这一个号即可。

### 1.2 告警 2：在线号比例突然下降

规则：`TgccOnlineAccountsDrop`（近 5 分钟均值相对近 1 小时均值下降 > 30%，5 分钟）、
`TgccOnlineAccountsDropEarly`（15%，10 分钟，warning）、
`TgccAllAccountsOffline`（在线数为 0 但库里有 `healthy` 的号，5 分钟）。

含义：成批号掉线。注意判据是「跨副本求和」（`tgcc:online_accounts:sum`），所以扩容、滚动重启引起的
租约重分配不会误报；真的整体下降才会响。

排查：

```bash
# 控制台工作台：在线数 / 异常数 / 失败任务
curl -fsS -H "Authorization: Bearer <JWT>" http://localhost:8000/api/dashboard | jq '.online_accounts, .abnormal_accounts'

# 按状态分布：healthy 变少、frozen/invalid 变多就是号侧问题
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT status, count(*) FROM tg_accounts GROUP BY 1 ORDER BY 2 DESC;"

# 最近 15 分钟谁改了什么（审计）
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT created_at, action, target_type, target_id, detail FROM audit_logs ORDER BY created_at DESC LIMIT 20;"
```

判断方向：

- Worker 心跳/抓取类告警同时响 → Worker 侧问题（重启、扩容、数据库连接）。
- 只有在线数掉，且 `frozen` / `invalid` 变多 → 号被 Telegram 限制或会话失效，按账号逐个处置（见 2.1 / 2.2）。
- `pending` 变多、`healthy` 没变 → 只是租约还没被认领（Worker 刚重启），等 1 分钟再确认。

### 1.3 告警 3：失败或到期未执行的任务持续增加

规则：`TgccTasksFailedIncreasing`（`delta(tgcc_tasks{status="failed"}[30m]) > 5`，10 分钟，warning）、
`TgccTasksOverdue`（`tgcc_tasks{status="overdue"} > 20`，5 分钟，warning）、
`TgccTasksStuck`（`tgcc_tasks{status="stuck"} > 5`，5 分钟，critical）、
`TgccTaskQueueStalled`（pending > 50 且 15 分钟零完成，warning）。

口径（与 `app/api/metrics.py` 一致）：`overdue` = `pending` 且 `next_run_at` 已过 5 分钟；
`stuck` = `running` 且 `started_at` 已过 30 分钟。

```bash
# 按类型看失败
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT type, status, count(*) FROM tasks GROUP BY 1,2 ORDER BY 3 DESC;"

# 看失败原因（最近的）
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT id, type, account_id, attempts, max_attempts, left(error, 80) AS error, updated_at
     FROM tasks WHERE status='failed' ORDER BY updated_at DESC LIMIT 20;"

# 到期未执行：这些是没人领的
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT id, type, account_id, next_run_at, attempts
     FROM tasks WHERE status='pending' AND next_run_at < now() - interval '5 minutes'
     ORDER BY next_run_at LIMIT 20;"
```

处置：

1. **没人领**：Worker 只领「自己持有租约的账号」的任务，API 只领带 `bot_id` 的任务。所以
   任务挂在 `dead` / `disabled` 的号上会永远 `pending` —— 这类任务在控制台任务中心取消掉
   （`POST /api/tasks/{id}/cancel`）或把号改回可认领状态。
2. **领了没做完**：Worker 日志按 `task_id` 过滤；确认不是 Telegram 调用卡死；必要时在任务中心点重试
   （`POST /api/tasks/{id}/retry`，`attempts` 归零）。
3. **整体堆积**：先看 Worker 心跳与副本数，再 `docker compose up -d --scale worker=<N>`；
   同时确认数据库连接池没打满（`SELECT count(*) FROM pg_stat_activity;`）。

### 1.4 告警 4：数据库磁盘或备份失败

规则：`TgccDatabaseSizeLarge`（单库 > 20 GiB，30 分钟）、
`TgccDatabaseGrowthFast`（按 6 小时趋势，7 天内会超 40 GiB）、
`TgccBackupFailed`（`tgcc_last_successful_backup_timestamp_seconds == 0`）、
`TgccBackupOverdue`（超过 24 小时没成功）、`TgccBackupNeverReported`（25 小时没有上报，指标缺失）、
`TgccBaseBackupOverdue`（超过 8 天没有基础备份）。

磁盘：

```bash
df -h                                    # 宿主磁盘 / 卷所在分区
docker system df                         # 镜像、卷、构建缓存占用
docker run --rm -v tgcc_pgdata:/data:ro alpine du -sh /data
docker run --rm -v tgcc_pg_wal_archive:/wal:ro alpine du -sh /wal     # WAL 归档会一直涨

docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) AS size
     FROM pg_class WHERE relkind='r' ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;"
```

WAL 归档清理（只保留基础备份之后需要的段）与归档健康检查见
[../deploy/postgres-backup.md](../deploy/postgres-backup.md) 第 5 节。

备份：

```bash
tail -n 100 /var/log/tgcc-backup.log     # 中文日志：哪一步、什么错、耗时
make backup                              # 手动跑一遍复现（会在 pushgateway 上留下时间戳）
crontab -l | grep backup                 # cron 是否装上、TGCC_HOME 是否对
curl -fsS localhost:9091/metrics | grep tgcc_last_successful   # 上报值是否在推进
```

备份脚本退出码：`0` 成功；`1` 备份失败（已上报 0）；`2` 参数错误；`3` 备份成功但上报失败
（此时检查 pushgateway 是否在跑、`BACKUP_PUSHGATEWAY_URL` 是否正确）。

## 2. 常见故障

### 2.1 号被冻结（`frozen`）

现象：状态变 `frozen`，不再替它发送；用户号方向的发送任务会失败。

处置：**不要连着重试发送**（会加重限制）。在账号管理页看这个号的当前任务与最近错误，
必要时「停用」这个号（`POST /api/accounts/{id}/disable`，会清租约），让 Worker 不再认领；
等确认解除后重新检测（`POST /api/accounts/{id}/check`）再启用。
`frozen` 只影响替它发送，不影响继续收消息入库。

```bash
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT id, phone_masked, status, status_reason, current_task, last_heartbeat
     FROM tg_accounts WHERE status IN ('frozen','invalid','needs_code');"
```

`status_reason` 里是最后一次判定原因（例如 Telegram 返回的限制说明），页面账号表也能看到。

### 2.2 会话失效 / 要验证码（`invalid` / `needs_code`）

现象：状态变 `invalid`（会话打不开）或 `needs_code`（需要重新验证码）；发送任务失败。

处置：重新走一次这个号自己的验证码登录（账号管理 → 登录 → `login_start` / `login_code` /
必要时 `login_password`），成功后状态回到 `healthy`，会话串重新加密入库。

如果**所有号**同时变成 `invalid`，先怀疑 `SESSION_ENCRYPTION_KEY` 被换过（解密失败）：
密钥换了就只能重新登录所有号；这条务必写进变更记录，别在发布时顺手改 `.env`。

### 2.3 任务堆积

见 1.3。补充两点：

- `tasks.dedupe_key` 是唯一约束：同一类任务重复入队会被去重，别把它当成「任务丢了」。
- 失败重试是指数退避（`TASK_RETRY_BASE_SECONDS` 10 秒起，封顶 `TASK_RETRY_MAX_SECONDS` 600 秒），
  到 `max_attempts`（默认 5）才记 `failed`，所以「失败」出现得比想象中慢。

### 2.4 租约续期失败

现象：`tgcc_lease_renew_failures_total` 在涨，日志里出现续租失败；严重时同一个号被两个副本同时持有
（Telegram 会把旧连接踢下线，表现为反复重连）。

排查：

```bash
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT worker_id, count(*) AS accounts, min(lease_until) AS soonest FROM leases GROUP BY 1;"
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY 2;"
docker compose logs --tail=200 worker | jq -c 'select(.msg|test("租约"))'
```

常见原因：数据库连接被打满（连接池或 `max_connections` 不够）、Worker 卡在某个长任务上没能按时续租、
宿主负载过高。处置：确认 `LEASE_RENEW_SECONDS(10) < LEASE_TTL_SECONDS(30)`；
调小 `ACCOUNTS_PER_REPLICA` 或加副本；必要时重启该副本（会先释放租约）。

### 2.5 Webhook 收不到消息（Bot 不回、员工群没转发）

按顺序查：

1. **地址可达**：`PUBLIC_BASE_URL` 必须是 Telegram 能访问到的公网地址，端口只支持 80/88/443/8443，
   HTTPS 证书要有效。改完 `.env` 后 `docker compose up -d --force-recreate api`，再到 Bot 管理页点「检查」重注册。
2. **密钥一致**：回调路径是 `/api/webhook/{bot_id}/{WEBHOOK_SECRET}`，secret 不匹配直接 403。
   自测：`curl -i -X POST "https://<你的域名>/api/webhook/<bot_id>/<secret>"` → 不是 403/404。
3. **群里的可见性**：Bot 只能收到「它是成员且隐私模式已关（或设为管理员）」的群消息，系统不补收不到的消息。
4. **去重**：Telegram 重试投递的 `update_id` 会被 Redis 的 `SETNX tg:update:{bot_id}:{update_id}`（TTL 24 小时）丢掉，
   这是预期的，不会漏消息。
5. **入口反代**：如果前面还有一层 nginx/网关，确认 `/api/` 转发到了 `frontend`（或直接转发到 `api:8000`），
   并且没有对 `POST` 做拦截。
6. **看日志**：`docker compose logs --no-log-prefix api | jq -c 'select(.logger|test("webhook"))'`。

## 3. 备份与恢复演练

完整步骤在 [../deploy/postgres-backup.md](../deploy/postgres-backup.md)。这里只列演练清单：

1. 挑最新的 `backups/daily-*.dump`，恢复到临时库（`createdb` + `pg_restore`），核对
   `tg_accounts` / `messages` / `tasks` 行数，然后 `dropdb`。
2. 挑最新的 `backups/base-*.tar.gz`，用临时容器 + `recovery.signal` + `recovery_target_time`
   恢复到「昨天某个整点」，确认 `pg_is_in_recovery()` 变 `f`、`messages` 能查到该时间点的数据。
3. 记录：备份文件、目标时间点、实际恢复到的 `max(created_at)`、耗时、卡住的步骤。
4. 演练完删掉临时容器与临时库，别把演练实例留在生产宿主上。
5. 每季度一次；换过 `SESSION_ENCRYPTION_KEY`、升级过 Postgres 主版本之后必须补一次。

恢复期间：先 `docker compose stop api worker frontend` 停写入，恢复完再 `start`，
最后 `curl -fsS localhost:8000/ready` 自检，并确认 `alembic_version` 与代码版本匹配。

## 4. 容量与扩容

### 4.1 Worker

- 一个副本约 100 个在线号（`ACCOUNTS_PER_REPLICA`），扩容就是加副本：
  `docker compose up -d --scale worker=3`。
- `WORKER_METRICS_PORT_RANGE`（默认 `9101-9110`）要覆盖副本数：超过 10 个副本就把它放大，
  否则会端口分配失败。
- 一个副本要多少内存，用实测决定，不要拍脑袋：

```bash
docker stats --no-stream                       # 每个副本的 RSS / CPU
curl -fsS localhost:9101/metrics | grep tgcc_online_accounts   # 该副本当前在线号
```

  用「RSS 增量 ÷ 在线号增量」估每号开销，再定 `ACCOUNTS_PER_REPLICA`。
- 副本越多，数据库连接越多：`(DB_POOL_SIZE + DB_MAX_OVERFLOW) × (api + worker 副本数)`
  必须小于 `POSTGRES_MAX_CONNECTIONS`（默认 200），否则会出现「连不上库」引发的续租失败。

### 4.2 数据库与磁盘

- 关注 `tgcc-database-backup` 组的三条：库大小、增长趋势、备份。默认阈值 20 GiB / 40 GiB，
  改阈值改 `deploy/alert.rules.yml` 里的连乘常量。
- `messages` 是增长最快的一张表。规划里没有硬性保留期，真要清理必须先备份、先确认页面不再需要历史：

```bash
# 先看增长最快的表
docker compose exec postgres psql -U cloudctl -d cloudctl -c \
  "SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) FROM pg_class
    WHERE relkind='r' ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;"
# 建议：定期 VACUUM (ANALYZE)，不要随手 DELETE 历史消息（先备份、先和值班的人确认）
docker compose exec postgres psql -U cloudctl -d cloudctl -c "VACUUM (ANALYZE);"
```

- WAL 归档会一直涨：按 [../deploy/postgres-backup.md](../deploy/postgres-backup.md) 第 5 节用
  `pg_archivecleanup` 清到「最老基础备份所需的段」。
- 扩容磁盘：停机 → 扩卷 → `docker compose up -d`；扩卷前先做一次 `make backup`。

### 4.3 Redis

Redis 只存心跳缓存、页面推送、`update_id` 去重，**不做持久化**（`--appendonly no`，也没挂数据卷），
丢了只影响页面实时推送和 24 小时内的去重窗口，事实数据在 Postgres。
`REDIS_MAXMEMORY`（默认 256MB）+ `allkeys-lru` 防止去重键堆积吃内存。

## 5. 日常巡检

每天（或告警响了）：

- [ ] `docker compose ps`：五个服务都 running；api / worker / postgres / redis 都是 healthy。
- [ ] `curl -fsS localhost:8000/ready`：`database` 与 `redis` 都是 true。
- [ ] Prometheus `/alerts`：没有未处理的 critical。
- [ ] 工作台：在线数、异常数、失败任务数是否异常。
- [ ] `curl -fsS localhost:9091/metrics | grep tgcc_last_successful`：备份时间戳在推进。

每周：

- [ ] 看一次 `backups/` 里的日备与周备是否都在、大小是否正常（突然变小要查）。
- [ ] `SELECT * FROM pg_stat_archiver;`：`last_archived_wal` 在推进、`failed_count` 不涨。
- [ ] `docker run --rm -v tgcc_pg_wal_archive:/wal:ro alpine du -sh /wal`：归档占用。
- [ ] 失败任务清零或逐条处理（任务中心）。

每季度：

- [ ] 按第 3 节做一次恢复演练（逻辑恢复 + 按时间点恢复）。
- [ ] 复核告警阈值（在线号规模变了，30% 的绝对量也变了）。
- [ ] 复核 `.env` 里的密钥与口令是否需要轮换（轮换 `SESSION_ENCRYPTION_KEY` 需要重登所有号，要排期）。

## 6. 改指标名时同步改什么

告警规则依赖下面这些指标（完整清单在 `deploy/alert.rules.yml` 顶部注释里）：

| 指标 | 来自 | 谁在用 |
|---|---|---|
| `tgcc_online_accounts` | `app/worker/metrics.py` | 录制规则 `tgcc:online_accounts:sum` → 告警 2 |
| `tgcc_worker_heartbeat_age_seconds` | `app/worker/metrics.py` | 告警 1 |
| `tgcc_lease_renew_failures_total` / `tgcc_reconnects_total` | `app/worker/metrics.py` | 处置时参考 |
| `tgcc_tasks{status=...}` | `app/api/metrics.py` | 告警 3 |
| `tgcc_accounts{status=...}` | `app/api/metrics.py` | 告警 2 兜底、工作台核对 |
| `pg_database_size_bytes` | postgres-exporter | 告警 4（磁盘） |
| `tgcc_last_successful_backup_timestamp_seconds` 等 | `deploy/backup.sh` → pushgateway | 告警 4（备份） |

改名或改标签时，按顺序改：`backend/app/**/metrics.py` → `deploy/alert.rules.yml`（表达式 + 顶部契约注释）
→ 本文档第 6 节 → `docs/ARCHITECTURE.md` 第 9 节。改完用上面第 1 节的 `promtool` 校验并热加载。

Worker 指标里的 `tgcc_worker_info{worker_id="..."} = 1` 就是给「一眼看出是哪个副本」用的：
告警里用 `* on(instance) group_left(worker_id) tgcc_worker_info` 关联即可把 `worker_id` 带进告警正文；
`instance`（容器 IP:9101）仍可用第 1.1 节的 `docker inspect` 反查容器名。
