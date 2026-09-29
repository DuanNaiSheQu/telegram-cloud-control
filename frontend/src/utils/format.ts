/** 时间 / 文本格式化。后端时间戳是带时区的 ISO8601（UTC），这里按浏览器本地时区展示。 */
import dayjs from 'dayjs';

export const TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';
export const MINUTE_FORMAT = 'MM-DD HH:mm';

export function formatTime(value?: string | null, format: string = TIME_FORMAT): string {
  if (!value) return '—';
  const d = dayjs(value);
  return d.isValid() ? d.format(format) : String(value);
}

/** 相对时间：3 分钟前 / 2 小时前 */
export function formatFromNow(value?: string | null): string {
  if (!value) return '—';
  const d = dayjs(value);
  return d.isValid() ? d.fromNow() : String(value);
}

/** 心跳是否过期（默认 60 秒） */
export function isHeartbeatStale(value?: string | null, seconds = 60): boolean {
  if (!value) return true;
  const d = dayjs(value);
  if (!d.isValid()) return true;
  return dayjs().diff(d, 'second') > seconds;
}

/** 号龄：天数 → 「x 天 / x 个月 / x 年」 */
export function formatAccountAge(days?: number | null): string {
  if (days === null || days === undefined) return '—';
  if (days < 0) return '—';
  if (days < 30) return `${days} 天`;
  if (days < 365) return `${Math.floor(days / 30)} 个月`;
  const years = days / 365;
  return `${years.toFixed(1)} 年`;
}

export function formatCount(value?: number | null): string {
  return value === null || value === undefined ? '0' : String(value);
}

/** 消息预览：去掉换行，截断 */
export function previewText(text: string | undefined | null, max = 40): string {
  if (!text) return '';
  const flat = text.replace(/\s+/g, ' ').trim();
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/** UUID 短展示 */
export function shortId(id?: string | null, len = 8): string {
  if (!id) return '—';
  return id.length > len ? id.slice(0, len) : id;
}

/** JSON 详情展示 */
export function stringifyDetail(detail: unknown): string {
  if (detail === null || detail === undefined) return '';
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
}

/** 字节数 */
export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

/** 千分位数字：12345 → 12,345 */
export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('zh-Hans');
}

/** 紧凑数字：12345 → 1.2万（看板卡片用） */
export function formatCompact(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs < 10_000) return formatNumber(value);
  if (abs < 100_000_000) return `${(value / 10_000).toFixed(abs < 100_000 ? 1 : 0)}万`;
  return `${(value / 100_000_000).toFixed(1)}亿`;
}

/** 百分比：0.8123 → 81.2% */
export function formatPercent(value?: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

/** 环比：正数带 +，0 视为持平 */
export function formatDelta(value?: number | null, suffix = '%'): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const sign = value > 0 ? '+' : '';
  return `${sign}${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;
}

/** 秒 → 1 天 2 小时 / 3 分 20 秒 */
export function formatDuration(seconds?: number | null): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds) || seconds < 0) return '—';
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const rest = Math.round(seconds % 60);
    return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest ? `${hours} 小时 ${rest} 分` : `${hours} 小时`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days} 天 ${restHours} 小时` : `${days} 天`;
}

/** 智能时间：今天 14:03 / 昨天 14:03 / 09-28 14:03 / 2025-09-28 14:03 */
export function formatSmartTime(value?: string | null): string {
  if (!value) return '—';
  const d = dayjs(value);
  if (!d.isValid()) return String(value);
  const now = dayjs();
  if (d.isSame(now, 'day')) return `今天 ${d.format('HH:mm')}`;
  if (d.isSame(now.subtract(1, 'day'), 'day')) return `昨天 ${d.format('HH:mm')}`;
  if (d.isSame(now, 'year')) return d.format('MM-DD HH:mm');
  return d.format('YYYY-MM-DD HH:mm');
}

/** 中间省略：8613800000000 → 8613…0000（长 ID / 长手机号） */
export function truncateMiddle(text?: string | null, head = 6, tail = 4): string {
  if (!text) return '—';
  if (text.length <= head + tail + 1) return text;
  return `${text.slice(0, head)}…${text.slice(-tail)}`;
}

/** 数值变化方向，配合 StatCard 的 delta 使用 */
export function deltaDirection(value: number): 'up' | 'down' | 'flat' {
  if (value > 0) return 'up';
  if (value < 0) return 'down';
  return 'flat';
}

