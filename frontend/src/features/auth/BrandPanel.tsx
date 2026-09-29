/**
 * BrandPanel —— 登录页左侧品牌区（企业 SaaS 叙事栏）。
 *
 * 内容结构：品牌名 + 价值主张 + 四张能力卡 + 底部状态条。
 * 纯 CSS 质感（渐变 + 光晕 + 网格），不引外链图片；颜色全走变量，深浅主题自适应。
 */
import { CheckCircleFilled, StarFilled, GithubOutlined, SendOutlined, HeartFilled } from '@ant-design/icons';

interface Feature {
  title: string;
  desc: string;
}

const FEATURES: Feature[] = [
  { title: '账号矩阵托管', desc: '登录、检测、同步、发送由 Worker 长连接托管' },
  { title: '消息中转', desc: '会话消息实时转发到员工群，员工回复送回原会话' },
  { title: '批量运营', desc: '私信、群发、素材、加退群、吵群与拟人发言按批次执行' },
  { title: '权限与审计', desc: '成员只看到分配给自己的号，谁在什么时候做了什么都有记录' },
];

/** Telegram 纸飞机标记（白描边，用于品牌区与迷你品牌头） */
function LogoPlane({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M21.4 3.2 3.6 10.3c-.8.3-.8 1.4 0 1.7l4.6 1.5 1.8 5.4c.3.8 1.2 1 1.8.4l2.6-2.5 4.6 3.2c.6.4 1.4.1 1.6-.6l3-13.6c.2-.9-.7-1.6-1.6-1.3Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="m9 13 10.3-8.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function BrandPanel() {
  return (
    <section className="login-brand" aria-label="产品介绍">
      <div className="login-brand-glow is-a" aria-hidden />
      <div className="login-brand-glow is-b" aria-hidden />

      <div className="login-brand-top">
        <div className="login-brand-name">
          <span className="login-brand-logo">
            <LogoPlane />
          </span>
          <span className="login-brand-name-text">
            <span className="login-brand-name-main">Telegram 云控</span>
            <span className="login-brand-name-sub">开源 · 可自托管</span>
          </span>
        </div>

        <h1 className="login-brand-title">把账号矩阵、消息中转与批量运营收进一个后台</h1>
        <p className="login-brand-desc">
          值班打开一个页面就能看到：哪些号在线、当前卡在哪条任务、某个群或私聊的最新消息。
          发送走原通道回去，重启页面服务不会把号全部踢下线。
        </p>

        <div className="login-brand-points">
          {FEATURES.map((feature) => (
            <div className="login-brand-point" key={feature.title}>
              <CheckCircleFilled className="login-brand-point-icon" />
              <span>
                <span className="login-brand-point-title">{feature.title}</span>
                <span className="login-brand-point-desc">{feature.desc}</span>
              </span>
            </div>
          ))}
        </div>
      </div>


      {/* 赞助商与开源入口：横排一行 —— 之前纵向堆叠，卡片很宽却只占左半边、右边一大块空白。
          现在左侧赞助商、右侧链接，两端对齐 */}
      <div className="login-brand-sponsors">
        <div className="login-brand-sponsors-main">
          <span className="login-brand-sponsors-label">
            <StarFilled className="login-brand-sponsors-icon" />
            赞助商
          </span>
          <a href="https://cafinx.com" target="_blank" rel="noreferrer" title="CAFINX 虚拟卡 · 跨境收付">
            <img src="/sponsors/cafinx-white.png" alt="CAFINX 虚拟卡" className="login-brand-sponsor-logo" />
          </a>
          <a href="https://cafinxsim.com" target="_blank" rel="noreferrer" title="CAFINXSIM · 全球 eSIM 流量卡">
            <img src="/sponsors/cafinxsim-white.png" alt="CAFINXSIM" className="login-brand-sponsor-logo" />
          </a>
        </div>
        <div className="login-brand-links">
          <a href="https://github.com/DuanNaiSheQu/telegram-cloud-control" target="_blank" rel="noreferrer">
            <GithubOutlined /> 源码
          </a>
          <a href="https://t.me/TGCloudcontrol" target="_blank" rel="noreferrer">
            <SendOutlined /> 交流群
          </a>
          <a href="https://github.com/sponsors/DuanNaiSheQu" target="_blank" rel="noreferrer">
            <HeartFilled /> 赞助
          </a>
        </div>
      </div>
      <div className="login-brand-foot">
        <span className="login-brand-status">
          <span className="login-brand-status-dot" aria-hidden />
          控制台服务运行中
        </span>
        <span>
          开源项目 · 数据留在自己的服务器 · v
          {typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : ''}
        </span>
      </div>
    </section>
  );
}
