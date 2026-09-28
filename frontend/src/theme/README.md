# 主题与设计 token（换皮入口）

> **改配色 / 圆角 / 密度 / 字体，只改 `tokens.ts` 一个文件。**
> 页面和组件里禁止出现写死色值，一律用 CSS 变量 `var(--tg-*)` 或 `useTheme().tokens`。

## 1. 文件职责

| 文件 | 作用 |
|---|---|
| `tokens.ts` | **唯一真源**：颜色 / 间距 / 圆角 / 字号 / 阴影 / 动效 / 布局 / 层级。零运行时依赖（纯数据） |
| `cssVars.ts` | 把 token 展开成 CSS 变量（`--tg-*`），并提供注入函数与常用变量名常量 `V` |
| `antdTheme.ts` | 把 token 映射到 antd v5 `ConfigProvider` 的 token 与 components 覆盖 |
| `ThemeProvider.tsx` | 主题运行时：偏好（浅色/深色/跟随系统）、localStorage 记忆、系统偏好监听、`useTheme()` |

## 2. 生效链路

```
tokens.ts ──┬─→ cssVars.ts ──→ applyThemeVars() ──→ <html> 内联样式（--tg-*）
            │                                        ↑ 内联优先级最高，覆盖一切样式表
            └─→ antdTheme.ts ─→ <ConfigProvider theme={...}> ─→ antd 组件
```

* 首屏（JS 未执行前）：`index.html` 的引导脚本按 `localStorage.tgcc_theme` 或系统偏好设 `data-theme`，
  `styles.css` 里的 `:root` / `[data-theme='dark']` 兜底块提供同名变量，因此不会闪白。
* 运行时：`ThemeProvider` 用 `tokens.ts` 重新注入同名变量，**真源始终是 tokens.ts**。
* 两套主题都是显式值（不是算法派生），所以不会出现「原生 antd 蓝 + 自定义蓝」两种蓝。

## 3. 重新生成 styles.css 兜底块

`styles.css` 里两个 `@tg-vars:light:start/end`、`@tg-vars:dark:start/end` 标记之间的内容是生成的，
**不要手改数值**；改完 `tokens.ts` 后执行（在 `frontend/` 下）：

```bash
./node_modules/.bin/esbuild src/theme/cssVars.ts --bundle --format=esm --platform=neutral \
  --outfile=/tmp/tg-cssvars.mjs --log-level=warning
node -e "$(cat <<'JS'
const fs=require('fs');
(async()=>{const {themeCssVars}=await import('/tmp/tg-cssvars.mjs');
let css=fs.readFileSync('src/styles.css','utf8');
const block=v=>Object.entries(v).map(([k,x])=>`  ${k}: ${x};`).join('\n');
for(const [name,sel,mode] of [['light',':root','light'],['dark',"[data-theme='dark']",'dark']]){
  const re=new RegExp(`(/\\* @tg-vars:${name}:start \\*/)[\\s\\S]*?(/\\* @tg-vars:${name}:end \\*/)`);
  css=css.replace(re,`$1\n${sel} {\n${block(themeCssVars(mode))}\n}\n$2`);}
fs.writeFileSync('src/styles.css',css);console.log('done');})();
JS
)"
```

校验（应输出「无」）：

```bash
node -e "const fs=require('fs');const css=fs.readFileSync('src/styles.css','utf8');
const used=new Set([...css.matchAll(/var\((--tg-[a-z0-9-]+)/g)].map(m=>m[1]));
const def=new Set([...css.matchAll(/^\s*(--tg-[a-z0-9-]+):/gm)].map(m=>m[1]));
console.log([...used].filter(v=>!def.has(v)).join(', ')||'无')"
```

## 4. Token 清单

### 4.1 颜色 `color.*`（每个 token → `--tg-color-<kebab>`）

