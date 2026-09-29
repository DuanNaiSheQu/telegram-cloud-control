/**
 * 关于 · 赞助 · 声明
 *
 * 为什么要有这个弹窗：这套系统会操作真实账号，使用者必须清楚两件事 ——
 * ① 它是开源项目、源码在哪、什么许可；② 用它有风险、责任在谁。
 * 只在 README 里写这些不够：部署者未必翻仓库，但一定会登录控制台。
 *
 * 首次进入自动弹一次（用 localStorage 记住），之后从用户菜单随时可开。
 */
import { GithubOutlined, HeartFilled, SendOutlined, StarFilled } from '@ant-design/icons';
import { Divider, Modal, Space, Tag, Typography } from 'antd';

export const ABOUT_SEEN_KEY = 'tgcc_about_seen';

const SOURCE_URL = 'https://github.com/DuanNaiSheQu/telegram-cloud-control';
const GROUP_URL = 'https://t.me/TGCloudcontrol';
const SPONSOR_URL = 'https://github.com/sponsors/DuanNaiSheQu';
const USDT_ADDR = 'TYozr2b8tV4fikCuQYYvaHRCW555555555';

interface AboutModalProps {
  open: boolean;
  onClose: () => void;
}

export function AboutModal({ open, onClose }: AboutModalProps) {
  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={onClose}
      okText="我已了解"
      cancelButtonProps={{ style: { display: 'none' } }}
      width={640}
      title={
        <Space>
          <StarFilled style={{ color: '#f5a623' }} />
          <span>关于 · 赞助 · 使用声明</span>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        这是一个<strong>开源项目</strong>，可以自由部署到你自己的服务器上使用。
        下面几点建议读一下。
      </Typography.Paragraph>

      <Divider orientation="left" plain style={{ margin: '12px 0' }}>
        开源信息
      </Divider>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <div>
          <GithubOutlined /> 源码仓库：
          <Typography.Link href={SOURCE_URL} target="_blank" rel="noreferrer">
            DuanNaiSheQu/telegram-cloud-control
          </Typography.Link>
          <Tag style={{ marginLeft: 8 }} color="green">
            MIT
          </Tag>
        </div>
        <div>
          <SendOutlined /> 交流群：
          <Typography.Link href={GROUP_URL} target="_blank" rel="noreferrer">
            @TGCloudcontrol
          </Typography.Link>
        </div>
        <div>
          <HeartFilled style={{ color: '#eb2f96' }} /> 赞助支持：
          <Typography.Link href={SPONSOR_URL} target="_blank" rel="noreferrer">
            GitHub Sponsors
          </Typography.Link>
          <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
            或 USDT(TRC20)：{USDT_ADDR}
          </Typography.Text>
        </div>
      </Space>

      <Divider orientation="left" plain style={{ margin: '16px 0 12px' }}>
        赞助商
      </Divider>
      <Space size={24} wrap align="center" style={{ paddingLeft: 2 }}>
        <a href="https://cafinx.com" target="_blank" rel="noreferrer">
          <img src="/sponsors/cafinx.png" alt="CAFINX 虚拟卡" style={{ height: 30 }} />
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>跨境收付虚拟卡</div>
        </a>
        <a href="https://cafinxsim.com" target="_blank" rel="noreferrer">
          <img src="/sponsors/cafinxsim.png" alt="CAFINXSIM" style={{ height: 30 }} />
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>全球 eSIM 流量卡</div>
        </a>
      </Space>

      <Divider orientation="left" plain style={{ margin: '16px 0 12px' }}>
        ⚠️ 使用声明
      </Divider>
      <Space direction="vertical" size={8} style={{ width: '100%', fontSize: 13 }}>
        <div>
          <strong>使用范围</strong>：本系统仅用于管理<strong>你自己拥有或有权操作</strong>的账号与 Bot。
          请遵守 Telegram 服务条款与所在地区法律。
        </div>
        <div>
          <strong>风险自担</strong>：自动化操作<strong>存在被平台限制或封禁的风险</strong>。
          系统内置了节流与熔断保护，但它<strong>不是免死金牌</strong> ——
          频率上限、活跃时段、动作间隔请按自己的实际情况保守配置，
          <strong>由此产生的任何后果由使用者自行承担</strong>。
        </div>
        <div>
          <strong>数据归属</strong>：账号、会话、消息等全部数据都存放在<strong>你自己的服务器</strong>上，
          不经过任何第三方。
        </div>
        <div>
          <strong>密钥安全</strong>：上线前请更换 <Typography.Text code>POSTGRES_PASSWORD</Typography.Text>、
          <Typography.Text code>SECRET_KEY</Typography.Text>、
          <Typography.Text code>SESSION_ENCRYPTION_KEY</Typography.Text> 三项。
          <strong>密钥一旦有账号登录过就不要再改</strong>，否则已入库的会话将无法解密。
        </div>
        <div>
          <strong>许可与标识</strong>：项目以 MIT 许可开源。请<strong>保留赞助商与出处标识</strong>，
          勿以本项目的衍生版本对外提供商业服务。
        </div>
      </Space>

      <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
        按「我已了解」关闭；之后可从右上角用户菜单再次打开。
      </Typography.Paragraph>
    </Modal>
  );
}

export default AboutModal;
