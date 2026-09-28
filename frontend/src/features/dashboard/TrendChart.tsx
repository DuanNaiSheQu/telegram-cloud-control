/**
 * TrendChart —— 工作台「在线趋势」多序列折线图（纯 SVG，无图表库）。
 *
 * 颜色 / 间距 / 字号全部来自 CSS 变量（var(--tg-*)），换皮只改 tokens.ts。
 * 交互：图例点击开关序列、悬浮十字线与数值提示、序列聚合。
 */
import { useMemo, useRef, useState } from 'react';
import type { MetricsTrendSeries } from '../../api/types';
import { formatTime } from '../../utils/format';

interface Props {
  series: MetricsTrendSeries[];
  height?: number;
  /** 无数据时的提示文案 */
  emptyText?: string;
}

/** 序列 key → 图表色 token 序号（online/abnormal/成功/失败 四色，其余轮换） */
const SERIES_COLOR: Record<string, number> = {
  online_accounts: 1,
  abnormal_accounts: 5,
  tasks_succeeded: 2,
  tasks_failed: 5,
};

const colorFor = (key: string, index: number): string => {
  const slot = SERIES_COLOR[key] ?? (index % 6) + 1;
  return `var(--tg-color-chart-${slot})`;
};

/** 合并所有序列的时间轴（按 t 去重排序） */
function mergeTimeline(series: MetricsTrendSeries[]): string[] {
  const set = new Set<string>();
  series.forEach((item) => item.points.forEach((point) => set.add(point.t)));
  return [...set].sort();
}

