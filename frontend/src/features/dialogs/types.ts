/**
 * 会话收件箱（IM）页面的本地类型与常量。
 * 只放 UI 态相关的类型，业务类型一律引用 api/types.ts。
 */
import type { MessageOut } from '../../api/types';

/** 消息流渲染项：日期分隔 / 未读分隔线 / 消息气泡，三者按序平铺 */
export type ImListItem =
  | { key: string; kind: 'date'; text: string }
  | { key: string; kind: 'unread'; count: number }
  | { key: string; kind: 'message'; message: MessageOut };

/** 左栏宽度拖动范围（px） */
export const IM_LIST_MIN = 260;
export const IM_LIST_MAX = 620;
export const IM_LIST_DEFAULT = 340;

/** 左栏宽度记忆键 */
export const IM_LIST_WIDTH_KEY = 'tgcc_im_list_width';

/** 每个会话一次拉取的消息条数（与后端 limit 上限 500 之内） */
export const IM_PAGE_SIZE = 50;

/** 会话列表一次拉取条数 */
export const DIALOG_PAGE_SIZE = 50;
