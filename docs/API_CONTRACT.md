# API 契约（v1）

内部运维控制台。所有时间戳为带时区的 ISO8601（UTC）；所有 ID 为 UUID 字符串；字段命名 snake_case。
基址：`http://<host>:8000`。

## 1. 鉴权

- 除 `POST /api/auth/login`、`POST /api/webhook/{bot_id}/{secret}`、`/health`、`/ready`、`/metrics` 外，全部需要
  `Authorization: Bearer <JWT>`。
- 员工角色：`admin`（看全部账号、可管员工）、`operator`（只能看/操作被分配到的账号）。
- 未授权 401，无权限 403。
- 错误统一 `{"detail": "原因"}`。

```
POST /api/auth/login        {"username","password"} → {access_token,token_type,expires_in,user}
GET  /api/auth/me                                    → UserOut
POST /api/auth/logout                                → {ok,message}
```

## 2. 工作台

```
GET /api/dashboard → DashboardOut
```

```json
{
  "total_accounts": 0, "online_accounts": 0, "abnormal_accounts": 0, "leased_accounts": 0,
  "total_dialogs": 0, "unread_dialogs": 0, "total_bots": 0,
  "tasks_pending": 0, "tasks_running": 0, "tasks_failed": 0, "tasks_overdue": 0, "tasks_stuck": 0,
  "workers": [{"worker_id":"w1","last_heartbeat":"...","online_accounts":3,"leased_accounts":3,"stale":false,"source":"redis"}],
  "recent_failures": [{"id":"...","type":"send_message","type_label":"单条发送","account_id":"...","account_label":"138****8888","error":"...","attempts":5,"max_attempts":5,"created_at":"..."}],
  "generated_at": "..."
}
```

## 3. 账号管理

```
GET    /api/accounts?page=1&page_size=20&group_id=&status=&current_task=&phone=&keyword=&sort=&order=
       → {items:[AccountOut], total, page, page_size, summary:AccountSummary}
GET    /api/accounts/summary → AccountSummary
POST   /api/accounts              AccountCreate          → AccountOut      # 建档（不自动登录）
GET    /api/accounts/{id}                                → AccountOut
GET    /api/accounts/{id}/overview                       → AccountOverviewOut  # 抽屉聚合，见第 13 节
PATCH  /api/accounts/{id}         AccountUpdate          → AccountOut
POST   /api/accounts/{id}/disable                        → {ok,message}    # status=disabled，清租约
POST   /api/accounts/{id}/enable                         → {ok,message}    # status=pending/healthy
DELETE /api/accounts/{id}                                → {ok,message}
POST   /api/accounts/{id}/release-lease                  → {ok,message}    # 单号异常时只清它的租约
POST   /api/accounts/{id}/sync-dialogs                   → {ok,message,task_id}
POST   /api/accounts/{id}/check                          → CheckResultOut
POST   /api/accounts/check        {"account_ids":[...]|null,"scope":"selected|all|group:<uuid>"} → [CheckResultOut]
POST   /api/accounts/{id}/profile {"first_name","last_name","bio","username","photo_url"}   → {ok,message,task_id}
```

批量动作（检测 / 同步会话 / 分配 / 改分组 / 改代理 / 停用启用 / 清租约）见第 11 节，
导出 CSV 见第 12 节，排序字段见第 16 节。

`PATCH /api/accounts/{id}` 的字段语义（`exclude_unset`）：

| 字段 | 传 null 的含义 |
|---|---|
| `group_id` / `proxy_id` | **解绑**（显式传 `null` 才解绑；不传该字段表示不改） |
| `remark` / `display_name` | 不可空文本，传 `null` 视为「没改」 |
| `status` | 只允许 `disabled`（停用）或 `healthy`（启用），其它状态由 Worker 按实况写回 |

`AccountSummary`：`{total, healthy, abnormal, new_this_week, online, leased}`
（页面四块汇总：总数、正常、异常、本周新增）。

### 单号登录（验证码只走这个号自己）

```
POST /api/accounts/login/start    {"phone"?,"group_id"?,"proxy_id"?,"account_id"?} → LoginStepResponse
POST /api/accounts/login/code     {"account_id","code"}                           → LoginStepResponse
POST /api/accounts/login/password {"account_id","password"}                       → LoginStepResponse
```

`phone` 与 `account_id` 至少给一个：
- 只给 `phone`：先建档（手机号重复则复用已有号）再发码；
- 只给 `account_id`：已有号重新登录，手机号从库里加密保存的 `phone_enc` 解出来，
  值班的人不必对着脱敏号（`861****2551`）重敲一遍。

