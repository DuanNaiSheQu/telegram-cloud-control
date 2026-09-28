# Postgres 备份与恢复

> 文档索引：[docs/README.md](../docs/README.md) · 相邻：部署 [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) · 运维 [docs/OPERATIONS.md](../docs/OPERATIONS.md)

> 备份由 `deploy/backup.sh` 执行，cron 片段见 `deploy/backup.cron`，告警规则见 `deploy/alert.rules.yml`
> 的 `tgcc-database-backup` 组。本文是恢复用的操作手册（每季度按「恢复演练」一节走一遍）。

## 1. 备份产物

| 产物 | 内容 | 频率 | 生成方 | 保留 |
|---|---|---|---|---|
| `backups/daily-<UTC>.dump` | `pg_dump -Fc` 自定义格式逻辑备份（单库、可单表恢复） | 每天 03:10 | `backup.sh daily` | 7 份（`BACKUP_KEEP_DAILY`） |
| `backups/base-<UTC>.tar.gz` | `pg_basebackup -Ft -z -X none` 物理基础备份（整个 PGDATA 的 tar） | 每周日 03:40 | `backup.sh base` | 4 份（`BACKUP_KEEP_WEEKLY`） |
| `pg_wal_archive` 卷 | Postgres 持续归档的 WAL（`archive_command` 写入，`archive_timeout=300` 保证最多 5 分钟一个段） | 持续 | postgres 容器 | 不自动清理，见第 4 节 |
| pushgateway 指标 | `tgcc_last_successful_backup_timestamp_seconds` 等 | 每次备份 | `backup.sh` | 每次覆盖 |

两条要点：

1. **逻辑备份用于日常误删**：恢复单库、单表最快，不需要停库。
2. **物理备份 + WAL 归档用于按时间点恢复（PITR）**。base 备份用 `-X none` 生成
   （pg_basebackup 不允许「tar 格式 + stdout + `-X stream`」，实测报错
   `cannot stream write-ahead logs in tar mode to stdout`），所以：
   **`base-*.tar.gz` 单独不可恢复，必须连同 `pg_wal_archive` 里的 WAL 一起用。**
   两个都要纳入异地/离线备份，缺一个 PITR 就不成立。

## 2. 先做无损校验（任何恢复之前）

```bash
cd <仓库根目录>

# 2.1 逻辑备份能不能读（不碰生产库）
pg_restore -l backups/daily-<UTC>.dump | head

# 2.2 真恢复到一个临时库，确认行数正常（不碰生产库）
docker compose exec -T postgres createdb -U cloudctl verify_restore
docker compose exec -T postgres pg_restore -U cloudctl -d verify_restore --no-owner < backups/daily-<UTC>.dump
docker compose exec -T postgres psql -U cloudctl -d verify_restore -c "SELECT count(*) AS accounts FROM tg_accounts;"
docker compose exec -T postgres psql -U cloudctl -d verify_restore -c "SELECT count(*) AS messages FROM messages;"
docker compose exec -T postgres dropdb -U cloudctl verify_restore
```

## 3. 场景 A：逻辑恢复（误删数据 / 单表回滚）

```bash
# 3.1 停写入，避免恢复过程中又产生新数据
docker compose stop api worker frontend

# 3.2 最保险：整库替换（会丢掉「备份时间点之后」的数据，请先确认时间点）
docker compose exec -T postgres psql -U cloudctl -d postgres -c 'DROP DATABASE cloudctl WITH (FORCE);'
docker compose exec -T postgres psql -U cloudctl -d postgres -c 'CREATE DATABASE cloudctl OWNER cloudctl;'
docker compose exec -T postgres pg_restore -U cloudctl -d cloudctl --no-owner < backups/daily-<UTC>.dump

# 3.3 只回滚一张表（例如误删了 tg_accounts 的几行）：先恢复到临时库，再按需导回
docker compose exec -T postgres createdb -U cloudctl t3_restore
docker compose exec -T postgres pg_restore -U cloudctl -d t3_restore --no-owner -t tg_accounts < backups/daily-<UTC>.dump
docker compose exec -T postgres psql -U cloudctl -d cloudctl -c \
  "INSERT INTO tg_accounts SELECT * FROM t3_restore.tg_accounts ON CONFLICT (id) DO NOTHING;"
docker compose exec -T postgres dropdb -U cloudctl t3_restore

# 3.4 起服务并自检
docker compose start api worker frontend
curl -fsS http://127.0.0.1:8000/ready
```

恢复后只要 `.env` 里的 `SESSION_ENCRYPTION_KEY` 没变，库里加密的会话与 Bot Token 仍可解密，
号不需要重新登录；**换过密钥就必须重新登录所有号**。

## 4. 场景 B：按时间点恢复（PITR）

前提：有 `base-*.tar.gz`，并且 `pg_wal_archive` 里有该基础备份之后到目标时间点的所有 WAL。

