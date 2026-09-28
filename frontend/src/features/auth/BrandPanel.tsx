/**
 * BrandPanel —— 登录页左侧品牌区（纯 CSS 质感：渐变 + 纹理，不引外链图片）。
 * 颜色/间距/圆角全部走 var(--tg-*)，深浅两套主题自动适配。
 */
import type { CSSProperties } from 'react';
import { CheckCircleFilled } from '@ant-design/icons';

const FEATURES = [
  '账号矩阵：登录 / 检测 / 同步 / 发送全托管',
  'Bot 转发：把会话消息实时推到员工群',
  'Bot 自动回复：按 persona 资料自动应答',
  '员工分配：operator 只能看到自己被分配的号',
] as const;

/** Telegram 纸飞机 logo（渐变底 + 白色描边纸飞机） */
function LogoMark({ size = 56 }: { size?: number }) {
  const box: CSSProperties = {
    width: size,
    height: size,
    borderRadius: 'var(--tg-radius-lg)',
    background: 'var(--tg-color-gradient-from), var(--tg-color-gradient-to)',
    backgroundImage:
      'linear-gradient(135deg, var(--tg-color-gradient-from) 0%, var(--tg-color-gradient-to) 100%)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: 'var(--tg-shadow-lg)',
    color: 'var(--tg-color-on-primary)',
    flexShrink: 0,
  };
  return (
    <div style={box} aria-hidden>
      <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none">
        <path
          d="M21.4 3.2 3.6 10.3c-.8.3-.8 1.4 0 1.7l4.6 1.5 1.8 5.4c.3.8 1.2 1 1.8.4l2.6-2.5 4.6 3.2c.6.4 1.4.1 1.6-.6l3-13.6c.2-.9-.7-1.6-1.6-1.3Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path d="m9 13 10.3-8.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    </div>
  );
}

export default function BrandPanel() {
  const root: CSSProperties = {
    flex: 1,
    minWidth: 0,
    alignSelf: 'stretch',
    position: 'relative',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    padding: 'var(--tg-space-xxxl) var(--tg-space-xxxl) var(--tg-space-huge)',
    background: 'var(--tg-color-gradient-from)',
    backgroundImage:
      'linear-gradient(150deg, var(--tg-color-gradient-from) 0%, var(--tg-color-gradient-to) 55%, var(--tg-color-primary-active) 100%)',
  };
  const glowA: CSSProperties = {
    position: 'absolute',
    width: 520,
    height: 520,
    right: -160,
    top: -160,
    borderRadius: '50%',
    background: 'var(--tg-color-on-primary)',
    opacity: 0.08,
    pointerEvents: 'none',
  };
  const glowB: CSSProperties = {
    position: 'absolute',
    width: 380,
    height: 380,
    left: -120,
    bottom: -140,
    borderRadius: '50%',
    background: 'var(--tg-color-on-primary)',
    opacity: 0.06,
    pointerEvents: 'none',
  };
  const grid: CSSProperties = {
    position: 'absolute',
    inset: 0,
    backgroundImage:
      'linear-gradient(var(--tg-color-on-primary) 1px, transparent 1px), ' +
      'linear-gradient(90deg, var(--tg-color-on-primary) 1px, transparent 1px)',
    backgroundSize: '48px 48px',
    opacity: 0.05,
    pointerEvents: 'none',
  };
  const title: CSSProperties = {
    color: 'var(--tg-color-on-primary)',
    fontSize: 'var(--tg-font-size-title)',
    fontWeight: 'var(--tg-font-weight-bold)',
    letterSpacing: 'var(--tg-font-letter-tight)',
    margin: 0,
  };
  const subtitle: CSSProperties = {
    color: 'var(--tg-color-on-primary)',
    opacity: 0.82,
    fontSize: 'var(--tg-font-size)',
    marginTop: 'var(--tg-space-md)',
    marginBottom: 0,
    lineHeight: 'var(--tg-font-line-loose)',
    maxWidth: 420,
  };
  const list: CSSProperties = {
    listStyle: 'none',
    margin: 'var(--tg-space-huge) 0 0',
    padding: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--tg-space-xl)',
  };
  const item: CSSProperties = {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 'var(--tg-space-lg)',
    color: 'var(--tg-color-on-primary)',
    fontSize: 'var(--tg-font-size)',
    lineHeight: 'var(--tg-font-line-normal)',
  };
  const icon: CSSProperties = { marginTop: 2, fontSize: 16, flexShrink: 0 };
  const footer: CSSProperties = {
    color: 'var(--tg-color-on-primary)',
    opacity: 0.7,
    fontSize: 'var(--tg-font-size-sm)',
    margin: 0,
  };

  return (
    <div style={root}>
      <div style={glowA} />
      <div style={glowB} />
      <div style={grid} />
      <div style={{ position: 'relative' }}>
        <LogoMark />
        <h1 style={title}>Telegram 云控</h1>
        <p style={subtitle}>账号矩阵与 Bot 转发的内部运维控制台，值班、自动回复、权限分配一站式。</p>
        <ul style={list}>
          {FEATURES.map((text) => (
            <li key={text} style={item}>
              <CheckCircleFilled style={icon} />
              <span>{text}</span>
            </li>
          ))}
        </ul>
      </div>
      <p style={footer}>内部系统 · 仅限授权员工使用</p>
    </div>
  );
}