`LoginStepResponse`：`{account_id, step: "code_required"|"password_required"|"done", message, task_id}`
步骤由 Worker 执行 Telethon 登录：`login_start` 发验证码，`login_code` 提交，若开了两步验证返回
`password_required`，否则 `done` 并把会话加密写回 `tg_accounts.session_enc`；
登录成功后 Worker 会**自动补一条 `sync_dialogs` 任务**（规划第一步：登录后拉出已有群和私信）。

### 账号检测

`CheckResultOut`：`{account_id, phone_masked, reachable, status, status_label, message, task_id}`
检测含义：连得上（`healthy`）、要验证码（`needs_code`）、会话失效（`invalid`）。
接口会写一条 `account_check` 任务并立刻续一次租约，Worker 读到后读一次状态写回该行。

### 账号表列（前端照此渲染）

手机号、用户名、用户 ID、号龄、群数量、分组、代理、状态、当前任务、最后心跳。
筛选：分组、状态、任务状态、手机号。排序字段见第 16 节。

## 4. 账号分组 / 网络（代理）/ 员工分配

```
GET/POST         /api/groups                → [GroupOut] / GroupOut
PATCH/DELETE     /api/groups/{id}
POST             /api/groups/{id}/accounts  {"account_ids":[...]}          → {ok,message}
POST             /api/groups/{id}/accounts/remove {"account_ids":[...]}    → {ok,message}

GET/POST         /api/proxies               → [ProxyOut] / ProxyOut
PATCH/DELETE     /api/proxies/{id}
POST             /api/proxies/{id}/accounts {"account_ids":[...]}          → {ok,message}

GET              /api/users                 → [UserOut]
POST             /api/users                 UserCreate (admin)             → UserOut
PATCH/DELETE     /api/users/{id}            (admin)
GET              /api/assignments           → [AssignmentOut]
POST             /api/assignments           {"user_id","account_ids":[...]} → AssignmentOut
DELETE           /api/assignments           ?user_id=&account_ids=a,b      → {ok,message}
```

`GroupOut`：`{id,name,description,account_count,created_at}`
`ProxyOut`：`{id,name,scheme,host,port,endpoint,has_auth,enabled,remark,account_count,created_at}`
（用户名/密码加密保存，只回 `has_auth`）

## 5. 会话（群聊 / 私信 / Bot 私信）

```
GET  /api/dialogs?channel=user_account|bot&kind=private|group&account_id=&bot_id=&keyword=&q=&only_unread=&page=&page_size=&sort=&order=
     → {items:[DialogOut], total, page, page_size}
GET  /api/dialogs/{id}                    → DialogOut
GET  /api/dialogs/{id}/messages?limit=50&before=<ISO>&q=<正文>  → {items:[MessageOut], total, dialog, has_more}
POST /api/dialogs/{id}/read               → {ok,message}      # 未读清零
POST /api/dialogs/{id}/sync  {"limit":50} → {ok,message,task_id}   # 拉该会话历史消息
GET  /api/dialogs/{id}/drafts             → [DraftOut]
POST /api/dialogs/{id}/draft {"instruction"}  → DraftOut      # AI 草稿，停在输入框
DELETE /api/drafts/{id}                   → {ok,message}      # 丢弃草稿
POST /api/messages/send   {"dialog_id","text","draft_id"?}    → SendMessageResponse
GET  /api/messages?q=&channel=&kind=&account_id=&dialog_id=&direction=&status=&page=&page_size=&sort=&order=
                                          → {items:[MessageOut], total, page, page_size}   # 跨会话搜索，见第 16 节
```

- `/api/dialogs` 的 `q` 与 `keyword` 等价：跨**标题、对方、用户名、最近预览和消息正文**搜索；
- `/api/dialogs/{id}/messages` 固定按时间正序返回（聊天视图），用 `before` 往前翻；`q` 只在正文里搜；
  要按字段排序请用 `GET /api/messages`；
- operator 只能看到（搜到）自己分配账号下的会话与消息，Bot 会话人人可见；越权 403。

`SendMessageResponse`：`{ok, message, task_id, status: "pending"|"sent", detail}`

发送规则（两条通道分开）：

| 会话通道 | 行为 |
|---|---|
| `user_account` | 预写一条 `messages`（direction=outgoing, status=pending）并写 `send_message` 任务，等持有租约的 Worker 发出后回填 `tg_message_id`、status=sent。账号不在 `healthy` → 409 |
| `bot` | API 直接用 Bot API 发出，立即写 `messages`（status=sent），回 `task_id=null` |

