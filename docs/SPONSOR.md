<div align="center">
  <img src="assets/logo.svg" width="88" alt="Telegram 云控">
  <h1>赞助支持</h1>
  <p><b>让这套控制台一直有人维护、一直跟得上 Telegram 的变化</b></p>
  <p>
    <a href="https://github.com/sponsors/cafinxnull"><img src="https://img.shields.io/badge/GitHub%20Sponsors-赞助-3FB950?logo=githubsponsors&logoColor=white" alt="GitHub Sponsors"></a>
    <a href="#赞助方式"><img src="https://img.shields.io/badge/%E7%88%B1%E5%8F%91%E7%94%B5-%E8%B5%9E%E5%8A%A9-946CE6" alt="爱发电"></a>
    <a href="#赞助方式"><img src="https://img.shields.io/badge/%E5%BE%AE%E4%BF%A1%2F%E6%94%AF%E4%BB%98%E5%AE%9D-%E6%89%AB%E7%A0%81-07C160" alt="微信/支付宝"></a>
    <a href="../README.md"><img src="https://img.shields.io/badge/%E8%BF%94%E5%9B%9E-README-2AABEE" alt="返回 README"></a>
  </p>
</div>

---

> 文档索引：[docs/README.md](README.md) · 相邻：版本记录 [../CHANGELOG.md](../CHANGELOG.md)

## 赞助方

感谢下面的赞助方。它们不只是出钱，本身也都是这套系统在真实运营中用到的服务——
放在这里既是对它们的回报，也是给同样在做多号运营的人的参考。

<table>
  <tr>
    <td align="center" width="50%">
      <a href="https://cafinx.com"><img src="assets/sponsor/cafinx.png" width="96" alt="CAFINX 虚拟卡"></a><br>
      <b><a href="https://cafinx.com">CAFINX 虚拟卡</a></b><br>
      <sub>跨境收付虚拟卡</sub><br>
      <sub><a href="https://cafinx.com">cafinx.com</a></sub>
    </td>
    <td align="center" width="50%">
      <a href="https://cafinxsim.com">
        <picture>
          <source media="(prefers-color-scheme: dark)" srcset="assets/sponsor/cafinxsim-white.png">
          <img src="assets/sponsor/cafinxsim.png" width="220" alt="CAFINXSIM">
        </picture>
      </a><br>
      <b><a href="https://cafinxsim.com">CAFINXSIM</a></b><br>
      <sub>全球 eSIM 流量卡</sub><br>
      <sub><a href="https://cafinxsim.com">cafinxsim.com</a></sub>
    </td>
  </tr>
</table>

### 为什么这两个和本项目相关

