/**
 * TrendSparkline —— 轻量趋势线（纯 SVG，无第三方图表库）。
 *
 * props 契约：
 * ┌──────────────┬───────────────────────────────────────────────────────────┐
 * │ data         │ Array<number | {t?: string; v: number}>  数据点，空数组显示占位 │
 * │ width        │ number  默认 160（同时受容器 100% 宽影响）                  │
 * │ height       │ number  默认 44                                            │
 * │ color        │ string  CSS 颜色/变量，默认 var(--tg-color-primary)         │
 * │ area         │ boolean 是否填充渐变面积，默认 true                          │
 * │ strokeWidth  │ number  默认 2                                             │
 * │ showLastDot  │ boolean 最后一个点画实心圆，默认 true                         │
 * │ showMinMax   │ boolean 是否在两端标注最小/最大值，默认 false                  │
 * │ baseline     │ number  'auto' 最小值为基线（默认）；0 表示从 0 起            │
 * │ formatValue  │ (v:number)=>string  悬浮/标注格式化                          │
 * │ emptyText    │ string  无数据时文案，默认 '暂无趋势'                         │
 * │ label        │ string  无障碍描述                                            │
 * └──────────────┴───────────────────────────────────────────────────────────┘
 * 用法：<TrendSparkline data={points.map(p=>p.v)} color="var(--tg-color-chart-2)" />
 */
import { useId, type CSSProperties } from 'react';

export interface SparkPoint {
  t?: string;
  v: number;
}

export interface TrendSparklineProps {
  data: Array<number | SparkPoint>;
  width?: number;
  height?: number;
  color?: string;
  area?: boolean;
  strokeWidth?: number;
  showLastDot?: boolean;
  showMinMax?: boolean;
  baseline?: number | 'auto';
  formatValue?: (value: number) => string;
  emptyText?: string;
  label?: string;
  className?: string;
  style?: CSSProperties;
}

function toValues(data: Array<number | SparkPoint>): number[] {
  return data
    .map((item) => (typeof item === 'number' ? item : item?.v))
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
}

export function TrendSparkline({
  data,
  width = 160,
  height = 44,
  color = 'var(--tg-color-primary)',
  area = true,
  strokeWidth = 2,
  showLastDot = true,
  showMinMax = false,
  baseline = 'auto',
  formatValue = (value: number) => String(value),
  emptyText = '暂无趋势',
  label,
  className,
  style,
}: TrendSparklineProps) {
  const gradientId = useId().replace(/[:]/g, '');
  const values = toValues(data);

  if (values.length < 2) {
    return (
      <div
        className={['tg-sparkline-empty', className].filter(Boolean).join(' ')}
        style={{ width, height, ...style }}
        role="img"
        aria-label={label ?? emptyText}
      >
        {emptyText}
      </div>
    );
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const floor = baseline === 'auto' ? min : Math.min(baseline, min);
  const span = max - floor || 1;
  const pad = strokeWidth + 1;
  const innerH = height - pad * 2;

  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = pad + innerH - ((value - floor) / span) * innerH;
    return { x, y, value };
  });

  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ');
  const areaPath = `${line} L${width},${height} L0,${height} Z`;
  const last = points[points.length - 1];
  const maxPoint = points.find((p) => p.value === max);
  const minPoint = points.find((p) => p.value === min);

  return (
    <svg
      className={['tg-sparkline', className].filter(Boolean).join(' ')}
      style={style}
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      height={height}
      preserveAspectRatio="none"
      role="img"
      aria-label={label ?? `趋势：${formatValue(min)} → ${formatValue(values[values.length - 1])}`}
    >
      <defs>
        <linearGradient id={`spark-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {area ? <path d={areaPath} fill={`url(#spark-${gradientId})`} stroke="none" /> : null}

      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />

      {showLastDot ? <circle cx={last.x} cy={last.y} r={strokeWidth + 1} fill={color} /> : null}

      {showMinMax && maxPoint ? (
        <circle cx={maxPoint.x} cy={maxPoint.y} r={2} fill={color} opacity={0.75} />
      ) : null}
      {showMinMax && minPoint ? (
        <circle cx={minPoint.x} cy={minPoint.y} r={2} fill={color} opacity={0.45} />
      ) : null}
    </svg>
  );
}

export default TrendSparkline;
