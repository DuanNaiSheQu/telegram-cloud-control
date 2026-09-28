/**
 * StatCard —— 看板统计卡（数字 + 环比 + 图标 + 状态色 + 迷你趋势）。
 *
 * props 契约：
 * ┌────────────┬────────────────────────────────────────────────────────────────┐
 * │ title      │ ReactNode  指标名（如「在线账号」）                              │
 * │ value      │ ReactNode  大数字（number 会自动千分位；也可传 <CountUp/> 之类）   │
 * │ unit       │ ReactNode  单位（台 / % / 条）                                   │
 * │ icon       │ ReactNode  右上角图标                                            │
 * │ tone       │ 'primary'|'success'|'warning'|'danger'|'info'|'neutral'           │
 * │            │ 默认 'neutral'；决定图标底色                                     │
 * │ delta      │ { value: number; suffix?: string; label?: string;               │
 * │            │   goodWhen?: 'up'|'down'|'none'; formatter?: (v)=>string }       │
 * │            │ 环比：正数显示 +，颜色按 goodWhen 判定好坏                        │
 * │ trend      │ Array<number|{v:number}>  迷你趋势线数据（为空则不画）             │
 * │ trendColor │ string  趋势线颜色，默认跟随 tone                                 │
 * │ hint       │ ReactNode  底部左侧补充说明                                      │
 * │ footer     │ ReactNode  底部自定义（给了就不渲染 hint）                        │
 * │ loading    │ boolean    骨架态                                                │
 * │ onClick    │ () => void 可点击卡片（整卡 hover 抬升 + 键盘可聚焦）              │
 * │ className / style                                                │
 * └────────────┴────────────────────────────────────────────────────────────────┘
 * 用法：
 *   <StatCard title="异常账号" value={d.abnormal_accounts} tone="danger"
 *             icon={<WarningOutlined/>} delta={{ value: 12, suffix:'%', goodWhen:'down' }}
 *             trend={[3,5,4,7,6,9]} onClick={()=>nav('/accounts?status=needs_code')} />
 */
import type { CSSProperties, ReactNode } from 'react';
import { formatDelta } from '../utils/format';
import TrendSparkline from './TrendSparkline';
import type { Tone } from '../constants';

export interface StatDelta {
  value: number;
  suffix?: string;
  label?: string;
  /** 上升是好还是坏；'none' 表示中性（不着色） */
  goodWhen?: 'up' | 'down' | 'none';
  formatter?: (value: number) => string;
}

export interface StatCardProps {
  title: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  delta?: StatDelta;
  trend?: Array<number | { v: number }>;
  trendColor?: string;
  hint?: ReactNode;
  footer?: ReactNode;
  loading?: boolean;
  onClick?: () => void;
  className?: string;
  style?: CSSProperties;
}

const TONE_COLOR: Record<Tone, string> = {
  primary: 'var(--tg-color-chart-1)',
  success: 'var(--tg-color-chart-2)',
  warning: 'var(--tg-color-chart-3)',
  danger: 'var(--tg-color-chart-5)',
  info: 'var(--tg-color-chart-6)',
  neutral: 'var(--tg-color-neutral)',
};

function deltaClass(delta: StatDelta): string {
  const goodWhen = delta.goodWhen ?? 'none';
  if (goodWhen === 'none' || delta.value === 0) return 'is-flat';
  const isGood = goodWhen === 'up' ? delta.value > 0 : delta.value < 0;
  return isGood ? 'is-good' : 'is-bad';
}

export function StatCard({
  title,
  value,
  unit,
  icon,
  tone = 'neutral',
  delta,
  trend,
  trendColor,
  hint,
  footer,
  loading = false,
  onClick,
  className,
  style,
}: StatCardProps) {
  if (loading) {
    return (
      <div className={['tg-stat-card', className].filter(Boolean).join(' ')} style={style} aria-busy="true">
        <div className="tg-skeleton" style={{ gap: 'var(--tg-space-md)' }}>
          <div className="tg-skeleton-block" style={{ width: 72, height: 12, borderRadius: 'var(--tg-radius-sm)' }} />
          <div className="tg-skeleton-block" style={{ width: 96, height: 28, borderRadius: 'var(--tg-radius-md)' }} />
          <div className="tg-skeleton-block" style={{ width: 120, height: 10, borderRadius: 'var(--tg-radius-sm)' }} />
        </div>
      </div>
    );
  }

  const clickable = Boolean(onClick);
  const displayValue = typeof value === 'number' ? value.toLocaleString('zh-CN') : value;

  return (
    <div
      className={['tg-stat-card', clickable ? 'is-clickable' : '', className].filter(Boolean).join(' ')}
      style={style}
      onClick={onClick}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
    >
      <div className="tg-stat-head">
        <span className="tg-stat-title">{title}</span>
        {icon ? <span className={`tg-stat-icon is-${tone}`}>{icon}</span> : null}
      </div>

      <div className="tg-stat-value-row">
        <span className="tg-stat-value tg-num">{displayValue}</span>
        {unit ? <span className="tg-stat-unit">{unit}</span> : null}
        {delta ? (
          <span className={`tg-stat-delta ${deltaClass(delta)}`}>
            {delta.formatter ? delta.formatter(delta.value) : formatDelta(delta.value, delta.suffix ?? '%')}
            {delta.label ? <span className="tg-muted">{delta.label}</span> : null}
          </span>
        ) : null}
      </div>

      {trend && trend.length > 1 ? (
        <div className="tg-stat-spark">
          <TrendSparkline data={trend} color={trendColor ?? TONE_COLOR[tone]} height={40} label={`${String(title)} 趋势`} />
        </div>
      ) : null}

      {footer ? (
        <div className="tg-stat-footer">{footer}</div>
      ) : hint ? (
        <div className="tg-stat-footer">
          <span className="tg-stat-hint">{hint}</span>
        </div>
      ) : null}
    </div>
  );
}

export default StatCard;
