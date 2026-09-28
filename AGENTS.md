# Telegram 云控 —— 项目约定

## Git：本项目只对接 cafinxnull 这一个仓库

- `origin` → `https://github.com/cafinxnull/telegram-cloud-control`（private，`main`）
- 这是**本项目专属**远程。不要为它新增、切换或迁移任何其他 remote。
- 凭据按仓库隔离：本仓库局部配置 `credential.https://github.com.username=cafinxnull`，
  macOS keychain 中 `acct=cafinxnull` 条目只服务本项目，push 无需再认证。
  该条目与 `acct=DuanNaiSheQu` 并存，互不覆盖。

## 硬约束：不得影响其他项目

1. 不改 `gh` 的全局登录状态（active 账号保持 `DuanNaiSheQu`），不执行
   `gh auth login / logout / switch` 这类会波及全局的操作。
2. 不触碰 `DuanNaiSheQu` 名下的任何仓库（`cafinxesim`、`claude-*`、`Telegram-bot` 等）：
   不改名、不转移、不删除、不推送。
3. 提交只包含明确要提交的文件；工作区里他人未提交的改动保持原样，不代为 commit。

## 本地运行（不用 Docker）

依赖本机 Postgres `127.0.0.1:55432` 与 Redis `127.0.0.1:56379`（配置见 `backend/.env`）。

- 起停整套：`make stack-up` / `make stack-down` / `make stack-status`
- 控制台：<http://127.0.0.1:5173>（`cd frontend && npm run dev`，`/api` 反代到 `:8000`）
- API：<http://127.0.0.1:8000>；健康检查是 `/health` 与 `/ready`，**没有** `/api` 前缀
- 进程 pid 写在 `run/{api,worker,web}.pid`，日志在 `run/*.log`
- `backend/.env` 中 `TELEGRAM_API_ID=0`、`TELEGRAM_API_HASH` 为空时，worker 只认领租约
  与发心跳、不建立 Telegram 连接，属预期行为（账号不会显示在线）

## 本地栈排障要点

- `run/*.pid` 可能因进程被外部重启而失效，`make stack-down` 前先 `make stack-status`
  核对真实 pid；进程真实归属以 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 为准。
- 同时跑多个 worker 副本会互抢账号租约，日志刷 `已放开该号 / 租约已不属于本进程`；
  本地只应保留一个 api + 一个 worker。
