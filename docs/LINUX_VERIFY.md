# Linux 部署后必须验证的一件事

> 这份清单只在**第一次把云控跑到 Linux 上**时需要走一遍。走完没问题就可以忘掉它。

## 为什么需要单独验证

加群自动过验证分两条通道，它们在 Linux 上的风险**完全不同**：

| 通道 | 原理 | Linux 上的风险 |
|---|---|---|
| **佩奇（Cap）** | 工作量证明 + 服务器签名的 `tgWebAppData` | **无风险**。纯计算，与图形环境无关 |
| **NuoMi（Turnstile）** | Cloudflare 主动识别自动化 | **需实测**。它要求页面真实可见，且会看渲染指纹 |

Linux 服务器通常没有桌面，我们靠 **Xvfb** 造一块虚拟屏幕。**Xvfb 是软件渲染**（llvmpipe），
WebGL 指纹与真实 GPU 有差异 —— Turnstile 有可能会识别这一点。**这一点在 macOS 上无法验证**，
必须在目标机器上跑一次才能确定。

## 三步走

### ① 装环境

```bash
bash scripts/install_browser.sh
```

### ② 自检

```bash
cd backend
.venv/bin/python -c "from app.services.verify_runner import verify_runner; import json; print(json.dumps(verify_runner.preflight(), ensure_ascii=False, indent=2))"
```

看 `ready` 字段：

- `true` → 继续第 ③ 步；
- `false` → 按返回里的 `hint` 装依赖（通常是缺 Xvfb 或 Chrome）。

### ③ 实测 Turnstile（关键一步）

建一个加群任务，目标是**一个带 NuoMi 验证的群**（比如 `@devqun`），然后看任务结果：

```json
{
  "verified": true,
  "verify": { "kind": "turnstile", "passed": true, "elapsed": 18.6 }
}
```

**看 `verify.passed`**：

- **`true`** → ✅ 这条路通了，之后全自动，不用再管；
- **`false`** → ❌ 读 `verify.error`：
  - `打开真 Chrome 失败` → Chrome/Xvfb 没装好，回到第 ① 步；
  - `浏览器阶段未在预期时间内放行` → **Xvfb 的软件渲染被 Turnstile 识别了**，见下面的退路。

## 如果 Turnstile 在 Xvfb 下过不了

按投入从低到高：

1. **换一台带桌面/GPU 的 Linux 机器**（Ubuntu Desktop 也行）—— 真 GPU 渲染，最稳；
2. **只把 NuoMi 类群分流到那台机器上跑**，Cap 类群留在无桌面的服务器上（Cap 不受影响）；
3. **给 Xvfb 配虚拟 GPU**（工程量大，一般不必要）。

## 不需要为它担心的部分

- **佩奇（Cap）**：Linux 上直接可用，不需要额外验证；
- **`apply` / 私信 / 群发 / 采集**等其它功能：与图形环境无关；
- **退群重进重试**：逻辑平台无关，已在 macOS 上验证。

## 顺带一条运维提醒

验证流程要**独占号的会话**。跑验证时 Worker 会让出该号 ——
同一个 Telegram session 被两处同时连接会触发 `AuthKeyDuplicated`，**号会永久报废**。
所以：**同一时间只跑一个 Worker 副本**（AGENTS.md 里也有这条）。
