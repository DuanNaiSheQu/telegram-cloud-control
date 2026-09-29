<div align="center">

<img src="docs/assets/logo.svg" width="120" alt="Telegram 云控">

<h1>Telegram 云控</h1>

<p><b>面向自有账号与官方 Bot 的 Telegram 运维控制台</b><br>
在线状态 · 会话收件箱 · 任务队列 · Bot 转发 · 全链路审计</p>

<!-- 徽章说明：仓库为 private 时 shields.io 的 github/* 徽章会显示 not found，
     改成 public 后自动恢复；其余静态徽章不受影响。 -->
<p>
  <a href="#许可证"><img src="https://img.shields.io/badge/license-待定-yellow.svg" alt="License"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/releases"><img src="https://img.shields.io/github/v/release/cafinxnull/telegram-cloud-control?label=release&color=2AABEE" alt="Release"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/releases"><img src="https://img.shields.io/badge/version-0.3.26-2AABEE.svg" alt="Version"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/releases"><img src="https://img.shields.io/badge/changelog-%E6%9B%B4%E6%96%B0%E8%AE%B0%E5%BD%95-blue.svg" alt="Changelog"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/stargazers"><img src="https://img.shields.io/github/stars/cafinxnull/telegram-cloud-control?label=stars&color=f5a623" alt="Stars"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/issues"><img src="https://img.shields.io/github/issues/cafinxnull/telegram-cloud-control?label=issues" alt="Issues"></a>
  <a href="https://github.com/cafinxnull/telegram-cloud-control/commits/main"><img src="https://img.shields.io/github/last-commit/cafinxnull/telegram-cloud-control?label=last%20commit" alt="Last commit"></a>
</p>

<p>
  <img src="https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/node-%E2%89%A520-339933?logo=nodedotjs&logoColor=white" alt="Node">
  <img src="https://img.shields.io/badge/postgresql-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/redis-7-DC382D?logo=redis&logoColor=white" alt="Redis">
  <img src="https://img.shields.io/badge/docker%20compose-v2-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
  <img src="https://img.shields.io/badge/telegram-MTProto%20%2B%20Bot%20API-26A5E4?logo=telegram&logoColor=white" alt="Telegram">
  <img src="https://img.shields.io/badge/status-可用-3FB950" alt="Status">
</p>

<p>
  <img src="https://img.shields.io/badge/%E8%B5%9E%E5%8A%A9%E5%95%86-CAFINX%20%C2%B7%20CAFINXSIM-2AABEE" alt="赞助商">
</p>

<p>
  <a href="#功能特性">功能</a> ·
  <a href="#界面预览">截图</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#部署与运维">部署</a> ·
  <a href="#开发与测试">开发</a> ·
  <a href="#赞助商">赞助商</a>
</p>

---

<div align="center">

### 赞助商

<table>
  <tr>
    <td align="center" width="50%">
      <a href="https://cafinx.com">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sponsor/cafinx-white.png">
          <img src="docs/assets/sponsor/cafinx.png" width="76" alt="CAFINX 虚拟卡">
        </picture>
      </a><br>
      <b><a href="https://cafinx.com">CAFINX 虚拟卡</a></b><br>
      <sub>跨境收付虚拟卡 · cafinx.com</sub>
    </td>
    <td align="center" width="50%">
      <a href="https://cafinxsim.com">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="docs/assets/sponsor/cafinxsim-white.png">
          <img src="docs/assets/sponsor/cafinxsim.png" width="196" alt="CAFINXSIM">
        </picture>
      </a><br>
      <b><a href="https://cafinxsim.com">CAFINXSIM</a></b><br>
      <sub>全球 eSIM 流量卡 · cafinxsim.com</sub>
    </td>
  </tr>
</table>

</div>

---

### 核心能力

<table>
  <tr>
    <td width="33%" valign="top">
      <h4>账号矩阵</h4>
      <sub>四种格式批量导入（手机号 / Session 串 / .session / tdata）、深度验活与健康分、<br>
      每号独立设备指纹、节流防封与养号阶梯</sub><br>
    </td>
    <td width="33%" valign="top">
      <h4>群情报采集</h4>
      <sub>入群即采、不发言不回应；粘贴群链接自动采群员，<br>
      进度逐条可见，采完一键打包（群总表 + 成员 + 事件）</sub><br>
    </td>
    <td width="33%" valign="top">
      <h4>批量运营</h4>
      <sub>私信 / 群发 / 素材群发 / 加群 / 退群 / 强拉 / 改资料 / 吵群 / 拟人发言，<br>
      按批次跟踪进度、可取消、可打包导出</sub><br>
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>会话收件箱</h4>
      <sub>群聊、私信、Bot 私信统一入口，WebSocket 实时推送，AI 草稿人工确认后发送</sub><br>
    </td>
    <td valign="top">
      <h4>任务队列与租约</h4>
      <sub>一个号同时只被一个 Worker 使用；被节流拦下的任务顺延而不是硬发</sub><br>
    </td>
    <td valign="top">
      <h4>审计与权限</h4>
      <sub>谁在什么时间对哪个号做了什么全部留痕；操作员只能看到分配给自己的账号</sub><br>
    </td>
  </tr>
</table>

</div>

---

**一套自己用的 Telegram 运维后台。** 管理你自己的用户号和官方 Bot，处理这些号已经在里面的群聊与私信，
用 Bot 把新消息转发到员工群、员工回复后按同一规则送回原会话；所有动作留审计。

- 🖥️ **值班一眼看全**：哪些号在线、卡在哪条任务、某个群/私信的最新消息，都在一个页面里。
- 🔌 **API 与长连接分离**：重启页面服务不会把号全部踢下线。
- ✋ **发送要员工确认**：用户号方向先写 `pending` 消息 + 任务，Worker 发出后才回填 Telegram 消息 ID；Bot 方向可以直接回。
- 🧾 **全链路可追溯**：谁在什么时间对哪个号做了什么，都落 `audit_logs`。
- 🐳 **一条命令起整套**：`docker compose` 起 `postgres / redis / api / worker / frontend`，监控栈走 `monitoring` profile。

## 目录

- [赞助商](#赞助商)
- [最新更新](#最新更新)
- [功能特性](#功能特性)
- [界面预览](#界面预览)
- [技术栈](#技术栈)
- [架构与关键不变量](#架构与关键不变量)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [常用命令](#常用命令)
- [开发与测试](#开发与测试)
- [部署与运维](#部署与运维)
- [范围与合规边界](#范围与合规边界)
- [路线图](#路线图)
- [贡献](#贡献)
- [许可证](#许可证)
- [鸣谢](#鸣谢)

## 功能特性

### 账号池运维

| 能力 | 说明 |
|---|---|
| 账号总览 | 手机号（脱敏）、用户名、用户 ID、号龄、群数量、分组、代理、状态、当前任务、最后心跳，一屏列全 |
| 七态状态机 | `待登录 / 正常 / 要验证码 / 冻结 / 失效 / 永久双向 / 停用`，状态由 Worker 按实况写回，页面标色区分 |
| 单号检测 | 一键续租 + 读一次真实状态（连得上 / 要验证码 / 会话失效），结果写回该行 |
| 验证码登录 | 只用这个号自己的验证码：发码 → 提交 →（可选）两步密码，会话串加密落库；登录成功后自动补一条「同步会话」 |
| 分组与代理 | 自定义标签把号分给同事；每个号绑定固定出站地址（代理口令加密保存，页面只显示「有没有」） |
| 批量操作 | 批量检测 / 同步会话 / 分配 / 改分组 / 改代理 / 停用启用 / 清租约 —— 都是「对已有的号做一次已有操作」 |
| 导出与详情 | 按当前筛选导出 CSV；点行看账号详情抽屉（租约、会话、最近消息、任务、审计一次拉齐） |

### 会话收件箱

| 能力 | 说明 |
|---|---|
| 两条连接一张收件箱 | 用户号的群聊/私信（Worker 长连接）与官方 Bot 的私信/群消息（Webhook）统一落进 `dialogs` / `messages` |
| 实时推送 | WebSocket 只推当前打开的会话；断线自动重连并按会话补订阅 |
| IM 级阅读体验 | 消息按时间正序、日期分隔、失败态重发、无限上翻、未读分隔线、会话内搜索 |
| AI 草稿 | 按资料库生成一段回复，**停在输入框**，员工点发送才出去（未配置 AI 时给引导文案，不报错弹窗） |
| 发送二分支 | 用户号 → `pending` + 任务（非正常状态会明确拒绝并说明原因）；Bot → 直接调 Bot API 发回原聊天 |

### 任务中心

- 队列就是 `tasks` 表：`FOR UPDATE SKIP LOCKED` 领取，失败按指数退避重试，超过上限记 `failed`，页面可手工重试或取消。
- **批量重试有类型白名单**：同步会话、拉历史、账号检测、改自己资料、转发到员工群可以批量重试；
  单条发送、登录类、Bot 自动回复、回复送回**不允许批量重试**（等于批量发出/批量登录），只能在详情里单条重试。
- 状态汇总含 `overdue`（到期未执行）与 `stuck`（执行中卡住），失败原因完整展示，详情抽屉带时间线与 payload/result。

### Bot 与转发

| 能力 | 说明 |
|---|---|
| 多 Bot 管理 | Token 加密保存、只回掩码；新增/换 Token 先调 `getMe` 校验；一键注册/注销 Webhook；无效 Token 在列表标黄 |
| 转发规则 | 「用哪个 Bot、转发到哪个员工群、只转发哪些来源（账号/会话）」；支持停用不删除 |
| 转发记录 | 原消息正文、发送人、所属会话、员工群那条消息 ID；可跳到原会话 |
| 员工群回复送回 | 员工在员工群里回复那条转发，系统按 `relay_links` 找到原会话，按同一规则送回（Bot 会话走 Bot API，用户号走任务队列） |
| 去重与幂等 | Webhook 按 `update_id` 去重（Redis），消息按 `(会话, Telegram 消息 ID)` 唯一；Redis 丢了只影响推送与去重 |
| 自动回复 | 官方 Bot 按自己的资料（persona）自动回复，身份是 Bot；草稿与调用记录与资料分开放 |

### 团队、审计与通知

- 角色：`admin`（看全部、管员工/Bot）与 `operator`（只看分配给自己的号）；越权一律 403 并给中文原因。
- 操作记录：时间、谁、动作（中文标签）、账号、Bot、目标、详情 JSON，可按动作/员工/账号/时间范围筛选并导出。
- 通知流：失败任务、Worker 心跳丢失、账号异常、**备份失败**（备份脚本推 Redis，API 聚合成通知），可单条/全部已读。

### 可观测与运维

- 探测：`/health`（进程活着）、`/ready`（数据库 + Redis 都通）、`/metrics`（Prometheus）。
- Worker 自带 `:9101/metrics`：在线号数、租约数、重连次数、任务成败与耗时、租约续期失败、心跳年龄、`tgcc_worker_info{worker_id}`。
- **四条告警**（外加监控自身的三条兜底）见 `deploy/alert.rules.yml`；处置步骤见运维手册。
- 日志是 JSON 一行一条，业务日志带 `account_id` / `worker_id` / `task_id`。
- 备份：每日 `pg_dump` + 每周 `pg_basebackup`，Postgres 全程 `archive_mode=on`，支持**按时间点恢复**。

### 安全

- 会话串、Bot Token、代理口令用 Fernet 加密入库，密钥只在环境变量里；响应只回脱敏手机号与 `token_masked`。
- 控制台 JWT（HS256）+ bcrypt 口令；Webhook 路径带 `WEBHOOK_SECRET` 且常量时间比较。
- 登录只用这个号自己的验证码或自己创建的 Bot Token，不导入别人的会话文件。
- Postgres / Redis 默认只绑定宿主 `127.0.0.1`，对外只暴露前端 80 端口（前面应再放一层 HTTPS 反代）。

## 最新更新

> 版本号唯一真源是仓库根的 [`VERSION`](VERSION)：后端 `/health` 返回它，前端构建时注入它（侧栏左下角可见）。
> 完整历史与版本号见本页顶部的版本徽章。

### v0.3.0 — 账号矩阵成熟化（2026-09-29）

- **多格式账号导入**：手机号清单 / StringSession 串 / `.session` 文件 / tdata 目录 zip，
  先预览再落库，去重按确定性哈希（修掉了「重复号码识别不出来」的老问题），每号独立设备指纹。
- **深度验活**：读权限 + 授权会话数 + 可选写探测，复算 0-100 健康分；批量节流旋钮（额度 / 间隔 / 解熔断）。
- **防封四道闸门**：FloodWait 熔断、活跃时段、动作最小间隔、每日配额；养号阶梯 20 → 200 条/天随号龄放量。
- **群情报（入群即采）**：入群/退群事件静默入库，群档案与成员名单按需只读采集；
  支持**粘贴群链接自动采群员**（`t.me/+hash`、`@username` 都行，可选自动加入、采完退出），
  进度逐条可见（解析 → 加入 → 采集中 N/M → 完成），采完可**一键打包**（zip：群总表 + 每群成员 + 事件 + 清单）。
- **官方机制养号**：身份取自官方真实发布版本表；读服务端下发的 `help.GetAppConfig` 限制参数驱动节流
  （只收紧不放松）；`warmup_activity` 按官方客户端节奏上线/翻会话/下线，不发消息、不加群。
- **修复**：`localStorage` 残缺结构导致的整页白屏；失败原因红字撑破列宽遮挡其它列。

## 界面预览

> 深色 / 浅色双主题；下图均为 1440×900 真实截图（2x 缩放），完整截图在 [`frontend/screenshots/`](frontend/screenshots/)。
> 截图可随时重生成：`cd frontend && npm run screenshots`（深色）或 `npm run screenshots -- --theme light`（浅色）。

<table>
  <tr>
    <td width="50%"><b>工作台</b>：在线/异常/失败任务、在线趋势、Worker 心跳、队列积压、通知流<br>
      <img src="frontend/screenshots/uicore-dashboard-dark-1440.png" alt="工作台"></td>
    <td width="50%"><b>会话收件箱</b>：会话列表 + 消息流 + AI 草稿 + 实时推送<br>
      <img src="frontend/screenshots/uiinbox-dialogs-chat-dark.png" alt="会话收件箱"></td>
  </tr>
  <tr>
    <td><b>账号管理</b>：全列 + 全量筛选 + 批量操作 + 详情抽屉<br>
      <img src="frontend/screenshots/uicore-accounts-dark-1440.png" alt="账号管理"></td>
    <td><b>任务中心</b>：状态汇总、失败原因、批量重试、详情时间线<br>
      <img src="frontend/screenshots/uiinbox-tasks-dark.png" alt="任务中心"></td>
  </tr>
  <tr>
    <td><b>Bot 转发</b>：规则 + 已转发记录 + 测试消息<br>
      <img src="frontend/screenshots/uiops-relay-dark.png" alt="Bot 转发"></td>
    <td><b>Bot 管理</b>：Token 掩码、Webhook 状态、自动回复资料<br>
      <img src="frontend/screenshots/uiops-bots-dark.png" alt="Bot 管理"></td>
  </tr>
  <tr>
    <td><b>账号检测</b>：勾选/全部/按分组检测，结果写回<br>
      <img src="frontend/screenshots/uicore-detection-results-dark-1440.png" alt="账号检测"></td>
    <td><b>成员分配</b>：成员、角色、账号选择器与归属反查<br>
      <img src="frontend/screenshots/uiops-assignments-dark.png" alt="成员分配"></td>
  </tr>
  <tr>
    <td><b>营销中心</b>：批量私信 / 群发 / 素材群发 / 加群退群 / 强拉 / 改资料 / 吵群 / 拟人<br>
      <img src="frontend/screenshots/uicore-campaigns-dark-1440.png" alt="营销中心"></td>
    <td><b>群情报</b>：入群即采、按链接采集群员、逐条进度与一键打包<br>
      <img src="frontend/screenshots/uicore-group-intel-dark-1440.png" alt="群情报"></td>
  </tr>
  <tr>
    <td><b>操作记录</b>：谁在什么时间对哪个号做了什么<br>
      <img src="frontend/screenshots/uiinbox-audit-dark.png" alt="操作记录"></td>
    <td><b>浅色主题</b>：同一套 token 换皮<br>
      <img src="frontend/screenshots/02-shell-light-1440.png" alt="浅色主题"></td>
  </tr>
  <tr>
    <td><b>登录页</b>：品牌叙事 + 环境标识 + 记住用户名<br>
      <img src="frontend/screenshots/uiops-login-dark.png" alt="登录页"></td>
    <td><b>账号管理（浅色）</b>：深浅双主题同一套组件<br>
      <img src="frontend/screenshots/uicore-accounts-light-1440.png" alt="账号管理浅色"></td>
  </tr>
</table>

## 技术栈

| 层 | 选型 | 为什么 |
|---|---|---|
| 语言 | Python 3.12 | 用户号长连接用 Telethon，Async 生态成熟 |
| API | FastAPI（无状态，可单独重启） | 显式依赖注入 + OpenAPI，页面和脚本共用一套契约 |
| 用户号长连接 | Telethon（一个 Worker 挂一批号） | MTProto 客户端，能收群/私信事件、能按号发消息 |
| 官方 Bot | aiogram 3（Webhook 收，Bot API 回） | 官方通道，稳定且不需要用户号参与 |
| 主库 | PostgreSQL 16 | 账号、会话、消息、任务、租约、审计都能直接用 SQL 查 |
| 协调 / 推送 | Redis 7 | 心跳缓存、WebSocket 推送、`update_id` 去重；丢了不影响事实数据 |
| 任务队列 | Postgres `tasks` 表 | 不引入额外中间件：`FOR UPDATE SKIP LOCKED` 领取，失败与积压用 SQL 就能看 |
| 前端 | React 18 + TypeScript + Vite + antd 5 | 控制台；设计 token 驱动，深浅主题一套代码 |
| 实时 | FastAPI WebSocket | 只推当前打开的会话，按会话订阅 |
| 观测 | Prometheus + Alertmanager + Pushgateway | 四条告警 + 备份时间上报 |
| 部署 | Docker Compose v2 | 单机可跑，`--scale worker=N` 扩容 |

## 架构与关键不变量

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

**关键不变量**（详见架构文档）：

1. **每个用户号同一时刻只属于一个 Worker**：`leases` 表，30 秒过期、每 10 秒续租；进程收到 SIGTERM 先释放租约再断开。
2. **Bot 收发不进 Worker**：Webhook 无状态，不跟某台 Worker 绑定。
3. **Redis 可以丢**：只影响页面订阅与 Webhook 去重；账号、消息、任务、租约的事实都在 Postgres。
4. **一副本约 100 个在线号**：扩容是增加 `worker` 副本，不是一个号一个容器。
5. **发送走确认**：用户号方向必须由员工在控制台点发送（写 `messages(status=pending)` + 任务），不允许无人值守的批量发出。

### 目录结构

```text
backend/
  app/api/             HTTP + WebSocket + Bot Webhook（FastAPI，86 条业务路由）
  app/worker/          认领租约、维持 Telethon 连接、执行本副本任务 + :9101/metrics
  app/models/          16 张表的 ORM 与枚举（含中文标签）
  app/core/            tasks（队列）/ leases（租约）/ events（推送）/ audit（审计）
  app/services/        inbound（统一入库）/ relay（转发）/ ai（草稿与 Bot 自动回复）
  app/schemas/         Pydantic 契约
  app/config.py        全部配置走环境变量（.env.example 逐项对应）
  alembic/             迁移
  tests/               冒烟与接口验收（真实 Postgres + Redis）
  Dockerfile           与 worker 共用镜像
  entrypoint.sh        统一入口：等库 → 迁移 → 可选建管理员 → exec
frontend/
  src/theme/           设计 token（187 个 CSS 变量）与主题
  src/components/      共享组件库（DataTable / FilterBar / StatCard / Drawer …）
  src/pages/           12 个页面
  src/api/             接口封装（与接口契约对齐）
  Dockerfile           多阶段构建 → nginx 托管 dist
deploy/
  prometheus.yml       抓取配置（api / worker / postgres-exporter / pushgateway）
  alert.rules.yml      四条告警 + 录制规则
  alertmanager.yml     告警分流（示例 webhook，附企业微信/钉钉/Slack 改法）
  backup.sh            日备（pg_dump）+ 周备（pg_basebackup）+ 上报 pushgateway
  backup.cron          crontab 片段（每日 03:10 / 每周日 03:40）
  恢复与演练手册      数据库备份与恢复步骤
docs/                  架构 / 接口契约 / 运维 / 验收 / 赞助
scripts/               create_admin / e2e_check / check_stack_config / stack_local
Makefile               make help 看全部命令
```

## 快速开始

前置条件：Docker 24+ 与 Compose v2（`docker compose version`）、可用磁盘 ≥ 20 GB、
一个能指向本机的域名或公网地址（Telegram Webhook 要用）。

### 1) 准备 `.env`

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

### 2) 起基础服务并迁移

```bash
docker compose up -d postgres redis     # Postgres 16（带 WAL 归档）+ Redis 7
make migrate                            # api 没起也能跑：自动改用一次性容器执行 alembic upgrade head
make admin ADMIN_PASSWORD='你的口令'      # 创建/重置管理员；不传口令则读 .env 的 BOOTSTRAP_ADMIN_PASSWORD
```

### 3) 起应用

```bash
docker compose up -d api worker frontend
docker compose ps                       # 五个服务都应是 healthy / running
curl -fsS http://127.0.0.1:8000/health  # {"status":"ok",...}
curl -fsS http://127.0.0.1:8000/ready   # {"status":"ready","database":true,"redis":true}
```

控制台：<http://localhost:8080>（端口由 `WEB_PORT` 控制；前端 nginx 把 `/api` 与 `/api/ws` 反代到 `api:8000`）。
API 直连端口：<http://localhost:8000>。

> `api` 容器启动时会自己跑一次 `alembic upgrade head`（entrypoint 里），并按需补建管理员，重复执行是幂等的。

### 4) 首次登录与单号登录流程

1. 打开 <http://localhost:8080>，用 `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` 登录。
2. **账号分组**（可选）：先建一个分组，方便把号分给同事。
3. **网络**（可选）：这个号固定的出站代理先建好（用户名/密码加密保存，页面只显示有没有）。
4. **账号管理 → 登录**：填手机号（可带分组和代理）→ 发验证码；输入收到的验证码；
   如果这个号开了两步验证，再输一次密码。全部通过后会话串加密写入 `tg_accounts.session_enc`，状态变 `正常`。
5. **账号检测**：点「检测」立刻续一次租约并读一次状态，结果写回该行（连得上 / 要验证码 / 会话失效）。
6. **同步会话**：在账号管理里点「同步会话」→ 写一条任务 → 持有该号租约的 Worker 拉出已加入的群聊和私信。
7. **会话页**：选一个会话就能看到历史消息；发送时用户号方向走「等待确认发送」——
   写一条 `pending` 的消息和任务，Worker 发出后回填 Telegram 消息 ID、状态变 `已发送`。
8. **Bot 转发**：BotFather 拿 Token → 「Bot 管理」页新增（会调 `getMe` 校验并注册 Webhook）→
   「Bot 转发」页配好「用哪个 Bot、转发到哪个员工群」→ 之后新消息会自动转发，员工在群里回复那条转发即送回原会话。

常见卡点：Webhook 注册失败基本都是 `PUBLIC_BASE_URL` 不是公网可达地址；验证码登录失败先看 Worker 日志里
`login_*` 任务的 `error`。

### 本地开发（不用 Docker）

```bash
# 1) 后端依赖
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..

# 2) 本地 Postgres 与 Redis（本仓库用 .pgdata / .redisdata，端口见 backend/.env：55432 / 56379）
pg_ctl -D .pgdata -l run/pg.log -o "-p 55432 -k /tmp" start
redis-server --port 56379 --dir .redisdata --daemonize yes

# 3) 一键起 API + Worker（含迁移、建管理员，日志落在 run/）
make stack-up            # 等价 ./scripts/stack_local.sh up；status / down / logs 见脚本头部

# 4) 前端 dev server（http://127.0.0.1:5173，/api 自动反代到 127.0.0.1:8000）
cd frontend && npm ci && npm run dev
```

也可以只把数据库交给容器：`docker compose up -d postgres redis`，
再把 `backend/.env` 的 `DATABASE_URL` / `REDIS_URL` 改成 `127.0.0.1:5432` / `127.0.0.1:6379`。

## 配置说明

全部配置走环境变量，完整清单见 [`.env.example`](.env.example)（83 个键，逐项有中文注释）。最常改的：

| 变量 | 默认 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://cloudctl:...@postgres:5432/cloudctl` | 主库连接串 |
| `REDIS_URL` | `redis://redis:6379/0` | 心跳缓存、推送、去重 |
| `SECRET_KEY` | — | JWT 签名 |
| `SESSION_ENCRYPTION_KEY` | — | 会话串 / Bot Token / 代理口令的 Fernet 密钥，**改了就都要重新登录** |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | — | 用户号长连接（为空时 Worker 空转，只认领租约与发心跳） |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Telegram Webhook 注册地址，必须公网可达 |
| `WEBHOOK_SECRET` | — | Webhook 路径里的口令，常量时间比较 |
| `LEASE_TTL_SECONDS` / `LEASE_RENEW_SECONDS` | `30` / `10` | 租约过期与续租间隔 |
| `ACCOUNTS_PER_REPLICA` | `100` | 一个 Worker 副本承载多少在线号 |
| `TASK_MAX_ATTEMPTS` / `TASK_RETRY_BASE_SECONDS` | `5` / `10` | 任务重试上限与退避基数 |
| `AI_ENABLED` / `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` | `false` / 空 | AI 草稿与 Bot 自动回复（OpenAI 兼容接口即可） |
| `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` | `admin` / 空 | 首次启动自动建管理员（users 表为空时） |
| `ENVIRONMENT` | `development` | `production` 时 entrypoint 强制校验密钥非空 |

## 常用命令

`make help` 是唯一权威清单，下面是摘要：

| 命令 | 作用 |
|---|---|
| `make up` / `make down` | 起/停全部服务（`down` 会连监控一起停；数据卷保留） |
| `make ps` / `make logs S=worker` | 看状态 / 跟踪日志 |
| `make migrate` / `make revision M="描述"` | 跑迁移 / 生成迁移脚本 |
| `make admin ADMIN_PASSWORD='xxx'` | 创建或重置管理员 |
| `make monitoring` | 带 `monitoring` profile 起 Prometheus + Alertmanager + Pushgateway + postgres-exporter |
| `make backup` / `make restore` | 立刻备份一次 / 打印恢复入口 |
| `make psql` | 进 psql 排查 |
| `make stack-up` / `make stack-down` / `make stack-status` | 本机直接起停 API + Worker（不用 docker） |
| `make dev-api` / `make dev-worker` / `make dev-web` | 本机分别跑进程 / 前端 dev server |
| `make check` | Python 编译检查 + 前端 `tsc --noEmit` |
| `make smoke` / `make e2e` / `make console-check` / `make config-check` | 四套自动验收（见下节） |

## 开发与测试

四套验收都可以在本地跑（先 `make stack-up`；`smoke` 只需 Postgres + Redis）：

| 命令 | 覆盖 | 当前基线 |
|---|---|---|
| `make smoke` | 共享层：任务队列、租约、统一入库、转发链路、去重；AI 服务层（未配置时报错、请求形状、上游异常冒泡） | `smoke_core` 31/31、`smoke_ai` 12/12 |
| `make e2e` | 端到端：探测、鉴权、权限边界、账号/分组/代理 CRUD、任务、WebSocket、清理 | 41/41 |
| `make console-check` | 控制台新接口：批量、CSV 导出、账号详情聚合、趋势、通知流、排序搜索、批量重试白名单 | 99 + 4 + 26 + 19 项 |
| `make config-check` | 部署产物静态校验：compose 接线、告警规则、`.env.example` 与 config 对齐、nginx 反代 | 33/33 |
| `make check` | Python 编译 + 前端类型检查 | — |

前端另有：`npm run typecheck`、`npm run build`、`npm run lint`；后端迁移自检：`alembic check`（模型与迁移零漂移）。

## 部署与运维

完整告警处置与故障排查在运维手册，恢复演练在备份文档。下面是最常查的四块。

### 四条告警

| # | 告警名（severity） | 判据 | 先做什么 |
|---|---|---|---|
| 1 | `TgccWorkerHeartbeatStale`（critical） | `tgcc_worker_heartbeat_age_seconds > 60` 持续 1 分钟 | `docker compose ps worker`；看日志；`restart worker`。另有 `TgccWorkerTargetDown`、`TgccWorkerTargetsMissing` 覆盖「进程没了 / 指标没起来 / 一个副本都没有」 |
| 2 | `TgccOnlineAccountsDrop`（critical） | 在线号总量近 5 分钟均值相对近 1 小时均值下降 > 30%，持续 5 分钟（15% 的 warning 与「全掉线」兜底各有一条） | 看工作台在线/异常数；`SELECT status, count(*) FROM tg_accounts GROUP BY 1;`；同时看告警 1 是否一起响（一起响是 Worker 侧问题，只掉在线数是号被限制或代理挂了） |
| 3 | `TgccTasksFailedIncreasing` / `TgccTasksOverdue`（warning）、`TgccTasksStuck`（critical） | 失败任务 30 分钟净增 > 5；`overdue > 20`；`stuck > 5` | 任务中心按失败筛查看 `error`；`SELECT type, error, count(*) FROM tasks WHERE status='failed' GROUP BY 1,2;`；到期堆积先看 Worker 副本数与租约占用，再考虑 `--scale worker=N` |
| 4 | `TgccBackupFailed` / `TgccBackupOverdue`（critical）、`TgccDatabaseSizeLarge` / `TgccDatabaseGrowthFast` / `TgccBaseBackupOverdue`（warning） | 备份脚本推的「最近成功时间」为 0 或超 24 小时没更新；库大小超 20 GiB 或按 6 小时趋势 7 天内会超 40 GiB | 看 `/var/log/tgcc-backup.log`；手动 `make backup` 复现；确认 `BACKUP_DIR` 可写、磁盘没满、pushgateway 在跑；涨得快先查 `messages` / `audit_logs` |

监控自身还有三条：`TgccApiDown`、`TgccExporterDown`、`TgccAlertmanagerDown`（不修就会出现「没人告警」的静默故障）。

### 备份与恢复

- 每天 03:10 `pg_dump -Fc` 逻辑备份（保留 7 份）；每周日 03:40 `pg_basebackup` 基础备份（保留 4 份）；
  Postgres 全程 `archive_mode=on`，WAL 归档在 `pg_wal_archive` 卷。
- **按时间点恢复（PITR）= 基础备份 + WAL 归档**，两者缺一不可，都要一起离线保存。
  完整步骤（含临时实例验证、权限与坑）见备份文档，摘要：

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
- 建议每季度按备份文档第 6 节演练一次。

### 发布顺序

1. 需要改表就先跑迁移：`make migrate`（向后兼容的迁移才允许先上线）。
2. **先滚 Worker**：`docker compose up -d --no-deps --build worker`；
   多副本想少掉线就先 `--scale worker=N+1` 让新副本认领一部分号，稳定后再缩回 `N`。
   Worker 收到 SIGTERM 会先释放租约再退出（`stop_grace_period: 60s`）。
3. **最后重启 API**：`docker compose up -d --no-deps api`。API 无状态，页面 WebSocket 会重连，号不受影响。
4. 前端：`docker compose up -d --no-deps --build frontend`。
5. **单个号异常**（会话失效、要验证码、发不出去）：只清这个号的租约 ——
   控制台账号管理页点「释放租约」，或 `DELETE FROM leases WHERE account_id='...';`，**不要重启全部连接**。

### 扩容与日志

- 扩容：`docker compose up -d --scale worker=3`（一副本约 100 个在线号，`ACCOUNTS_PER_REPLICA`）。
  注意 `WORKER_METRICS_PORT_RANGE` 要覆盖副本数（默认 `9101-9110` 支持 10 个副本），
  数据库连接数按 `(DB_POOL_SIZE + DB_MAX_OVERFLOW) × 进程数 < POSTGRES_MAX_CONNECTIONS` 估。
- 日志是 JSON 一行一条，带 `component`，业务日志带 `account_id` / `worker_id` / `task_id`：

```bash
docker compose logs -f --no-log-prefix worker | jq -c 'select(.account_id=="<uuid>")'
docker compose logs --no-log-prefix api | jq -c 'select(.level!="INFO")'
```

## 范围与合规边界

本 README 与规划文档记录的是这套控制台的**主线范围**：

> 管理自己的用户号与官方 Bot → 处理这些号已经在里面的群聊与私信 → 用 Bot 转发到员工群 →
> 员工回复按同一规则送回 → 发送要员工确认 → 全程留审计。

主线**不含**下面这批批量触达动作（规划文档把它们写在「不做这些」清单里）：

> 批量私信、批量群发、素材群发、批量加群、批量退群、强拉进群、批量改资料、吵群，
> 以及用多个用户号自动把话说得像真人。

主线代码里没有这些任务类型；批量接口只允许「检测 / 同步 / 分配 / 分组 / 代理 / 停用启用 / 清租约」
这类对已有账号的运维动作，且**发送类与登录类不允许批量重试**（详见 [任务中心](#任务中心)）。

需要一对多触达时，走官方通道：官方 Bot 广播（只发给主动 `/start` 的用户）、频道发布，
以及本项目的 Bot 转发 + 员工确认发送——这些在合规前提下同样能达到通知、客服与运营的目的。

> ⚠️ **部署方须知**：上面这批动作是平台风控的识别目标（错峰与拟人话术正是规避特征），
> 后果是号池成批被封，运营方还要承担 Telegram 服务条款与当地法律的责任。
> 这份 README 不为这类能力背书；如果你的分支或部署里自行加了它们，风险与合规责任由使用方自负。

## 路线图

- [x] 租约 / 心跳 / 任务队列 / 会话入库 / 单条发送 / Bot 转发 / 审计
- [x] 多号、分组、员工分配、WebSocket 实时推送
- [x] Bot Webhook 去重、转发记录与员工群回复送回
- [x] AI 草稿（停在输入框）与官方 Bot 自动回复
- [x] Docker Compose、备份与 PITR、四条告警、通知流
- [x] 控制台重做：设计 token、深浅双主题、共享组件库、批量与导出
- [ ] 会话媒体预览与下载（图片/文件）
- [ ] 会话标签与备注（需要后端加字段）
- [ ] 告警直达企业微信 / 钉钉 / 飞书机器人
- [ ] 英文文档
- [ ] 多租户字段（当前单租户使用，不拆商户）

## 贡献

- 提 Issue 请带上：版本（commit）、部署方式（Compose / 本地）、复现步骤、期望与实际、相关日志（JSON 一行一条，注意先脱敏手机号与 Token）。
- 提 PR 请保持：`make check` 与相关验收（`make smoke` / `make e2e` / `make console-check` / `make config-check`）全绿，中文注释解释「为什么」，不要引入未在本 README 与规划文档范围内的批量能力。
- **安全问题**不要开公开 Issue：请私下联系仓库作者，附最小复现。
- 本项目只对接一个远程仓库（`origin`），提交时只提交你自己改动的路径，不要顺手带上别人的工作区改动。

## 许可证

**许可证待定**：作者正在为开源发布选定协议（常见选择：AGPL-3.0 或 MIT）。
在 `LICENSE` 文件落地之前，你可以自由地自托管部署并使用本项目的全部功能；
对外二次分发或商用请先联系仓库作者。

选定协议后只需两步：把所选协议的 `LICENSE` 文件加入仓库根目录，并把本 README 顶部的
license 徽章从「待定」改成对应协议。

## 鸣谢

- [Telethon](https://github.com/LonamiWebs/Telethon)、[aiogram](https://github.com/aiogram/aiogram)、[FastAPI](https://github.com/fastapi/fastapi)、[SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy)、[Alembic](https://github.com/sqlalchemy/alembic)、[antd](https://github.com/ant-design/ant-design)、[Vite](https://github.com/vitejs/vite)、[Prometheus](https://github.com/prometheus/prometheus)
- 界面设计与工程实现由本仓库的 Agent Teams 分工完成：设计底座、后端接口、三组页面分队、独立验收
- 以及所有赞助者

<div align="center">
  <br>
  <b>如果这套东西帮你省下了值班时间，给个 ⭐ 支持一下</b>
  <br><br>
  <sub>本项目只用于管理你自己拥有或有权操作的账号与 Bot；请遵守 Telegram 服务条款与当地法律。</sub>
</div>
