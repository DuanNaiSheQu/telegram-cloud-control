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

## 为什么需要赞助

这套控制台是给**自己的号、自己的 Bot、自己的员工**用的运维后台，代码里没有 SaaS 收费点，也不会塞广告或者把数据卖出去。它的成本都在看不见的地方：

| 成本项 | 说明 |
|---|---|
| 服务器与带宽 | API、Worker、Postgres、Redis、Prometheus 一整套跑起来至少一台常驻机器；号越多，Worker 副本越多 |
| 出站代理 | 每个用户号要走固定出口，代理是月付的 |
| AI 调用 | 会话页的「AI 草稿」和 Bot 自动回复按 token 计费 |
| 域名与证书 | Webhook 必须公网可达（HTTPS），Bot 才收得到消息 |
| 维护时间 | Telegram 客户端与 Bot API 一直在变：错误码、限流规则、权限模型，每次都要跟；依赖升级、迁移、告警调优也都是时间 |

**没有赞助，项目不会消失，但只会以最低速度维护**：修崩溃和安全问题优先，新功能看心情。有赞助就能把「跟进 Telegram 变化」和「把运维体验做扎实」当成正经事情做。

## 资金去向

| 用途 | 占比（目标） | 具体花在哪 |
|---|---|---|
| 基础设施 | ~40% | 服务器、带宽、代理、域名与证书 |
| 模型调用 | ~20% | 草稿生成与 Bot 自动回复的 API 费用（赞助到位会加额度与更长的上下文） |
| 开发与维护 | ~30% | 跟进 Telegram API 变更、依赖升级、修 bug、写文档与测试 |
| 备份与容灾 | ~10% | 异地备份存储、恢复演练环境 |

每季度在本页更新一次收支与用途（收入不足时按比例缩减，不会挪用）。

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

需要**Logo 展示、需求优先排期、部署协助或私有化定制**的，走企业档并在赞助留言里写明：公司名、联系方式、想要的支持内容。企业档会单独签一页支持范围（不含任何绕过平台规则或平台风控的能力，见下方 FAQ）。

## 赞助档位

| 档位 | 金额（一次性 / 月） | 你能得到 |
|---|---|---|
| ☕ 一杯咖啡 | ¥20 / ¥10 | 鸣谢名单留名（可匿名） |
| 🍱 一顿饭 | ¥100 / ¥30 | 上一档 + Issue 优先响应（工作日 48 小时内） |
| 🛠️ 支持者 | ¥500 / ¥100 | 上一档 + 需求进 roadmap 的优先评估 + 私人部署答疑群 |
| 🏢 企业档 | ¥2000+ / ¥300+ | 上一档 + README 与赞助页展示 Logo（可选）+ 部署/迁移协助一次 |

> 金额不是门槛：**先用得上、再决定要不要给钱**。项目本身不需要赞助才能跑起来，也不会做「赞助才解锁功能」这种事。

## 鸣谢墙

赞助者名单（按时间倒序，想匿名/改名/去名随时说）：

| 赞助者 | 档位 | 时间 | 留言 |
|---|---|---|---|
| *虚位以待* | — | — | 第一位赞助者会出现在这里 |

代码与文档的贡献者名单见 [README 的鸣谢一节](../README.md#鸣谢)。

## 常见问题

**Q：赞助后能要求开放「批量私信 / 批量群发 / 批量加群 / 强拉进群 / 吵群 / 拟人发言」这类功能吗？**

不能，而且这跟钱无关。这批能力是批量骚扰与「水军」工具的典型形态（错峰、拟人话术就是为了规避平台风控），后果是号池成批被封、运营方承担法律风险。项目在 [规划.md](../规划.md) 里把它们明确写在「不做这些」清单里，README 也照实写清楚。赞助**不会**改变这条边界。

**Q：那赞助买的是什么？**

买的是「这套已经在用的东西继续被维护」：跟进 Telegram 变更、修 bug、把运维和界面做扎实、文档和测试补齐。

**Q：能开发票吗？**

企业档可以开（需要提供开票信息与邮箱）；个人档一般不开，可提供收款截图与感谢信。

**Q：可以指定用途吗？**

可以备注倾向（例如「只用于服务器」或「只用于 AI 额度」），本页会按备注记录并在季度收支里说明。

**Q：能退款吗？**

一个月内、且没有享受过档位权益的，直接说，原路退回。

**Q：赞助与商业授权的关系？**

本项目当前**尚未选定开源协议**（见 [README 的许可证一节](../README.md#许可证)）。想在自己的服务器上部署使用，直接照 README 部署即可，不需要额外授权；想把代码二次分发或商用，请先联系作者。

## 联系

- 赞助相关：在 [Issues](https://github.com/cafinxnull/telegram-cloud-control/issues) 开一条带 `sponsor` 标签的（或直接邮件联系仓库作者）
- 安全问题：不要开公开 Issue，按 [README 的安全一节](../README.md#安全) 私下报