| 赞助方 | 做什么 | 在本项目里的用法 |
|---|---|---|
| [CAFINX 虚拟卡](https://cafinx.com) | 跨境收付用的虚拟卡 | Telegram 相关的订阅与小额多笔付款；多号运营时分账、控额度 |
| [CAFINXSIM](https://cafinxsim.com) | 全球 eSIM 流量卡 | 一机一号一出口：海外号需要稳定、干净的出口 IP 时，eSIM 比公共代理更不容易撞风控 |

> 说明：以上是赞助方介绍，不构成效果承诺。出口 IP 只是降低风控的一个变量，
> 账号能不能用得久，更多取决于行为是否像真人（见 [ACCOUNT_MATRIX.md](ACCOUNT_MATRIX.md) 的节流与官方机制养号）。

### 企业赞助与 Logo 展示

- **企业赞助**包含本页与 README 的 Logo 展示位，位置与尺寸与上面两家一致；
- Logo 素材请提供：**浅色底一张 + 深色底一张**（PNG 透明背景或 SVG，横向字标建议宽度 ≥ 640px），
  归档到 `docs/assets/sponsor/` 后由维护者更新本页与 README；
- 已收录的素材：`docs/assets/sponsor/cafinx.png`（CAFINX 虚拟卡）、
  `docs/assets/sponsor/cafinxsim.png` 与 `cafinxsim-white.png`（CAFINXSIM，深浅两版）。

---

## 为什么需要赞助

这套控制台是给**自己的号、自己的 Bot 自己用**的运维后台：代码里没有 SaaS 收费点，不塞广告，
也不把数据卖出去。它需要持续跟进 Telegram 的变更（错误码、限流规则、权限模型），
还要修 bug、补文档与测试——这些都需要人花时间。

**没有赞助，项目不会消失，但只会以最低速度维护**：修崩溃和安全问题优先，新功能看节奏。
有支持就能把「跟进 Telegram 变化」和「把运维体验做扎实」当成正经事情做。

## 赞助方式

### ① GitHub Sponsors（推荐，走 GitHub 更透明）

- 一次性或按月：<https://github.com/sponsors/cafinxnull>
- 仓库右上角的 **Sponsor** 按钮也指向这里（配置在 [`.github/FUNDING.yml`](../.github/FUNDING.yml)）。

### ② 爱发电 / 其他平台

在 [`.github/FUNDING.yml`](../.github/FUNDING.yml) 里把 `custom` 段的地址换成你的主页即可；默认会同时指向本页。

### ③ 微信 / 支付宝扫码

<table>
  <tr>
    <td align="center"><b>微信</b><br><img src="assets/sponsor/wechat.svg" width="200" alt="微信收款码"></td>
    <td align="center"><b>支付宝</b><br><img src="assets/sponsor/alipay.svg" width="200" alt="支付宝收款码"></td>
  </tr>
</table>

> 上面两张是**占位图**：把真实收款码按 [assets/sponsor/README.md](assets/sponsor/README.md) 的说明替换掉即可（换成 `wechat.png` / `alipay.png` 时记得改本页的图片路径）。

### ④ 企业赞助

需要**Logo 展示、需求优先排期、部署协助或私有化定制**的，请在赞助留言里写明：公司名、联系方式、想要的支持内容。企业赞助会单独签一页支持范围（不含任何绕过平台规则或平台风控的能力，见下方 FAQ）。

## 不设档位

这里**不列金额、不设档位**：有多少力出多少力，给多给少都一样，匿名也完全可以。

- 赞助不换取功能、不改范围边界（见下方 FAQ），只用于「让这套东西继续被维护」；
- 如果你代表公司需要 **Logo 展示、需求优先排期或部署协助**，走[企业赞助](#企业赞助)，
  在留言里写清需要的支持内容即可，支持范围单独签一页。

> 一句话：**先用得上、再决定要不要支持**。项目不需要赞助也能完整跑起来，也不存在「赞助才解锁功能」。

## 鸣谢墙

赞助者名单（按时间倒序；想匿名、改名或去掉名字，随时说）：

| 赞助者 | 时间 | 留言 |
|---|---|---|
| *虚位以待* | — | 第一位赞助者会出现在这里 |

代码与文档的贡献者名单见 [README 的鸣谢一节](../README.md#鸣谢)。

## 常见问题

**Q：赞助后能要求开放某些功能吗？**

不能，而且这跟钱无关。这批能力是批量骚扰与「水军」工具的典型形态（错峰、拟人话术就是为了规避平台风控），后果是号池成批被封、运营方承担法律风险。项目在 [规划.md](../规划.md) 里把它们明确写在「不做这些」清单里，README 也照实写清楚。赞助**不会**改变这条边界。

**Q：那赞助买的是什么？**

支持的是「这套已经在用的东西继续被维护」：跟进 Telegram 变更、修 bug、把运维和界面做扎实、文档和测试补齐。金额多少不影响这一点。

**Q：赞助与商业授权的关系？**

本项目当前**尚未选定开源协议**（见 [README 的许可证一节](../README.md#许可证)）。想在自己的服务器上部署使用，直接照 README 部署即可，不需要额外授权；想把代码二次分发或商用，请先联系作者。

## 联系

- 赞助相关：在 [Issues](https://github.com/cafinxnull/telegram-cloud-control/issues) 开一条带 `sponsor` 标签的（或直接邮件联系仓库作者）
- 安全问题：不要开公开 Issue，按 [README 的安全一节](../README.md#安全) 私下报
