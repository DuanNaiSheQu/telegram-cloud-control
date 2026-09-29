/**
 * 关于 · 赞助 · 开源声明
 *
 * 为什么要有这个弹窗：这套系统会操作真实账号，使用者必须清楚三件事 ——
 * ① 它是开源项目、源码在哪、什么许可；② 用它有风险、责任在谁；
 * ③ 哪些用途是被明确禁止的。
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
      okText="我已阅读并了解"
      cancelButtonProps={{ style: { display: 'none' } }}
      width={680}
      title={
        <Space>
          <StarFilled style={{ color: '#f5a623' }} />
          <span>关于 · 赞助 · 开源声明</span>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        本项目为<strong>开源项目</strong>，代码可供学习研究。开源不易，请尊重开发者的劳动成果。
      </Typography.Paragraph>

      <Divider orientation="left" plain style={{ margin: '12px 0' }}>
        项目信息
      </Divider>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <div>
          <GithubOutlined /> 项目仓库：
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
      {/* 两家赞助商居中并列、彼此拉开距离 —— 挨在一起会显得像一个组合 logo */}
      <div className="about-sponsors">
        <a className="about-sponsor" href="https://cafinx.com" target="_blank" rel="noreferrer">
          <img src="/sponsors/cafinx.png" alt="CAFINX 虚拟卡" />
          <span>跨境收付虚拟卡</span>
        </a>
        <a className="about-sponsor" href="https://cafinxsim.com" target="_blank" rel="noreferrer">
          <img src="/sponsors/cafinxsim.png" alt="CAFINXSIM" />
          <span>全球 eSIM 流量卡</span>
        </a>
      </div>

      <Divider orientation="left" plain style={{ margin: '16px 0 12px' }}>
        ⚠️ 重要提醒：请务必合法使用本项目
      </Divider>
      <Space direction="vertical" size={9} style={{ width: '100%', fontSize: 13 }}>
        <div>
          <strong>1. 合法合规</strong>：使用者承诺仅在符合所在国家、地区法律法规，以及 Telegram
          平台用户协议的前提下使用本项目。
        </div>
        <div>
          <strong>2. 禁止用途</strong>：禁止用于非法入侵、批量骚扰、违规群发、未经许可的数据爬取、
          恶意群控以及其他任何违法违规场景。
        </div>
        <div>
          <strong>3. 风险自担</strong>：本软件按「现状」提供，不提供任何明示或暗示担保。
          因使用者违规部署、不当使用而产生的一切风险、责任、损失，均由<strong>使用者本人自行承担</strong>，
          项目作者不承担任何法律及连带责任。
        </div>
        <div>
          <strong>4. 二次分发</strong>：二次修改、分发需遵守对应开源许可协议，
          <strong>保留原项目开源声明与版权信息，不得去除原作者标识</strong>。
        </div>
        <div>
          <strong>5. 平台规则</strong>：严禁用于破坏平台规则、侵犯他人隐私与权益的行为。
          若用于违规用途，请立即停止使用。
        </div>
      </Space>

      <Divider orientation="left" plain style={{ margin: '16px 0 12px' }}>
        💡 部署建议
      </Divider>
      <Space direction="vertical" size={6} style={{ width: '100%', fontSize: 13 }}>
        <div>仅用于个人学习、私人授权环境内测试；</div>
        <div>使用前请充分读懂代码逻辑，评估安全风险；</div>
        <div>
          <strong>请勿直接公网裸奔部署</strong> —— 上线前务必更换三项密钥
          （<Typography.Text code>POSTGRES_PASSWORD</Typography.Text> /
          <Typography.Text code>SECRET_KEY</Typography.Text> /
          <Typography.Text code>SESSION_ENCRYPTION_KEY</Typography.Text>），
          并配置好访问控制；
        </div>
        <div>如发现他人利用本项目进行违法活动，请及时制止或举报。</div>
      </Space>

      <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0, fontSize: 12 }}>
        按「我已阅读并了解」关闭；之后可从右上角用户菜单再次打开。
      </Typography.Paragraph>
    </Modal>
  );
}

export default AboutModal;