带 `draft_id` 时发送成功后把 `reply_drafts.status=sent`、`sent_by`、`sent_at` 写全（审计里记是谁点的）。

## 6. 任务中心

```
GET  /api/tasks?status=&type=&account_id=&bot_id=&only_failed=&page=&page_size=&sort=&order=
     → {items:[TaskOut], total, page, page_size, counts:{pending,running,failed,completed,cancelled,pending_confirmation}}
GET  /api/tasks/{id}            → TaskOut
POST /api/tasks/{id}/retry      → {ok, task, message}     # failed/pending_confirmation → pending，attempts 归零
POST /api/tasks/{id}/cancel     → {ok, task, message}
POST /api/tasks/bulk/retry      {"task_ids":[...]}        # 批量重试，最多 200 条，逐条给结果
```

排序字段见第 16 节；失败任务同时会进通知流（第 15 节）。

批量重试（队列运维动作，不是批量发送）：

```json
POST /api/tasks/bulk/retry   {"task_ids": ["…"]}   // 最多 200 个，重复 id 只处理一次
→ {"ok": true, "requested": 4, "succeeded": 2, "failed": 2,
   "results": [
     {"task_id": "…", "ok": true,  "message": "已重新排队，等待 Worker 领取"},
     {"task_id": "…", "ok": false, "message": "任务不存在"},
     {"task_id": "…", "ok": false, "message": "该任务类型不允许批量重试，请在任务详情里单独重试"},
     {"task_id": "…", "ok": false, "message": "当前状态「completed」不能重试：只允许失败或等待确认的任务"},
     {"task_id": "…", "ok": false, "message": "账号未分配给你"}
   ]}
```

**类型白名单**：

| 允许批量重试 | 禁止批量重试（`ok:false` + 固定提示） |
|---|---|
| `sync_dialogs`、`sync_messages`、`account_check`、`update_profile`、`relay_to_staff` | `send_message`、`login_start`、`login_code`、`login_password`、`bot_reply`、`reply_to_origin` |

批量运营类本身就是批量动作，失败后整批重新排队正是运营场景。单条发送（走人工确认通道）、
登录类与 Bot 回复类只能在任务详情里**单条**重试（`POST /api/tasks/{id}/retry` 不受白名单限制）。

- 逐条给结果：某一条不可重试**不会**让整个请求失败（顶层 `ok = (failed == 0)`）；
- 判断顺序：任务存在 → 可见范围 → **类型白名单** → 状态；被类型拦下的任务状态不会被改动；
- 任务不存在 → `ok:false`（不 404、不 500）；operator 拿到不属于自己账号的任务 → `ok:false, "账号未分配给你"`；
- 语义与单条重试一致：`failed` / `pending_confirmation` → `pending`，`attempts` 归零；
- 空 `task_ids` → 400；超过 200 个 → 422；写一条 `task.bulk_retry` 汇总审计（detail 里带 `blocked_types` 计数）。

`TaskOut` 里 `type_label` / `status_label` 用中文（见 `app/models/enums.py`），
`account_label` 为脱敏手机号，`created_by_name` 为操作员工。

## 7. Bot 与转发

```
GET    /api/bots                 → [BotOut]
POST   /api/bots                 BotCreate → BotOut    # 调 getMe 校验 Token，成功后注册 Webhook
PATCH  /api/bots/{id}            BotUpdate → BotOut
DELETE /api/bots/{id}                                 → {ok,message}
POST   /api/bots/{id}/webhook    {"enable":true}       → {ok,message}   # 注册/删除 Telegram Webhook
GET    /api/bots/{id}/check                            → BotOut        # 重新 getMe，回填 username

GET    /api/relays               → [RelayRouteOut]
POST   /api/relays               RelayRouteCreate → RelayRouteOut
POST   /api/relays/test          {"bot_id","chat_id","text"?} → {ok,message,detail,staff_message_id}   # 发一条测试消息
PATCH  /api/relays/{id}          RelayRouteUpdate → RelayRouteOut
DELETE /api/relays/{id}                                → {ok,message}
GET    /api/relays/links?route_id=&page=&page_size=    → {items:[RelayLinkOut], total}
GET    /api/audit?action=&user_id=&account_id=&bot_id=&from=&to=&page=&sort=&order=  → {items:[AuditOut], total, page, page_size}
```

