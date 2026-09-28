# 变更记录

版本号只有一处真源：仓库根目录的 [`VERSION`](VERSION) 文件——后端 `/health` 返回它，
前端构建时注入它（侧栏左下角显示），发布时同步打 git tag。

格式按「版本 → 日期 → 本次功能信息」记录，新增功能与修复都写清**对用户意味着什么**。

---

## v0.3.1 — 2026-09-29

主题：**文档与品牌标识补齐**——赞助方 Logo 入库、README 写完整、版本记录机制固化。

### 文档

- README 新增「最新更新」（当前版本功能摘要）与「赞助方」（Logo + 简介）两段，
  顶部徽章补齐版本与变更记录入口，界面预览补上营销中心与群情报截图。
- [`docs/SPONSOR.md`](docs/SPONSOR.md) 新增「赞助方」区块与「企业赞助与 Logo 展示」说明，
  列清成为赞助方需要提供的素材规格（浅色底 + 深色底两版）。
- 新增赞助方素材到 `docs/assets/sponsor/`：

| 文件 | 赞助方 | 用途 |
|---|---|---|
| `cafinx.png` | [CAFINX 虚拟卡](https://cafinx.com) | 狐狸标识，README 与赞助页展示 |
| `cafinxsim.png` / `cafinxsim-white.png` | [CAFINXSIM](https://cafinxsim.com) | 横向字标，深色模式用 `<picture>` + `prefers-color-scheme` 自动切白色版 |
| `cafinxsim-mark.png` | CAFINXSIM | 图形标记（方位置用） |

- 素材维护方式写入 `docs/assets/sponsor/README.md`：覆盖同名文件即可，Markdown 引用不用改。

### 修复

- `docs/SPONSOR.md` 的「赞助方」区块一直没写进去：判断条件用了 `"## 赞助方"`，
  而它是 `"## 赞助方式"` 的前缀，永远命中为「已存在」。改用图片路径做存在性判断后正常写入。

---

## v0.3.0 — 2026-09-29

主题：**账号矩阵成熟化**——多格式导入、验活、防封，加上群情报采集与官方机制养号。

### 新增功能

**账号矩阵：多账户导入与批量管理**（`docs/ACCOUNT_MATRIX.md` 第 1-6 节）

- 四种导入方式：手机号清单、Telethon StringSession 串、`.session` 文件（Telethon / Pyrogram SQLite，
  自动读 `auth_key` + `dc_id`）、tdata 目录 zip（可选依赖 `opentele2`，未装时给出替代路径）。
  先 `/parse` 预览再落库，逐条回执，写批次记录可回溯来源。
- 去重修正：`phone_enc` 是 Fernet 密文（带随机 IV），拿密文做等值查询永远查不到——新增
  `phone_hash` 确定性哈希列，导入与建档共用同一个去重键。
- 每号独立**设备指纹**，连接时带入 `TelegramClient`；一批号同型号同版本是最显眼的批量特征。
- **深度验活**：读权限、授权会话数、可选写权限探测，复算 0-100 健康分（账号页新增「健康」列，
  绿 ≥80 / 黄 ≥50 / 红 <50），详情走 `/api/accounts/{id}/matrix`。
- **批量节流旋钮**：`/api/accounts/bulk/throttle` 设置每日上限、最小间隔、解熔断、重置养号起点。

**防封：四道闸门 + 养号阶梯**（`docs/ACCOUNT_MATRIX.md` 第 3 节）

- 熔断（FloodWait 写冷却，期间发送类任务顺延）、活跃时段（默认只在北京时间 08:00–24:00 动作）、
  动作最小间隔、Redis 每日配额。
- 养号阶梯按号龄放量：0-2 天 20 条/120 秒 → ≥30 天 200 条/20 秒；连续限流 3 次额度自动减半。
- 动作权重：消息 1，群发/吵群/加群/强拉 3，读取类 0——「一天发 20 条私信」与「一天进 20 个群」
  不再被同等对待。

**群情报：入群即采的无感采集**（第 7-9 节）

- 三张表：群档案、成员快照、入退群流水（含「被谁拉进来」）。事件由 Worker 的 `ChatAction` 回调
  静默记录——不回复、不打招呼、不加表情、不撤回。
- 采集只用读接口，成员名单按页拉取（页间隔默认 3 秒、单任务上限 500），大群不一次性拉全量。
- **按链接采集群员**：粘贴 `t.me/xxx`、`t.me/+hash`、`@username`、数字 ID，自动解析、可选加入、
  采完可退出；多链接 round-robin 分给不同账号。
- **进度可见**：`/api/group-intel/jobs` 给出每条任务的阶段（解析 → 定位/加入 → 采集中 N/M → 完成）
  与失败原因，页面 5 秒轮询；**采集后打包**：zip 内含群总表、每群成员明细、事件流与清单文件。

**官方机制养号**（第 10 节）

- 身份对齐：`OFFICIAL_CLIENTS` 收录 13 个真实发布过的客户端身份，导入指纹不再随机编造版本号。
- 限制对齐：`sync_official` 读服务端下发的 `help.GetAppConfig`，把 flood/上限参数落库，
  节流换算只有一条规则——**取更严的那个**（服务端收紧立刻跟上，放宽不给松绑）。
- 行为对齐：`warmup_activity` 按官方客户端节奏上线 → 翻会话 → 可选已读/打字 → 下线，
  全程不发消息、不加群；批量入口在账号页「官方养号」。

### 修复

- **整页白屏缺陷**：`localStorage` 里存着旧结构或残缺对象（例如 `{}`）时，`useLocalStorage`
  不与默认值合并，导致 `state.xxx.includes(...)` 读到 undefined，整个侧栏崩、整页被 ErrorBoundary
  兜住。现在 `readJson` 做浅合并并对数组字段校验，侧栏再加一层兜底。
- **失败原因撑破列宽**：antd 表格的 `ellipsis` 在自定义 `render` 下不生效，红色长文本会压到隔壁列。
  新增 `.tg-clamp-cell` 块级截断 + Tooltip，并把表格改为固定布局 + 横向滚动（5 处渲染点）。
- 导入去重、`upload_max_fileparts` 被误当限制参数、`collect_link` 枚举值晚于建表迁移等若干问题。

### 验收

```
cd backend && .venv/bin/python -m tests.matrix_check             # 14 项 账号矩阵导入/去重/节流/验活
cd backend && .venv/bin/python -m tests.group_intel_check        # 10 项 群情报查询与导出
cd backend && .venv/bin/python -m tests.collect_link_check       #  7 项 按链接采集
cd backend && .venv/bin/python -m tests.collect_progress_check   # 13 项 采集进度与打包
cd backend && .venv/bin/python -m tests.official_check           # 17 项 官方机制养号
cd backend && .venv/bin/python -m tests.campaign_api             # 30 项 批量运营
backend/.venv/bin/python scripts/e2e_check.py                    # 41 项 既有回归
```

界面截图：`cd frontend && npm run screenshots`（深色）或 `npm run screenshots -- --theme light`。

---

## v0.2.0 — 2026-09-28

主题：**营销中心成型 + 界面体系化**，并转为可自托管的开源定位。

### 新增功能

- **营销中心**：批量私信、群发、素材群发、批量加群、批量退群、强拉进群、批量改资料、吵群、
  拟人发言共 9 类批量动作；一次性提交一批账号，按批次查看进度、可取消、可重试。
- **素材库**：文本 / 图片 / 视频 / 文档素材统一管理，素材群发按号分配不同话术，降低重复内容特征。
- **拟人化**：文本池按号分配、口语化微调、随机间隔、上下文相关的连续发言。
- **导航改三级子菜单**：侧栏分组 → 父项 → 子项，面包屑三级可点，营销中心 11 个功能各自独立路由。
- **企业级界面**：重写登录页（品牌叙事 + 环境标识 + 记住用户名 + 大写锁定提示）、
  工作台队列卡片与快捷入口、账号页登录向导与新账号引导条。
- **开源化**：去掉全部「内部系统」定位表述，README 改为可自托管口径（AGPL/自托管路线）。

### 修复

- `/campaigns` 路由缺失导致 404；批量聚合 SQL 的 `GROUPING` 错误；侧栏父项按钮继承浏览器默认样式
  呈现为灰色色块。

---

## v0.1.0 — 2026-09-26

首个可用版本：账号管理（分组 / 代理 / 租约）、会话收件箱（WebSocket 实时）、
任务中心（队列 / 重试 / 取消）、Bot 管理与转发、操作审计、CSV 导出、
Worker 与 API 分离（用户号任务走 Worker，Bot 任务走 API）、本地一键起停脚本与验收基线。
