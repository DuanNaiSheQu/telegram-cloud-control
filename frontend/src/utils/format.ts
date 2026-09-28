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