`POST /api/relays/test`（仅 admin）：不依赖已保存的规则，保存规则前也能先试通；只发**一条**消息到
指定的员工聊天，不碰任何用户号。`text` 不传用默认文案，最长 4096 字符。
失败：Bot 不存在 / Token 解不开 → 400；Telegram 拒绝（Bot 不在群里、没和它说过话、被拉黑等）→ 409；
上游异常 → 502，`detail` 一律中文。写 `relay.test` 审计。

`GET /api/audit` 的时间范围：`from` / `to` 为 ISO8601（可带时区；不带时区按 UTC），作用在 `created_at`
上且**都是闭区间**；`from > to` → 400 `时间范围不合法：from 不能晚于 to`。
`GET /api/export/audit.csv` 支持同样的 `from`/`to`。

`RelayLinkOut` 除了表上的列，还带列表页要用的上下文（由路由回填）：
`origin_body`（原消息正文，截断 500 字）、`origin_sender_name`、`origin_dialog_title`、
`origin_dialog_id`（原会话 id，详情抽屉「跳原会话」深链 `/dialogs` 用）、
`account_label`（脱敏手机号；Bot 会话为 null）、`origin_created_at`。
这样「已转发记录」能看出转的是什么，而不是一串 ID。

`BotOut.token_masked` 只回 `123456...abcd`，永不回明文。

### Telegram 回调（无 JWT）

```
POST /api/webhook/{bot_id}/{secret}
```

处理顺序（必须）：
1. 校验 `secret == settings.webhook_secret`，否则 403。
2. Redis `SETNX tg:update:{bot_id}:{update_id}`（TTL 24h）去重，重复直接 200 丢弃
   （`core.events.seen_update`）。
3. 私信 / 群里能看到的普通消息 → `services.inbound.ingest_message` 入库
   （channel=`bot`），再 `services.relay.enqueue_relays` 写 `relay_to_staff` 任务；
   若该 Bot `auto_reply_enabled` 再写一条 `bot_reply` 任务。
4. 员工群里的回复：`update.message.reply_to_message.message_id` 去 `relay_links` 找原会话
   （`services.relay.find_origin_by_staff_reply`），写 `reply_to_origin` 任务。
5. Bot 群消息只在 Bot 是该群成员（管理员或已关隐私模式）时才会到达，系统不补收不到的消息。

## 8. WebSocket

```
WS /api/ws?token=<JWT>
```

客户端 → 服务端：

```json
{"op":"subscribe","dialog_ids":["..."]}
{"op":"unsubscribe","dialog_ids":["..."]}
{"op":"ping"}
```

服务端 → 客户端：

```json
{"kind":"hello","dialogs":["..."]}
{"op":"pong"}
{"kind":"message","dialog_id":"...","message":{...},"dialog":{...}}
{"kind":"account","account_id":"...","status":"healthy","current_task":"idle","last_heartbeat":"..."}
{"kind":"task","task_id":"...","type":"relay_to_staff","ok":true,"detail":""}
```

只推当前打开的会话（按 `dialog_ids` 过滤）。Redis 里丢了推送不影响数据。

## 9. 运维探测

```
GET /health   → {"status":"ok","service":"api","version":"1.0.0"}          # 进程活着
GET /ready    → {"status":"ready","database":true,"redis":true}             # 200；任一不通 → 503
GET /metrics  → Prometheus 文本（API 侧任务积压、账号状态计数）
```

业务趋势（画折线用的时间序列）在 `GET /api/metrics/trends`，见第 14 节；`/metrics` 只给 Prometheus 抓取。

Worker 单独暴露 `:9101/metrics`：在线号数量、重连次数、任务成功/失败、租约续期失败。

## 10. 任务载荷约定（API 写入，Worker / API 读取）

| type | 执行方 | payload |
|---|---|---|
| `sync_dialogs` | Worker | `{}`（账号取自 `account_id`） |
| `sync_messages` | Worker | `{"dialog_id","limit"}` |
| `send_message` | Worker | `{"dialog_id","text","message_id","draft_id"?}` |
| `account_check` | Worker | `{}` |
| `update_profile` | Worker | `{"first_name"?,"last_name"?,"bio"?,"username"?,"photo_url"?}` |
| `login_start` | Worker | `{"phone"}` |
| `login_code` | Worker | `{"code"}` |
| `login_password` | Worker | `{"password"}` |
| `relay_to_staff` | API | `{"route_id","message_id","dialog_id","staff_chat_id"}` |
| `bot_reply` | API | `{"dialog_id","message_id"}` |
| `reply_to_origin` | API | `{"dialog_id","text","staff_chat_id","staff_message_id","origin_message_id"}` |

