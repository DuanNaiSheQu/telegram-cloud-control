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
GET    /api/accounts?page=1&page_size=20&group_id=&status=&current_task=&phone=&keyword=
       → {items:[AccountOut], total, page, page_size, summary:AccountSummary}
GET    /api/accounts/summary → AccountSummary
POST   /api/accounts              AccountCreate          → AccountOut      # 建档（不自动登录）
GET    /api/accounts/{id}                                → AccountOut
PATCH  /api/accounts/{id}         AccountUpdate          → AccountOut
POST   /api/accounts/{id}/disable                        → {ok,message}    # status=disabled，清租约
POST   /api/accounts/{id}/enable                         → {ok,message}    # status=pending/healthy
DELETE /api/accounts/{id}                                → {ok,message}
POST   /api/accounts/{id}/release-lease                  → {ok,message}    # 单号异常时只清它的租约
POST   /api/accounts/{id}/sync-dialogs                   → {ok,message,task_id}
POST   /api/accounts/{id}/check                          → CheckResultOut
POST   /api/accounts/check        {"account_ids":[...]|null,"scope":"selected|all|group:"} → [CheckResultOut]
POST   /api/accounts/{id}/profile {"first_name","last_name","bio","username","photo_url"}   → {ok,message,task_id}
```

`AccountSummary`：`{total, healthy, abnormal, new_this_week, online, leased}`
（页面四块汇总：总数、正常、异常、本周新增）。

### 单号登录（验证码只走这个号自己）

```
POST /api/accounts/login/start    {"phone","group_id","proxy_id","account_id"?} → LoginStepResponse
POST /api/accounts/login/code     {"account_id","code"}                          → LoginStepResponse
POST /api/accounts/login/password {"account_id","password"}                      → LoginStepResponse
```

`LoginStepResponse`：`{account_id, step: "code_required"|"password_required"|"done", message, task_id}`
步骤由 Worker 执行 Telethon 登录：`login_start` 发验证码，`login_code` 提交，若开了两步验证返回
`password_required`，否则 `done` 并把会话加密写回 `tg_accounts.session_enc`。

### 账号检测

`CheckResultOut`：`{account_id, phone_masked, reachable, status, status_label, message, task_id}`
检测含义：连得上（`healthy`）、要验证码（`needs_code`）、会话失效（`invalid`）。
接口会写一条 `account_check` 任务并立刻续一次租约，Worker 读到后读一次状态写回该行。

### 账号表列（前端照此渲染）

手机号、用户名、用户 ID、号龄、群数量、分组、代理、状态、当前任务、最后心跳。
筛选：分组、状态、任务状态、手机号。

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
GET  /api/dialogs?channel=user_account|bot&kind=private|group&account_id=&bot_id=&keyword=&only_unread=&page=&page_size=
     → {items:[DialogOut], total, page, page_size}
GET  /api/dialogs/{id}                    → DialogOut
GET  /api/dialogs/{id}/messages?limit=50&before=<ISO>  → {items:[MessageOut], total, dialog, has_more}
POST /api/dialogs/{id}/read               → {ok,message}      # 未读清零
POST /api/dialogs/{id}/sync  {"limit":50} → {ok,message,task_id}   # 拉该会话历史消息
GET  /api/dialogs/{id}/drafts             → [DraftOut]
POST /api/dialogs/{id}/draft {"instruction"}  → DraftOut      # AI 草稿，停在输入框
DELETE /api/drafts/{id}                   → {ok,message}      # 丢弃草稿
POST /api/messages/send   {"dialog_id","text","draft_id"?}    → SendMessageResponse
```

`SendMessageResponse`：`{ok, message, task_id, status: "pending"|"sent", detail}`

发送规则（两条通道分开）：

| 会话通道 | 行为 |
|---|---|
| `user_account` | 预写一条 `messages`（direction=outgoing, status=pending）并写 `send_message` 任务，等持有租约的 Worker 发出后回填 `tg_message_id`、status=sent。账号不在 `healthy` → 409 |
| `bot` | API 直接用 Bot API 发出，立即写 `messages`（status=sent），回 `task_id=null` |

带 `draft_id` 时发送成功后把 `reply_drafts.status=sent`、`sent_by`、`sent_at` 写全（审计里记是谁点的）。

## 6. 任务中心

```
GET  /api/tasks?status=&type=&account_id=&bot_id=&only_failed=&page=&page_size=
     → {items:[TaskOut], total, page, page_size, counts:{pending,running,failed,completed,cancelled,pending_confirmation}}
GET  /api/tasks/{id}            → TaskOut
POST /api/tasks/{id}/retry      → {ok, task, message}     # failed/pending_confirmation → pending，attempts 归零
POST /api/tasks/{id}/cancel     → {ok, task, message}
```

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
PATCH  /api/relays/{id}          RelayRouteUpdate → RelayRouteOut
DELETE /api/relays/{id}                                → {ok,message}
GET    /api/relays/links?route_id=&page=&page_size=    → {items:[RelayLinkOut], total}
```

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