export default function TrendChart({ series, height = 300, emptyText }: Props) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const visible = useMemo(() => series.filter((item) => !hidden.has(item.key)), [series, hidden]);
  const timeline = useMemo(() => mergeTimeline(visible), [visible]);
  const byKey = useMemo(() => {
    const map = new Map<string, Map<string, number>>();
    visible.forEach((item) => {
      const inner = new Map<string, number>();
      item.points.forEach((point) => inner.set(point.t, point.v));
      map.set(item.key, inner);
    });
    return map;
  }, [visible]);

  const values = useMemo(
    () => visible.flatMap((item) => item.points.map((point) => point.v)),
    [visible],
  );

  const hasData = timeline.length > 0 && values.length > 0;

  // 图区几何（用 var 变量做内边距，避免写死像素）
  const padLeft = 44;
  const padRight = 16;
  const padTop = 12;
  const padBottom = 24;
  const chartWidth = 960;
  const chartHeight = height;
  const innerW = chartWidth - padLeft - padRight;
  const innerH = chartHeight - padTop - padBottom;

  const xAt = (index: number): number =>
    timeline.length <= 1 ? padLeft + innerW / 2 : padLeft + (index / (timeline.length - 1)) * innerW;

  const { minV, maxV } = useMemo(() => {
    if (!values.length) return { minV: 0, maxV: 1 };
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) return { minV: 0, maxV: max + 1 };
    return { minV: min, maxV: max };
  }, [values]);

  const yAt = (value: number): number => {
    const span = maxV - minV || 1;
    return padTop + innerH - ((value - minV) / span) * innerH;
  };

  const ticks = useMemo(() => {
    const count = 4;
    return Array.from({ length: count + 1 }, (_, i) => minV + ((maxV - minV) / count) * i);
  }, [minV, maxV]);

  const pathFor = (key: string): string => {
    const points = byKey.get(key);
    if (!points) return '';
    return timeline
      .map((t, index) => {
        const v = points.get(t);
        if (v === undefined) return '';
        return `${index === 0 ? 'M' : 'L'}${xAt(index).toFixed(1)},${yAt(v).toFixed(1)}`;
      })
      .filter(Boolean)
      .join(' ');
  };

  const onMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * chartWidth;
    if (!timeline.length) return;
    let best = 0;
    let bestDist = Number.POSITIVE_INFINITY;
    timeline.forEach((_, index) => {
      const dist = Math.abs(xAt(index) - x);
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    setHover(best);
  };

  const toggle = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (!hasData) {
    return (
      <div
        className="tg-empty is-compact"
        style={{ minHeight: height - 40, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <span className="tg-empty-desc">{emptyText ?? '后端还没有开始采样，稍后自动出现趋势点'}</span>
      </div>
    );
  }

  const hoverBucket = hover !== null ? timeline[hover] : null;

  return (
    <div ref={wrapRef}>
      <div
        className="tg-flex"
        style={{ flexWrap: 'wrap', gap: 'var(--tg-space-lg)', marginBottom: 'var(--tg-space-md)' }}
      >
        {series.map((item, index) => {
          const isHidden = hidden.has(item.key);
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => toggle(item.key)}
              className="tg-status-badge"
              style={{
                height: 24,
                cursor: 'pointer',
                background: isHidden ? 'var(--tg-color-bg-sunken)' : 'var(--tg-color-bg-card)',
                borderColor: 'var(--tg-color-border-subtle)',
                color: isHidden ? 'var(--tg-color-text-disabled)' : 'var(--tg-color-text-secondary)',
              }}
            >
              <span
                aria-hidden
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: 'var(--tg-radius-pill)',
                  background: colorFor(item.key, index),
                  opacity: isHidden ? 0.4 : 1,
                }}
              />
              {item.label}
              <span className="tg-num" style={{ fontWeight: 'var(--tg-font-weight-semibold)' }}>
                {item.points.length ? item.points[item.points.length - 1].v : 0}
              </span>
            </button>
          );
        })}
      </div>

      <div style={{ overflowX: 'auto' }}>
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          style={{ width: '100%', height: 'auto', minWidth: 560, display: 'block' }}
          role="img"
          aria-label="在线趋势折线图"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          {/* 网格与 Y 轴刻度 */}
          {ticks.map((tick) => {
            const y = yAt(tick);
            return (
              <g key={tick}>
                <line
                  x1={padLeft}
                  x2={chartWidth - padRight}
                  y1={y}
                  y2={y}
                  stroke="var(--tg-color-chart-grid)"
                  strokeWidth={1}
                />
                <text
                  x={padLeft - 8}
                  y={y + 4}
                  textAnchor="end"
                  fontSize="var(--tg-font-size-xs)"
                  fill="var(--tg-color-chart-axis)"
                >
                  {tick}
                </text>
              </g>
            );
          })}

          {/* X 轴时间标签（首 / 中 / 尾） */}
          {[0, Math.floor((timeline.length - 1) / 2), timeline.length - 1]
            .filter((value, index, arr) => arr.indexOf(value) === index)
            .map((index) => (
              <text
                key={index}
                x={xAt(index)}
                y={chartHeight - 6}
                textAnchor={index === 0 ? 'start' : index === timeline.length - 1 ? 'end' : 'middle'}
                fontSize="var(--tg-font-size-xs)"
                fill="var(--tg-color-chart-axis)"
              >
                {formatTime(timeline[index], 'MM-DD HH:mm')}
              </text>
            ))}

          {/* 序列折线 */}
          {visible.map((item, index) => (
            <path
              key={item.key}
              d={pathFor(item.key)}
              fill="none"
              stroke={colorFor(item.key, index)}
              strokeWidth={2}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.9}
            />
          ))}

          {/* 悬浮十字线 + 端点 */}
          {hover !== null ? (
            <g>
              <line
                x1={xAt(hover)}
                x2={xAt(hover)}
                y1={padTop}
                y2={padTop + innerH}
                stroke="var(--tg-color-border-strong)"
                strokeDasharray="4 4"
              />
              {visible.map((item, index) => {
                const value = byKey.get(item.key)?.get(timeline[hover]);
                if (value === undefined) return null;
                return (
                  <circle
                    key={item.key}
                    cx={xAt(hover)}
                    cy={yAt(value)}
                    r={4}
                    fill={colorFor(item.key, index)}
                    stroke="var(--tg-color-bg-card)"
                    strokeWidth={2}
                  />
                );
              })}
            </g>
          ) : null}
        </svg>
      </div>

      {hoverBucket ? (
        <div
          className="tg-muted"
          style={{
            fontSize: 'var(--tg-font-size-sm)',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 'var(--tg-space-lg)',
          }}
        >
          <span>{formatTime(hoverBucket)}</span>
          {visible.map((item) => {
            const value = byKey.get(item.key)?.get(hoverBucket);
            return value === undefined ? null : (
              <span key={item.key}>
                {item.label}：<span className="tg-num">{value}</span>
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
