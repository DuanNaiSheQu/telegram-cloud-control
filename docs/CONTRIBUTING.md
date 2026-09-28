# 贡献指南

> 文档索引：[docs/README.md](README.md) · 相邻：架构 [ARCHITECTURE.md](ARCHITECTURE.md) · 版本记录 [../CHANGELOG.md](../CHANGELOG.md)

欢迎改代码，但请守住两条：**行为要与文档一致**，**提交要小且可回滚**。

## 1. 本地开发环境

```bash
make stack-up                     # Postgres + Redis + API + Worker
cd frontend && npm install && npm run dev    # http://127.0.0.1:5173
```

- 环境变量与首次登录：[GETTING_STARTED.md](GETTING_STARTED.md)。
- 本地只能跑一个 Worker（多副本会抢租约，见 [AGENTS.md](../AGENTS.md)）。

## 2. 代码约定

### 后端

- Python 3.12，`ruff` 风格；类型标注尽量写全，`Optional` 显式。
- **注释解释「为什么」，不解释「是什么」**：例如「Fernet 密文带随机 IV，所以去重要用确定性哈希」这类
  踩过坑的地方必须写；`i += 1` 这种不用写。
- 数据库改动一律走 Alembic 迁移，**只做加法**（`ADD COLUMN` / `CREATE TABLE` / `ALTER TYPE ADD VALUE`），
  默认值保证老数据语义不变。
- 新增任务类型：`TaskType` 加值 → 迁移加枚举值 → Worker 注册 handler → 视情况加入批量重试白名单
  （只读任务才加）。别忘了这一步，否则入队会报枚举不存在。
- 对 Telegram 的调用：先判 `flood_wait_seconds()`，限流要写熔断（`note_flood`）而不是硬重试。

### 前端

- React + TS + antd；改 UI 前先读 [../frontend/src/components/README.md](../frontend/src/components/README.md)
  与 [../frontend/src/theme/README.md](../frontend/src/theme/README.md)（组件与 token，别自己造样式）。
- 颜色、间距、字号一律用 CSS 变量（`var(--tg-*)`），不要写死色值。
- 表格里显示长文本（错误、说明）要用 `.tg-clamp-cell` + `Tooltip`：antd 的 `ellipsis` 在自定义 `render`
  下不生效，会撑破列宽遮挡相邻列。
- 组件里的中文文案要写「用户能看懂的原因」，不要写内部术语（例如「该号不在群里：勾选自动加入后可采集」）。

### 通用

- 中文注释与中文界面文案；命令、字段名、错误码保持原文。
- 默认 ASCII 之外才用 Unicode；文件本身已用中文时保持一致。
- 不要提交：`run/`、`backend/.venv/`、`node_modules/`、`.env`、素材文件、截图脚本的 `manifest-*.json`。

## 3. 验收门槛（提交前必须全绿）

```bash
cd frontend && npm run typecheck && npm run build     # 类型 + 构建
cd backend && .venv/bin/python -m tests.matrix_check           # 14 项 账号矩阵
cd backend && .venv/bin/python -m tests.group_intel_check      # 10 项 群情报
cd backend && .venv/bin/python -m tests.collect_link_check     #  7 项 按链接采集
cd backend && .venv/bin/python -m tests.collect_progress_check # 13 项 采集进度与打包
cd backend && .venv/bin/python -m tests.official_check         # 17 项 官方机制养号
cd backend && .venv/bin/python -m tests.campaign_api           # 30 项 批量运营
backend/.venv/bin/python scripts/e2e_check.py                  # 41 项 既有回归
```

- 改了某块功能就顺手补该块的验收项；测试脚本自己清理造的数据。
- 涉及 Telegram 真机的部分本地跑不了（`TELEGRAM_API_ID=0`）：在 PR 里写明「未真机验证」，
  并说清验证方式。见 [ACCEPTANCE.md](ACCEPTANCE.md) 第 5 节。

## 4. 提交与 PR

- 提交信息写清「做了什么 + 为什么」，一次提交只做一件事；**只提交你自己改的路径**
  （`git commit -- <路径>`），不要把别人工作区的改动卷进来。
- 发版三件事：改 [`../VERSION`](../VERSION) → 在 [`../CHANGELOG.md`](../CHANGELOG.md) 加一条
  （功能 / 修复 / 验证）→ 打 tag。
- PR 描述请包含：变更点、影响范围（哪个页面/接口/进程）、验收结果、是否需要迁移或新环境变量。
- 如果改动会改变用户可见行为，**同一次 PR 里更新对应文档**（`docs/` 下的哪一篇，自己判断）。

## 5. 加新功能时的自查

- [ ] 是否需要新表/新列？迁移只做加法了吗？老数据默认值合理吗？
- [ ] 新任务类型加进枚举 + 迁移 + handler 注册了吗？
- [ ] 发送类动作过闸门（`_throttle_gate`）并记账（`_throttle_record`）了吗？
- [ ] 只读采集是否限速、是否有单任务上限？
- [ ] 长文本列是否有截断 + Tooltip？
- [ ] 文档与 CHANGELOG 更新了吗？验收脚本补了吗？

## 6. 安全与漏洞

**不要开公开 Issue**：私下联系仓库作者，附最小复现与影响范围，确认后在修复版本里致谢。
细节见 [SECURITY.md](SECURITY.md) 第 7 节。