| 分组 | 变量 | 浅色 | 深色 | 用途 |
|---|---|---|---|---|
| 品牌 | `primary` | `#2aabee` | `#2aabee` | Telegram 蓝，主按钮/选中/链接 |
| | `primaryHover` / `primaryActive` | `#4bb8f0` / `#1e97d6` | `#4cbcff` / `#1e97d6` | 悬浮 / 按下 |
| | `primaryBg` / `primaryBgHover` | `#eaf6fe` / `#dceffc` | `rgba(42,171,238,.16)` / `.24` | 浅底（选中行、Tag） |
| | `primaryBorder` | `#a8dcf8` | `rgba(42,171,238,.42)` | 描边 |
| | `onPrimary` | `#ffffff` | `#04141f` | 主色上的文字 |
| | `gradientFrom` / `gradientTo` | `#2aabee` / `#229ed9` | 同左 | Logo 渐变 |
| 背景 | `bgApp` | `#f6f7f9` | `#0d1117` | 页面底 |
| | `bgSider` / `bgTopbar` | `#ffffff` | `#111721` | 侧栏 / 顶栏 |
| | `bgCard` / `bgCardHover` | `#ffffff` / `#fafbfc` | `#151c26` / `#1a2230` | 卡片 |
| | `bgElevated` | `#ffffff` | `#1b2331` | 浮层（Modal/Dropdown/Popover） |
| | `bgSunken` | `#f7f8fa` | `#10161f` | 表头 / 代码块 / 聊天区 |
| | `bgInput` | `#ffffff` | `#0f151d` | 输入框 |
| | `bgHover` / `bgActive` / `bgSelected` | `rgba(16,24,40,.04/.07)` / `#e8f4fd` | `rgba(255,255,255,.05/.09)` / `rgba(42,171,238,.16)` | 交互态 |
| | `bgMask` / `bgSkeleton` | `rgba(16,24,40,.45)` / `.06` | `rgba(3,6,10,.65)` / `rgba(255,255,255,.07)` | 蒙层 / 骨架 |
| | `scrollThumb` / `scrollThumbHover` | `rgba(16,24,40,.18/.3)` | `rgba(255,255,255,.16/.28)` | 滚动条 |
| | `tooltipBg` / `tooltipText` | `#101828` / `#ffffff` | `#1f2937` / `#f1f5f9` | 提示气泡 |
| | `skeletonHighlight` | `rgba(16,24,40,.1)` | `rgba(255,255,255,.12)` | 骨架高光 |
| 文本 | `textPrimary` | `#101828` | `#e8edf4` | 正文/标题 |
| | `textSecondary` | `#475467` | `#a9b4c4` | 次要 |
| | `textTertiary` | `#667085` | `#7d8899` | 说明/占位 |
| | `textDisabled` | `#98a2b3` | `#5a6577` | 禁用 |
| | `textLink` / `textLinkHover` | `#1e97d6` / `#2aabee` | `#5cc0f5` / `#8ad3ff` | 链接 |
| 边框 | `border` | `#e4e7ec` | `#25303f` | 默认描边 |
| | `borderStrong` / `borderSubtle` / `borderFocus` | `#d0d5dd` / `#eef0f4` / `#2aabee` | `#334155` / `#1c2532` / `#2aabee` | 强/弱/聚焦 |
| | `divider` | `#eceff3` | `#1f2937` | 分割线 |
| 语义 | `success` / `successBg` / `successBorder` | `#12a06a` / `#e6f7ef` / `#b7e6d0` | `#34d399` / `rgba(18,160,106,.16)` / `rgba(74,222,159,.32)` | 正常 |
| | `warning` … | `#d99a00` / `#fff7e6` / `#ffe0a3` | `#fbbf24` / … | 待处理 |
| | `danger` … | `#e5484d` / `#fef3f2` / `#fecdca` | `#f87171` / … | 失败/异常 |
| | `info` … | `#2aabee` / `#eaf6fe` / `#a8dcf8` | `#2aabee` / … | 提示 |
| | `neutral` … | `#667085` / `#f4f5f7` / `#e4e7ec` | `#8b93a1` / … | 无状态 |
| 业务 | `account.<status>.{fg,bg,border,dot}` | 7 态各一组 | 7 态各一组 | 账号状态配色 |
| | `task.<status>.{fg,bg,border,dot}` | 6 态各一组 | 6 态各一组 | 任务状态配色 |
| 图表 | `chart1..chart6` / `chartGrid` / `chartAxis` | `#2aabee #12a06a #f79009 #7a5af8 #e5484d #0ba5ec` | `#38bdf8 #34d399 #fbbf24 #a78bfa #f87171 #22d3ee` | 趋势线 |
| | `shadowColor` | `rgba(16,24,40,.08)` | `rgba(0,0,0,.45)` | 自定义阴影拼接 |

账号状态键：`healthy`（正常）/ `pending`（待登录）/ `needs_code`（要验证码）/ `frozen`（冻结）/
`invalid`（失效）/ `dead`（永久双向）/ `disabled`（停用）。
任务状态键：`pending` / `pending_confirmation` / `running` / `completed` / `failed` / `cancelled`。

### 4.2 间距 `space.*`（→ `--tg-space-*`，8px 网格，`grid(n) = n*8`）

| 变量 | px | 典型用途 |
|---|---|---|
| `none` | 0 | — |
| `xxs` | 2 | 图标与文字微调 |
| `xs` | 4 | 紧凑内间距 |
| `sm` | 6 | Tag 内间距 / 圆点间距 |
| `md` | 8 | 控件之间（基准网格） |
| `lg` | 12 | 卡片内次级分组 |
| `xl` | 16 | 区块内间距 |
| `xxl` | 20 | 抽屉分区 |
| `xxxl` | 24 | 大间距 |
| `huge` | 32 | — |
| `giant` | 40 | — |
| `colossal` | 48 | 内容区底部留白 |
| `mega` | 64 | — |

### 4.3 圆角 `radius.*`（→ `--tg-radius-*`）