领取规则：Worker 只领「账号租约属于自己」的 `account_id` 任务；API 只领带 `bot_id` 的任务
（`core.tasks.claim_tasks(kind="worker"|"bot")`）。

## 11. 批量账号操作

只做账号运维层面的批量动作：**检测、同步会话、分配/取消分配、改分组、改代理、停用/启用、清租约**。
批量私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉进群 / 批量改资料 / 吵群 / 拟人发言这类对外发送动作
**系统不提供**，也不写任务类型（规划「不做这些」是硬约束），以后也不加。

```
POST /api/accounts/bulk/check          {选择器}                      → BulkResultResponse
POST /api/accounts/bulk/sync-dialogs   {选择器}                      → BulkResultResponse
POST /api/accounts/bulk/assign         {选择器,"user_id","mode"}     → BulkResultResponse   # 仅 admin
POST /api/accounts/bulk/group          {选择器,"group_id":uuid|null} → BulkResultResponse
POST /api/accounts/bulk/proxy          {选择器,"proxy_id":uuid|null} → BulkResultResponse
POST /api/accounts/bulk/status         {选择器,"enabled":bool}       → BulkResultResponse
POST /api/accounts/bulk/disable        {选择器}                      → BulkResultResponse   # = status{enabled:false}
POST /api/accounts/bulk/enable         {选择器}                      → BulkResultResponse   # = status{enabled:true}
POST /api/accounts/bulk/release-lease  {选择器}                      → BulkResultResponse   # 只清租约，不改状态
```

选择器（公共请求体）：

| 字段 | 说明 |
|---|---|
| `account_ids` | 明确点名的账号（`scope=selected` 时用它）。operator 传了未分配的号 → 403；号不存在 → 404 |
| `scope` | `selected`（默认）\| `all` \| `group:<分组ID>`。operator 的 `all` 自动收敛为「分配给他的号」 |
| `limit` | 本次最多处理多少个号，1..500，默认 200。超出时只处理前 N 个（建档时间正序）并回 `truncated=true` |

各动作额外字段：
`assign` → `user_id`（必填）+ `mode`：`assign`（默认）/ `unassign`；
`group` → `group_id`，传 `null` = **移出分组**；
`proxy` → `proxy_id`，传 `null` = **改为直连**；
`status` → `enabled`：`false` 停用并清租约，`true` 启用。

响应（所有批量端点统一）：

```json
{
  "ok": true,
  "action": "disable",
  "message": "已停用 2 个账号，清掉 2 个租约",
  "requested": 2, "succeeded": 2, "failed": 0, "skipped": 0, "truncated": false,
  "task_ids": [],
  "items": [
    {"account_id": "…", "account_label": "861****2551", "ok": true,
     "message": "已停用并清除租约", "task_id": null,
     "reachable": null, "status": null, "status_label": null}
  ]
}
```

- `action` 是动作短名：`check` / `sync-dialogs` / `assign` / `unassign` / `group` / `proxy` /
  `status` / `disable` / `enable` / `release-lease`；
- `account_label` 是脱敏手机号；`task_ids` 是入队的任务 id（`check` / `sync-dialogs` 会有）；
- `check` 的 item 额外带 `reachable` / `status` / `status_label`，与单号检测同口径；
- `requested` = 本次命中的账号数（`items` 的长度），`succeeded` / `failed` 按 item 汇总。

行为要点：

- **停用**：`status=disabled` + `current_task=idle` + 清租约，Worker 会断开这些号，其它号不受影响；
- **启用**：有会话的号回 `healthy`，没有会话的回 `pending`（等重新登录）；
- **改分组 / 改代理**：只改 `group_id` / `proxy_id`，不动状态与租约；代理 / 分组不存在 → 400；
- **分配**：只有 admin 能做（员工归属是管理动作，operator → 403）；重复分配自动跳过；
- 每次批量操作写一条审计（`account.bulk_check`、`account.bulk_sync_dialogs`、`account.bulk_assign`、
  `account.bulk_unassign`、`account.bulk_group`、`account.bulk_proxy`、`account.bulk_disable`、
  `account.bulk_enable`、`account.bulk_release_lease`），`target_type=account_batch`；
  任务批量重试写 `task.bulk_retry`，转发测试消息写 `relay.test`。

错误：越权 403（`账号未分配给你：<id>`）、不存在 404（`账号不存在：<id>`）、
空选择 400、`scope` 写法错 400（`scope 要写成 group:<分组ID>`）、`mode` 非法 400。

## 12. CSV 导出

