# 账号矩阵：导入、验活、防封与批量管理

这套控制台把「一批 Telegram 账号」当作**资产**来管：怎么进来、还剩多少额度、
这个号还能不能干活、什么时候该停手。对应实现分布在
`services/account_import.py`（导入）、`services/throttle.py`（节流）、
`worker/task_runner.py`（验活）、`api/routers/accounts_bulk.py`（批量动作）。

## 1. 有哪几种导入方式

前端入口：**账号管理 → 批量导入**（`POST /api/accounts/import`）。
所有导入都会写一条批次记录（`account_imports`），可回溯「这批号哪来的、谁导的、失败原因」。

| 方式 | 输入 | 行为 | 说明 |
|---|---|---|---|
| 手机号清单 | 每行一个号，可带备注：`+8613800138000,北京一组` | 建档，状态 `待登录` | 之后走「登录向导」发验证码拿会话 |
| Session 串 | 每行一个 Telethon StringSession；也支持 `手机号,session` / `session,备注` | 解析校验后加密入库，状态直接 `正常` | 最常用的批量方式 |
| `.session` 文件 | Telethon / Pyrogram 的 SQLite 会话文件，可多选 | 读 `auth_key` + `dc_id` 组装成 StringSession 入库 | 兼容 hex / base64 / BLOB 三种存法 |
| `tdata` 目录 | Telegram Desktop 的 tdata 打包成 zip（可含多账号） | 交给 `opentele2` 转成 Telethon 会话 | **可选依赖**：没装时接口会明确提示不可用并给替代路径 |

导入时的统一处理：

- **去重**：先按 `tg_user_id`，再按手机号确定性哈希（`phone_hash`）。
  注意 `phone_enc` 是 Fernet 密文（带随机 IV），**不能**拿密文做等值查询——
  这是早期版本重复号码识别不出来的根因，现已用哈希列解决。
- **设备指纹**：每个号随机分配 机型 / 系统版本 / 客户端版本 / 语言（`DEVICE_POOL`），
  连接时由 `AccountSnapshot` 带入 `TelegramClient`。一批号用同型号同版本是最容易被关联的特征。
- **代理与分组**：导入时可直接绑定一个代理、归入一个分组，避免后继再批量补。
- **养号起点**：可选择「从今天起算」，新号自动落到最严额度档。
- 单次上限 `IMPORT_MAX_ACCOUNTS`（默认 500），超了直接 400，不会把库打满。

`GET /api/accounts/import/formats` 会告诉前端每种格式的说明、`accept` 与 tdata 是否可用，
所以前端不需要写死格式清单。

## 2. 验活：从「连得上」到「还能不能干活」

两档：

- **轻检**（普通「批量检测」）：确认会话能连、能 `getMe`，写回账号状态。
- **深度验活**（`POST /api/accounts/bulk/probe`）：额外做四件事，复算 `health_score`（0-100）：

| 探测 | 记录字段 | 扣分 |
|---|---|---|
| 读权限：`getDialogs(limit=1)` | `read_ok` / `read_error` | 失败 −30 |
| 授权会话数：`account.GetAuthorizations` | `auth_count`（突然变多说明可能被异地登录） | 仅记录 |
| 写权限（可选，勾选 `write_probe`）：往自己的收藏夹发一条 | `write_ok` / `write_error` / `flood_wait` | 限流 −25，其它失败 −45 |
| 账号状态与历史限流次数 | `flood_strikes` ≥ 3 | −15；状态非正常 −25 |

结果写入 `health_score` / `health_checked_at` / `health_detail` / `risk_flags`，
账号页「健康」列按 绿 ≥80 / 黄 ≥50 / 红 <50 展示；详情抽屉的
`GET /api/accounts/{id}/matrix` 能看到明细与当前节流快照。

## 3. 防封：四道闸门 + 一个阶梯

发送类动作（单条发送、批量私信、群发、素材群发、加群、强拉、吵群、拟人）在真正调 Telegram 之前
都要过 `services/throttle.py` 的闸门，不通过就**顺延**（可重试失败 + `requeue_after`），绝不硬发：

1. **熔断**：`flood_until` 未到期 → 直接挡。收到 FloodWait 时写入
   `wait + THROTTLE_FLOOD_COOLDOWN_SECONDS`，并累加 `flood_strikes`；≥3 次后当日额度自动减半。
2. **活跃时段**：默认只在本地 `08:00–24:00` 动作（`THROTTLE_ACTIVE_HOURS`）。凌晨批量操作是典型机器特征。
3. **动作间隔**：两次动作之间至少 N 秒，按号龄从 120 秒（新号）递减到 20 秒（老号）。
4. **每日配额**：Redis 按号计数（`tgcc:throttle:<account>:<yyyymmdd>`，当天过期）。

**养号阶梯**（`WARMUP_LADDER`，号龄按 `warmup_started_at` → `authorized_at` → 建档时间取第一个可用的）：

| 号龄 | 每日上限 | 最小间隔 |
|---|---|---|
| 0-2 天 | 20 | 120 秒 |
| 3-6 天 | 50 | 60 秒 |
| 7-13 天 | 80 | 45 秒 |
| 14-29 天 | 120 | 30 秒 |
| ≥30 天 | `THROTTLE_DAILY_DEFAULT`（默认 200） | 20 秒 |

