# 赞助收款码占位目录

把收款码图片放到这个目录，文件名按下面约定命名（**替换同名占位文件即可**，改完不用动文档）：

| 文件 | 用途 |
|---|---|
| `wechat.svg` | 微信收款码（占位文件，请替换为 `wechat.png` 或直接覆盖本文件） |
| `alipay.svg` | 支付宝收款码（同上） |
| `sponsor-qr.png` | 如果你只想放一张通用收款码，用这个名字，`docs/SPONSOR.md` 里已经预留引用 |

替换建议：

1. 收款码原图尽量是正方形 PNG（≥ 500×500），别用截图带聊天记录的版本；
2. 换成 PNG 时，把 `docs/SPONSOR.md` 里对应的 `wechat.svg` / `alipay.svg` 改成 `wechat.png` / `alipay.png`；
3. 只想放一个码：保存成 `sponsor-qr.png`，然后删掉文档里另外两张图的引用。

> 这些是**占位图**，内容只是提示文字；提交前记得换成真实收款码，不要把占位图留在对外页面上。

## 赞助方 Logo（已收录）

| 文件 | 用途 | 来源 |
|---|---|---|
| `cafinx.png`（256×256） | CAFINX 虚拟卡标识（浅色底用，黑色笔画） | <https://cafinx.com> 站点图标 |
| `cafinx-white.png`（256×256） | CAFINX 虚拟卡标识（深色底用，白色笔画 + 透明底） | 由 `cafinx.png` 生成：黑色笔画转白、白底转透明，保留抗锯齿 |
| `cafinxsim.png`（320×123） | CAFINXSIM 横向字标（浅色底） | 品牌素材 `logo.png` |
| `cafinxsim-white.png`（320×123） | CAFINXSIM 横向字标（深色底，README 用 `<picture>` 自动切换） | 品牌素材 `logo-white.png` |
| `cafinxsim-mark.png`（256×256） | CAFINXSIM 图形标记（方位置用） | 品牌素材 `logo-mark.png` |

更新方式：把新素材覆盖同名文件即可，README 与 SPONSOR.md 的引用不需要改
（深色模式靠 `<picture>` + `prefers-color-scheme` 自动切到 `-white` 版本）。