```bash
cd <仓库根目录>
TS=20260928T123201Z          # 选一个基础备份
TARGET='2026-09-28 20:00:00+08'   # 想恢复到的时间点（要晚于基础备份时间）

# 4.1 停写入；同时保留现场（把当前数据目录另存一份，别直接覆盖）
docker compose stop api worker frontend postgres
mkdir -p restore/pgdata restore/wal
docker run --rm -v tgcc_pgdata:/data:ro -v "$PWD/backups":/out alpine \
  tar -czf /out/pgdata-broken-$(date +%Y%m%d%H%M).tar.gz -C /data .

# 4.2 解开基础备份（tar 顶层就是 PGDATA：backup_label / base/ / pg_wal/ ...）
tar -xzf "backups/base-$TS.tar.gz" -C restore/pgdata

# 4.3 把 WAL 归档拷贝出来（恢复实例要能读到）
docker run --rm -v tgcc_pg_wal_archive:/wal:ro -v "$PWD/restore/wal":/out alpine \
  sh -c 'cp -a /wal/. /out/'

# 4.4 写恢复配置（recovery.signal 是 PG12+ 的方式）
touch restore/pgdata/recovery.signal
cat >> restore/pgdata/postgresql.auto.conf <<EOF
restore_command = 'cp /wal-archive/%f %p'
recovery_target_time = '$TARGET'
recovery_target_action = 'promote'
EOF

# 4.5 属主必须是容器里的 postgres（alpine 镜像 uid=70）
docker run --rm -v "$PWD/restore/pgdata":/data alpine chown -R 70:70 /data
chmod 700 restore/pgdata

# 4.6 用临时实例起来验证（不同容器名、只绑本地 55433，不动生产卷）
docker run --rm --name tgcc-restore \
  -e PGDATA=/var/lib/postgresql/data/pgdata \
  -v "$PWD/restore/pgdata":/var/lib/postgresql/data/pgdata \
  -v "$PWD/restore/wal":/wal-archive:ro \
  -p 127.0.0.1:55433:5432 postgres:16-alpine
# 另开一个终端：
psql "postgresql://cloudctl@127.0.0.1:55433/cloudctl" -c "SELECT pg_is_in_recovery();"   # 恢复中为 t
psql "postgresql://cloudctl@127.0.0.1:55433/cloudctl" -c "SELECT count(*), max(created_at) FROM messages;"
# 日志里出现 "recovery stopping before ... / database system is ready to accept connections" 即完成

# 4.7 验证通过后切回生产：停临时实例，把恢复数据搬回生产卷，再起服务
docker stop tgcc-restore
docker run --rm -v tgcc_pgdata:/data -v "$PWD/restore/pgdata":/restore alpine \
  sh -c 'rm -rf /data/* && cp -a /restore/. /data/'
docker compose up -d postgres
docker compose exec -T postgres psql -U cloudctl -d cloudctl -c 'SELECT * FROM alembic_version;'
docker compose up -d api worker frontend
curl -fsS http://127.0.0.1:8000/ready
```

常见坑：

- **恢复到的时间点晚于归档末尾 → 恢复会一直等 WAL**。`archive_timeout=300` 只能保证「最多丢 5 分钟」，
  最后一段未写完的 WAL 不在归档里；必要时把 `recovery_target_time` 往前挪，或改成
  `recovery_target = 'immediate'`（恢复到基础备份结束时，不需要 WAL 归档）。
- **权限**：PGDATA 属主必须是 70:70、权限 700，否则容器起来就报 `data directory has invalid permissions`。
- **别在生产卷上直接试**：先按 4.6 用临时卷验证，确认数据对了再搬回去。
- **搬回生产卷前先确认卷名**：`docker volume ls | grep tgcc`（项目名固定 `tgcc`，卷名形如 `tgcc_pgdata`）。
- `restore_command` 里的路径是**容器内**路径（`/wal-archive/%f`），不是宿主路径。

## 5. WAL 归档的保留与清理

归档卷会一直涨。清理原则：**至少保留到最老的那个基础备份所需的 WAL**。

```bash
# 从基础备份里读出起始 WAL 文件（START WAL LOCATION）
tar -xzOf backups/base-<TS>.tar.gz backup_label | grep 'START WAL LOCATION'

# 在容器里删掉该文件之前的归档段（pg_archivecleanup 会保留指定段本身）
docker compose exec -T postgres pg_archivecleanup /var/lib/postgresql/wal-archive 0000000100000000000000XX

# 看归档是否在正常工作：last_archived_wal 在推进、failed_count 不涨
docker compose exec -T postgres psql -U cloudctl -d cloudctl -c 'SELECT * FROM pg_stat_archiver;'
```

顺带看一眼归档占用：

```bash
docker run --rm -v tgcc_pg_wal_archive:/wal:ro alpine du -sh /wal
```

## 6. 恢复演练（每季度一次）

1. 挑最新的 `daily-*.dump`，按第 2 节恢复进临时库，核对 `tg_accounts` / `messages` / `tasks` 行数。
2. 挑最新的 `base-*.tar.gz`，按第 4 节恢复到临时实例，再用 `recovery_target_time` 指到「昨天某个整点」，
   确认 `pg_is_in_recovery()` 变 `f`、`messages` 里能看到该时间点的数据。
3. 记录：用的备份文件、目标时间点、实际恢复到的 `max(created_at)`、耗时、卡住的步骤。
4. 演练完删掉临时库/临时容器（`dropdb` / `docker rm -f tgcc-restore`），别把演练实例留在生产宿主上。

## 7. 备份失败时的处置

| 现象 | 处理 |
|---|---|
| 告警 `TgccBackupFailed`（指标被推 0） | 看 `/var/log/tgcc-backup.log`；手动 `make backup` 复现；常见是磁盘满、`BACKUP_DIR` 不可写、postgres 容器不健康 |
| 告警 `TgccBackupOverdue`（>24h 没成功） | 确认宿主 cron 装没装（`crontab -l`）、`docker` 在当前用户 PATH 里、`BACKUP_MODE=docker` 时当前用户在 docker 组 |
| 告警 `TgccBackupNeverReported`（指标缺失） | pushgateway 没起（`make monitoring`）或 `BACKUP_PUSHGATEWAY_URL` 不对；脚本退出码 3 表示「备份成功但上报失败」 |
| 告警 `TgccBaseBackupOverdue`（>8 天） | 手动 `BACKUP_KIND=base deploy/backup.sh`；同时确认 `archive_mode=on`（脚本会自己检查并告警） |
