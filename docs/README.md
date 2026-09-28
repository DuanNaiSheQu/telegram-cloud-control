# 文档索引

这里是全部文档的入口。按「你要做什么」找对应的一篇，不用从头读。

| 我想…… | 看这篇 | 说明 |
|---|---|---|
| 把系统跑起来、登录第一个号 | [GETTING_STARTED.md](GETTING_STARTED.md) | 从零到发出第一条消息，含环境准备与常见坑 |
| 知道这套系统能做什么 | [FEATURES.md](FEATURES.md) | 功能总览与归类，每项都指向详细文档 |
| 搞清进程、表结构、队列怎么跑 | [ARCHITECTURE.md](ARCHITECTURE.md) | 进程职责、数据模型、任务队列、租约与心跳 |
| 调接口 / 写客户端 | [API_CONTRACT.md](API_CONTRACT.md) | 全部 REST 端点与 WebSocket 协议 |
| 管账号：导入、验活、防封、批量改 | [ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md) | 账号矩阵、节流防封、群情报、官方机制养号 |
| 部署到服务器 / 备份 / 升级 | [DEPLOYMENT.md](DEPLOYMENT.md) | Compose 部署、反代与证书、备份恢复、升级回滚 |
| 线上出问题了 | [OPERATIONS.md](OPERATIONS.md) | 故障速查、告警处置、容量与巡检 |
| 搞清楚密钥、权限、数据边界 | [SECURITY.md](SECURITY.md) | 加密、权限模型、审计、采集的行为边界 |
| 跑验收 / 复现测试结论 | [ACCEPTANCE.md](ACCEPTANCE.md) | 验收范围、不变量与可复跑清单 |
| 想改代码 / 提 PR | [CONTRIBUTING.md](CONTRIBUTING.md) | 开发环境、代码约定、验收门槛、提交规范 |
| 版本改了哪些东西 | [../CHANGELOG.md](../CHANGELOG.md) | 按版本记录功能与修复 |
| 接下来打算做什么 | [../规划.md](../规划.md) | 范围边界与路线 |
| 赞助 / 成为赞助方 | [SPONSOR.md](SPONSOR.md) | 赞助方、支持方式、Logo 展示位 |

## 按类别归类

### 入门

- **[GETTING_STARTED.md](GETTING_STARTED.md)** — 环境要求、本地起栈、首次登录账号、发第一条消息、常见坑排查。

### 功能

- **[FEATURES.md](FEATURES.md)** — 全部功能的地图：账号矩阵、群情报、营销中心、任务队列、Bot 与转发、审计与导出。
- **[ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md)** — 四类导入方式、深度验活、节流防封（四道闸门 + 养号阶梯）、
  批量管理清单、群情报（无感采集 / 按链接采集 / 进度与打包）、官方机制养号。

### 架构与接口

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — 进程与职责、数据模型、任务队列与租约、收件箱的两条连接、状态口径。
- **[API_CONTRACT.md](API_CONTRACT.md)** — 鉴权、工作台、账号、分组与代理、会话与消息、任务、Bot 与转发、WebSocket。

### 运维与部署

- **[DEPLOYMENT.md](DEPLOYMENT.md)** — 本地与 Compose 两种起法、生产清单、反向代理与证书、备份与恢复、升级与回滚。
- **[OPERATIONS.md](OPERATIONS.md)** — 故障速查表、告警处置、常见故障、容量与扩容、日常巡检。
- **[../deploy/postgres-backup.md](../deploy/postgres-backup.md)** — 数据库备份脚本的细节与演练步骤。

### 安全与验收

- **[SECURITY.md](SECURITY.md)** — 凭据与密钥、权限模型、审计留痕、采集与发送的行为边界、数据留存建议。
- **[ACCEPTANCE.md](ACCEPTANCE.md)** — 验收范围、关键不变量、可复跑命令，以及哪些必须真机验证。

### 协作与社区

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — 开发环境、代码约定、验收门槛、提交与 PR 规范、安全问题披露方式。
- **[../AGENTS.md](../AGENTS.md)** — 本仓库的协作约定（远程仓库、凭据隔离、本地运行）。
- **[SPONSOR.md](SPONSOR.md)** — 赞助方与支持方式（不设档位与金额）、企业 Logo 展示位规格。
- **[../CHANGELOG.md](../CHANGELOG.md)** — 版本记录（版本号真源是 [`../VERSION`](../VERSION)）。

### 代码内文档

- **[../frontend/src/components/README.md](../frontend/src/components/README.md)** — 通用组件清单与用法（改 UI 前先看）。
- **[../frontend/src/theme/README.md](../frontend/src/theme/README.md)** — 设计 token 与主题机制（改样式前先看）。
- **[assets/sponsor/README.md](assets/sponsor/README.md)** — 赞助方 Logo 素材的替换方式。

## 阅读顺序建议

1. **第一次接触**：GETTING_STARTED → FEATURES → ACCOUNT_MATRIX。
2. **要上线**：DEPLOYMENT → SECURITY → OPERATIONS。
3. **要改代码**：ARCHITECTURE → API_CONTRACT → CONTRIBUTING → 代码内文档。

## 文档约定

- 全部中文；命令与字段名保持原样。
- 结论与命令必须与当前代码一致；改了行为就同步改文档，并在 [../CHANGELOG.md](../CHANGELOG.md) 记一条。
- 截图统一由 `cd frontend && npm run screenshots` 生成（深色）/ `-- --theme light`（浅色），
  素材放在 `frontend/screenshots/`。
- 每篇文档顶部有一行导航，指回本索引与相邻文档。