```
GET /api/export/accounts.csv?group_id=&status=&current_task=&phone=&keyword=&sort=&order=
GET /api/export/dialogs.csv?channel=&kind=&account_id=&bot_id=&q=&keyword=&only_unread=&sort=&order=
GET /api/export/messages.csv?q=&channel=&kind=&account_id=&dialog_id=&direction=&status=&sort=&order=
GET /api/export/tasks.csv?status=&type=&account_id=&bot_id=&only_failed=&sort=&order=
GET /api/export/audit.csv?action=&user_id=&account_id=&bot_id=&sort=&order=
```

- 查询参数与对应列表接口完全一致（含 `sort`/`order`/`q`），但**不受 `page`/`page_size` 影响**：
  导出的就是当前筛选条件下的全部数据；
- 响应头：
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="accounts_20260928T131107Z.csv"`（UTC 时间戳）
  - `X-Export-Total`（真实条数）、`X-Export-Truncated`（`true` = 超过 5 万行被截断）
  - 已带 `Access-Control-Expose-Headers`，浏览器可读文件名与这两个头
- 正文流式输出，首字节是 **UTF-8 BOM**（Excel 打开中文不乱码），行结束符 CRLF；
- 文本以 `= + - @` 开头时前面加单引号（防止 Excel 把消息正文当公式执行）；
- 每次导出写一条 `export.download` 审计（谁、什么时候、哪张表、什么筛选、多少行）；
- 权限：operator 只能导出分配到的账号及其会话 / 消息 / 任务 / 与本人相关的审计；
  带越权的 `dialog_id` / `account_id` → 403，不存在 → 404。

表头（中文，第一行）：

| 文件 | 列 |
|---|---|
| `accounts.csv` | 手机号(脱敏)、用户名、用户ID、显示名、号龄(天)、群数量、分组、代理、状态、状态说明、当前任务、最后心跳、最后检测、最后错误、备注、Worker、租约到期、建档时间、账号ID |
| `dialogs.csv` | 会话ID、通道、类型、账号、标题、用户名、对方、成员数、未读、最近消息时间、最近消息预览、置顶、建档时间 |
| `messages.csv` | 时间、会话标题、账号、通道、方向、状态、发送人、正文、有媒体、媒体类型、TG消息ID、会话ID、消息ID |
| `tasks.csv` | 建档时间、类型、状态、账号、Bot、优先级、尝试次数、最大尝试、Worker、错误、下次执行、开始时间、完成时间、创建人、任务ID |
| `audit.csv` | 时间、动作、动作名、操作人、账号、目标类型、目标ID、详情、IP |

时间列一律 ISO8601 带时区（`2026-09-28T13:11:32.898100+00:00`）。

## 13. 账号详情聚合

```
GET /api/accounts/{id}/overview → AccountOverviewOut
```

```json
{
  "account": { "…AccountOut…" },
  "group": {"id":"…","name":"验证分组","description":"","account_count":3,"created_at":"…"},
  "proxy": {"id":"…","name":"代理A","scheme":"socks5","host":"1.2.3.4","port":1080,
            "endpoint":"socks5://1.2.3.4:1080","has_auth":true,"enabled":true,"remark":"","account_count":2,"created_at":"…"},
  "lease": {"worker_id":"w1","lease_until":"…","last_heartbeat":"…","active":true},
  "dialog_stats": {"total":12,"group":9,"private":3,"unread":2},
  "task_stats": {"pending":1,"pending_confirmation":0,"running":0,"completed":8,"failed":1,"cancelled":0},
  "recent_dialogs": ["…DialogOut，最近 20 个会话…"],
  "recent_messages": ["…MessageOut，最近 50 条，按时间倒序…"],
  "recent_tasks": ["…TaskOut，最近 20 条…"],
  "recent_audit": ["…AuditOut，最近 20 条…"],
  "generated_at": "…"
}
```

- `group` / `proxy` 没有绑定时是 `null`；`lease` 没有租约时是 `null`，`active=false` 表示租约已过期
  （页面不要把它显示成「在线」）；
- 抽屉只给「最近 N 条」，翻更早的历史用各自的列表接口（避免一次拉全库）；
- admin 可看任意号；operator 看未分配的号 → 403，不存在 → 404。

## 14. 趋势

```
GET /api/metrics/trends?window=24h|7d|30d
```

`range=` 是 `window=` 的别名（两者都接受，同时给以 `window` 为准），默认 `24h`。

```json
{
  "window": "24h", "range": "24h", "granularity": "hour",
  "from": "2026-09-27T13:11:08+00:00", "to": "2026-09-28T13:11:08+00:00",
  "latest_sample_at": "2026-09-28T13:14:41+00:00",
  "generated_at": "2026-09-28T13:15:02+00:00",
  "series": [
    {"key":"online_accounts","label":"在线账号","unit":"count","points":[{"t":"2026-09-28T13:00:00+00:00","v":3}]},
    {"key":"abnormal_accounts","label":"异常账号","unit":"count","points":[{"t":"…","v":1}]},
    {"key":"tasks_succeeded","label":"任务成功","unit":"count","points":[{"t":"…","v":0}]},
    {"key":"tasks_failed","label":"任务失败","unit":"count","points":[{"t":"…","v":2}]}
  ],
  "points": [
    {"bucket":"2026-09-28T13:00:00+00:00","online_accounts":3,"abnormal_accounts":1,
     "tasks_succeeded":0,"tasks_failed":2}
  ]
}
```

- `24h` → 逐小时（最多 24 个点）；`7d` / `30d` → 逐天（在线 / 异常取当天采样**均值**，任务成败取当天**合计**）；
- `series` 与 `points` 是同一份数据的两种形状：前者直接画折线，后者给表格；
- **没有采样的时间桶不会补 0**（补 0 会画出误导性的深谷）；`latest_sample_at=null` 表示采样还没写过数据，
  此时 `series[].points` 是空数组，前端显示空状态；
- 数据来源 `metrics_samples`：每小时一行，采样协程每 60 秒写一次（多个 API 副本用 Redis 键
  `tgcc:metrics:sampler-leader` 选出一个采样者，避免任务计数被重复累加；leader 挂掉后最多 90 秒由其它副本接手）；
- 口径：`online_accounts` = 状态 `healthy` 且租约未过期；`abnormal_accounts` = 状态不在
  {`healthy`,`pending`,`disabled`}；与工作台数字同源；
- 口径是**全局**的（只有计数，不含手机号 / 用户名 / 消息内容）。工作台对 operator 的数字会按分配范围收敛，
  趋势为了画出连续曲线使用全局计数；
- 非法 `window` → 400（`window 只能是 24h / 7d / 30d`）。

## 15. 通知流

```
GET  /api/notifications?unread_only=&kind=&level=&page=&page_size=&sort=&order=  → NotificationListResponse
POST /api/notifications/{id}/read                                              → {ok,message,notification}
POST /api/notifications/read-all                                               → {ok,message,marked}
```

```json
{
  "items": [
    {"id":"…","kind":"task_failed","kind_label":"任务失败","level":"error",
     "title":"任务失败：账号检测",
     "body":"账号 861****2551 · 未配置 TELEGRAM_API_ID/TELEGRAM_API_HASH…（第 5/5 次尝试）",
     "link":"/tasks?status=failed",
     "account_id":"…","account_label":"861****2551","bot_id":null,"task_id":"…","worker_id":null,
     "detail":{"type":"account_check","error":"…","attempts":5},
     "read":false,"read_at":null,"created_at":"2026-09-28T13:11:32+00:00"}
  ],
  "total": 3, "unread": 2, "page": 1, "page_size": 20,
  "counts_by_kind": {"task_failed":1,"worker_lost":0,"account_abnormal":1,"backup_failed":0}
}
```

四类来源：

| kind | 判定 | level | 去重键（同一件事只通知一次） | link |
|---|---|---|---|---|
| `task_failed` | `tasks.status=failed`（近 7 天，最多 200 条） | `error` | `task_failed:<task_id>` | `/tasks?status=failed` |
| `worker_lost` | 仍持有有效租约，但 Redis 心跳超过 60 秒没更新 | `warning` | `worker_lost:<worker_id>:<UTC 小时>` | `/` |
| `account_abnormal` | `tg_accounts.status ∈ {needs_code, frozen, invalid, dead}` | `warning` | `account_abnormal:<account_id>:<status>` | `/accounts/<account_id>` |
| `backup_failed` | Redis 键 `tgcc:backup:last-result` 报 `ok=false` | `error` | `backup_failed:<kind>:<日期>` | `/` |

- 通知是**聚合产物**（事实在 tasks / leases / tg_accounts）：列表接口在返回前会尝试聚合一次，
  用 Redis 键 `tgcc:notifications:last-sync` 做 20 秒节流；后台协程也会定时聚合。
  刚失败的任务下一次刷新就能看到；聚合失败只记日志，绝不让铃铛打不开；
- `unread` 与 `counts_by_kind` 只按可见范围统计，**不受** `kind`/`level`/`unread_only` 影响（角标不会因为筛选变小）；
- `kind` 非法 → 400（`kind 只能是 task_failed / worker_lost / account_abnormal / backup_failed`）；
  `level` 非法 → 400（`level 只能是 info / warning / error / success`）；
- `POST /{id}/read` 幂等（已读再点回 `这条通知本来就已经读过了`），不存在 → 404；
- `POST /read-all` 只标记当前用户可见的未读通知，回 `{"ok":true,"message":"…","marked":3}`；
- 权限：admin 看全部；operator 看「与自己分配账号相关 + 全局（`account_id` 为 null 的 Worker / 备份类）」，
  读别人号上的通知 → 403。

**备份结果上报约定**（`deploy/backup.sh` 侧接入，API 只读）：

```
SET tgcc:backup:last-result '{"ok":false,"kind":"daily","ts":"2026-09-28T03:10:00+00:00","message":"pg_dump 退出码 1"}'
```

键不存在**不告警**（没接入上报 ≠ 备份失败，避免误报）；键过期后该类通知不再新增（已有通知保留，直到被读）。

## 16. 列表排序与搜索

- 所有列表接口都接受 `sort=<字段>&order=asc|desc`：accounts / dialogs / messages / tasks / audit / notifications；
- 非法字段 → 400 `不支持的排序字段：xxx；可用字段：…`；非法方向 → 400 `order 只能是 asc 或 desc`；
- 默认排序：accounts `created_at desc`、dialogs `last_message_at desc`（null 排最后）、messages `created_at desc`、
  tasks `created_at desc`、audit `created_at desc`、notifications `created_at desc`；
  并列时用 id 兜底，翻页稳定不重不漏。

| 接口 | 可用 sort 字段 |
|---|---|
| `/api/accounts` | `created_at`、`updated_at`、`phone_masked`、`username`、`display_name`、`status`、`current_task`、`age_days`、`group_count`、`last_heartbeat`、`last_checked_at` |
| `/api/dialogs` | `last_message_at`、`created_at`、`updated_at`、`title`、`unread_count`、`member_count` |
| `/api/messages`（含导出） | `created_at`、`updated_at`、`sender_name`、`status`、`direction`、`tg_message_id` |
| `/api/tasks` | `created_at`、`updated_at`、`status`、`type`、`priority`、`attempts`、`next_run_at`、`started_at`、`completed_at` |
| `/api/audit` | `created_at`、`updated_at`、`action`、`target_type`（另外支持 `from`/`to` 时间范围，见第 7 节） |
| `/api/notifications` | `created_at`、`updated_at`、`kind`、`level`、`is_read` |

跨会话消息搜索：

```
GET /api/messages?q=&channel=&kind=&account_id=&dialog_id=&direction=&status=&page=&page_size=&sort=&order=
    → {items:[MessageOut], total, page, page_size}