| 变量 | px | 用途 |
|---|---|---|
| `none` | 0 | — |
| `xs` | 4 | 徽标/键帽 |
| `sm` | 6 | Tag / 小标签 |
| `md` | 8 | 输入类小元素 / 图标底 |
| `lg` | 10 | 聊天气泡 |
| `card` | **14** | 卡片 / 面板（参考图校准时优先改这里） |
| `cardLg` | 16 | Modal / 大面板 |
| `control` | 8 | 按钮 / 输入框 / Select |
| `pill` | 999 | 胶囊（圆点、进度条、角标） |

### 4.4 字体 `font.*`（→ `--tg-font-*`）

| 变量 | 值 | 用途 |
|---|---|---|
| `family` | `-apple-system, BlinkMacSystemFont, Inter, Segoe UI, PingFang SC, Hiragino Sans GB, Microsoft YaHei, …` | 全局 |
| `familyMono` | `ui-monospace, SFMono-Regular, SF Mono, Menlo, Consolas, …` | ID / Token / 代码 |
| `sizeXs` | 11 | 分组标题、键帽 |
| `sizeSm` | 12 | 说明、表格辅助 |
| `sizeMd` | 13 | 紧凑正文 |
| `size` | **14** | 正文基准 |
| `sizeLg` | 16 | 区块标题 |
| `sizeXl` | 18 | — |
| `sizeTitle` | 20 | 页面标题 |
| `sizeDisplay` | 28 | 统计卡数字 |
| `weightRegular/Medium/Semibold/Bold` | 400 / 500 / 600 / 700 | — |
| `lineTight/Normal/Loose` | 1.25 / 1.55 / 1.75 | — |
| `letterTight` | `-0.01em` | 大字号标题 |

### 4.5 阴影 `shadow.*`（→ `--tg-shadow-*`）

`none` / `xs`（卡片默认）/ `sm` / `md`（悬浮）/ `lg`（浮层）/ `xl`（Modal）/ `focus`（聚焦光环）/ `inset`（顶部高光）。
浅色用柔和灰，深色用更深的黑 + 1px 顶部高光，避免「糊成一片」。

### 4.6 动效 `motion.*`（→ `--tg-motion-*`）

`durationFast` 120ms / `durationBase` 180ms / `durationSlow` 260ms；
`easeStandard` `cubic-bezier(.2,0,0,1)` / `easeOut` / `easeInOut`。

### 4.7 布局 `layout.*`（→ `--tg-layout-*`）

| 变量 | px | 用途 |
|---|---|---|
| `siderWidth` | 232 | 侧栏展开 |
| `siderCollapsedWidth` | 64 | 侧栏折叠 |
| `topbarHeight` | 56 | 顶栏 |
| `contentMaxWidth` | 1680 | 内容区最大宽度（1920 下居中） |
| `contentPaddingX` / `contentPaddingY` | 24 / 20 | 内容区内边距（窄屏由 CSS 派生变量降到 16/12） |
| `pageGap` | 16 | 区块之间 |
| `cardPadding` | 20 | 卡片内边距 |
| `controlHeight` / `Sm` / `Lg` | 34 / 28 / 40 | 控件高度 |

### 4.8 层级 `zIndex.*`（→ `--tg-z-*`）

`base` 0 / `sticky` 10 / `sider` 90 / `topbar` 100 / `drawer` 1000 / `modal` 1100 / `toast` 1200 / `tooltip` 1300。

## 5. 用法

```tsx
// 1) 样式里（推荐）
<div style={{ background: 'var(--tg-color-bg-card)', borderRadius: 'var(--tg-radius-card)' }} />

// 2) JS 里需要色值时
const { tokens, isDark } = useTheme();
chart.setOption({ color: tokens.color.chart1 });

// 3) 只用变量名常量
import { V } from '../theme';
style={{ color: V.textSecondary }}

// 4) 动态状态色（账号/任务）
`var(--tg-color-account-${status}-fg)`
`var(--tg-color-task-${status}-bg)`
```

## 6. 参考图校准清单（Lead 后续只改这些）

| 参考图差异 | 改哪里 |
|---|---|
| 主色/品牌色 | `COLORS_LIGHT/primary*` + `COLORS_DARK/primary*`（含 hover/active/bg/border） |
| 底色、卡片底色、层次 | `bgApp` / `bgCard` / `bgSider` / `bgTopbar` / `bgElevated` / `bgSunken` |
| 文字深浅、灰阶 | `textPrimary/Secondary/Tertiary` |
| 描边轻重 | `border` / `borderSubtle` / `divider` |
| 圆角 | `RADIUS.card` / `RADIUS.cardLg` / `RADIUS.control` |
| 密度（松紧） | `LAYOUT.cardPadding` / `contentPaddingX/Y` / `pageGap` / `controlHeight` |
| 字号层级 | `FONT.size*` |
| 阴影强弱 | `SHADOW_LIGHT/SHADOW_DARK` |
| 侧栏宽度、顶栏高度 | `LAYOUT.siderWidth` / `topbarHeight` |
| 卡片是否带描边/阴影 | `styles.css` 的 `.tg-card`（唯一允许的"外壳"级样式调整） |