**动作权重**：一条消息算 1，群发/吵群/拟人/加群/强拉算 3（`ACTION_COST`），
读取类动作（同步会话、检测、改资料）不消耗额度。
于是「一天发 20 条私信」和「一天进 20 个群」对账号的损耗不会被同等对待。

**人工旋钮**：`POST /api/accounts/bulk/throttle` 可批量设置
`daily_message_limit`（0 = 回到自动阶梯）、`min_action_seconds`（0 = 自动）、
`reset_flood`（解除熔断）、`start_warmup_now`（重置养号起点）。

配套的还有：批量动作入队时按 `CAMPAIGN_STAGGER_SECONDS` 错峰、
文本池按号分配（不同号说不同的话）、口语化微调、随机间隔（`worker/humanize.py`）。

## 4. 批量管理清单

| 动作 | 接口 | 说明 |
|---|---|---|
| 批量导入 | `POST /api/accounts/import` | 四种来源；写批次记录与逐条结果 |
| 批量检测 / 深度验活 | `POST /api/accounts/bulk/check`、`/bulk/probe` | 后者复算健康分 |
| 批量设置节流 | `POST /api/accounts/bulk/throttle` | 额度、间隔、解熔断、重置养号 |
| 批量改资料 | `POST /api/campaigns/profile-update` | 改名/简介/用户名/头像，支持按号覆盖 |
| 批量加群 / 退群 / 强拉 | `POST /api/campaigns/join-group`、`/leave-group`、`/force-add` | 高风险动作按权重计费 |
| 批量改分组 / 代理 / 停用启用 / 清租约 | `POST /api/accounts/bulk/*` | 账号运维动作 |
| 批量私信 / 群发 / 素材群发 / 吵群 / 拟人 | `POST /api/campaigns/*` | 按批次执行，可查进度、可取消 |
| 批量导出 | `GET /api/exports/{resource}.csv` | 账号、会话、消息、任务、审计 |

## 5. 验收

    cd backend && .venv/bin/python -m tests.matrix_check     # 14 项：导入/去重/节流/验活/矩阵状态
    cd backend && .venv/bin/python -m tests.campaign_api     # 30 项：批量运营
    backend/.venv/bin/python scripts/e2e_check.py            # 41 项：既有回归

## 6. 环境变量

| 变量 | 默认 | 作用 |
|---|---|---|
| `THROTTLE_DAILY_DEFAULT` | 200 | 号龄足够后的每日上限 |
| `THROTTLE_ACTIVE_HOURS` | `8-24` | 允许动作的活跃时段（本地时区） |
| `THROTTLE_FLOOD_COOLDOWN_SECONDS` | 30 | FloodWait 之外额外冷却 |
| `IMPORT_MAX_ACCOUNTS` | 500 | 单次导入上限 |
| `MATERIALS_DIR` | `materials` | 素材落盘目录 |

## 7. 群情报：入群即采（无感）

对应实现：`models/group_intel.py`（三张表）、`services/group_intel.py`（写入口径）、
`worker/group_intel.py`（事件监听 + 采集任务）、`api/routers/group_intel.py`（查询与导出）。

**无感三条纪律**（代码里逐条落实，不是口号）：

1. 事件回调**只写库**——不回复、不打招呼、不加表情、不撤回，群里看不到任何动作；
2. 采集只用读接口（`GetFullChannel` / `GetFullChat` / `GetParticipants`），不发言、不加群；
3. 成员名单按页拉取，页间 `GROUP_INTEL_PAGE_INTERVAL_SECONDS`（默认 3 秒），单任务上限
   `GROUP_INTEL_MAX_MEMBERS_PER_TASK`（默认 500）——大群不一次性拉全量。

**采到什么**

| 表 | 内容 | 来源 |
|---|---|---|
| `group_profiles` | 群名、用户名、类型、成员数、简介、邀请链接、创建时间、是否公开/受限、采集进度 | 事件被动更新 + `collect_group` 只读拉取 |
| `group_members` | 用户 ID、用户名、昵称、是否机器人/会员/管理员、在群状态、入群时间、最近出现、发言数 | 入群事件增量 + `collect_members` 名单同步 + 群内发言 |
| `group_events` | 入群 / 被邀请入群 / 退群 / 被移除，含「被谁拉进来」 | ChatAction 事件回调（Worker 常驻监听） |

**接口**

```
POST /api/group-intel/collect               {选择器, dialog_ids?, limit_groups, sample_members, with_members, member_limit}
GET  /api/group-intel/stats                 概览：群数 / 成员数 / 机器人 / 今日入退群
GET  /api/group-intel/profiles              群档案列表（关键词、成员数下限、只看公开群、排序分页）
GET  /api/group-intel/profiles/{id}         详情：成员状态分布、机器人数量、事件分布
GET  /api/group-intel/profiles/{id}/members 成员名单（真人/机器人过滤、状态、来源、搜索）
GET  /api/group-intel/events                事件流（按群、类型、最近 N 小时）
GET  /api/group-intel/members.csv           导出成员（Excel 友好）
```

**开关**：`GROUP_INTEL_WATCH_ENABLED=false` 可关掉入群监听（只保留手动采集），
页面会显式提示「事件监听已关闭」，避免以为流水在积累而实际没有。

验收：`cd backend && .venv/bin/python -m tests.group_intel_check`（10 项）。