```

- `q` 只在**正文**里搜；`/api/dialogs` 的 `q`/`keyword` 跨标题、对方、用户名、最近预览与正文；
- 会话内的聊天记录用 `/api/dialogs/{id}/messages?limit=&before=&q=`（固定时间正序 + `before` 往前翻）；
- operator 只搜得到自己分配账号下的会话与消息；按未分配的 `dialog_id` 搜 → 403，不存在 → 404。

## 17. 新增数据表与 Redis 键（本次补接口时新增）

| 表 | 用途 | 关键列 |
|---|---|---|
| `metrics_samples` | 趋势采样，一小时一行 | `bucket`(PK)、`total_accounts`、`online_accounts`、`abnormal_accounts`、`tasks_succeeded`、`tasks_failed`、`sampled_at` |
| `notifications` | 站内通知（聚合产物） | `kind`、`level`、`title`、`body`、`link`、`account_id`、`bot_id`、`task_id`、`worker_id`、`detail`、`dedupe_key`(唯一)、`is_read`、`read_at`、`read_by` |

迁移：`backend/alembic/versions/c3f1a9d24b70_console_completeness.py`，**只建新表**（additive），
不动任何已有列语义；`alembic downgrade -1` 只删这两张表。

| Redis 键 | 写入方 | 用途 |
|---|---|---|
| `tgcc:metrics:sampler-leader` | API 采样协程 | 多副本选一个采样者（TTL 90s，每 60s 续期；leader 挂掉最多 90s 接手） |
| `tgcc:notifications:last-sync` | 通知聚合 | 20 秒节流，避免页面轮询每次都跑聚合 |
| `tgcc:backup:last-result` | `deploy/backup.sh`（待接入） | 备份结果上报，`ok=false` 生成 `backup_failed` 通知 |

