/**
 * Relay 页面私有类型。
 * /api/relays/links 后端已回填原文上下文字段（origin_*），
 * api/types.ts 的 RelayLinkOut 暂未同步这些字段，这里在本地补齐，不修改 api/**。
 */
import type { RelayLinkOut, UUID } from '../../api/types';

export interface RelayLinkItem extends RelayLinkOut {
  /** 原消息正文（后端截断到 500 字） */
  origin_body?: string | null;
  /** 原消息发送人 */
  origin_sender_name?: string | null;
  /** 原会话标题 */
  origin_dialog_title?: string | null;
  /** 原会话 id（详情抽屉「跳原会话」用） */
  origin_dialog_id?: UUID | null;
  /** 原会话归属账号标签 */
  account_label?: string | null;
  /** 原消息时间（早于转发时间） */
  origin_created_at?: string | null;
}

/** POST /api/relays/test 的响应（后端补齐中，字段名以后端为准） */
export interface RelayTestResponse {
  ok: boolean;
  message: string;
  detail?: string;
  staff_message_id?: number | null;
}

export function botLabel(name?: string | null, username?: string | null): string {
  if (!name) return '—';
  return username ? `${name} (@${username})` : name;
}
