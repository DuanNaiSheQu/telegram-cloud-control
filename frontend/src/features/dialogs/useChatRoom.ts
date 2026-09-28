/**
 * 聊天室状态：当前会话的消息流、无限上翻、会话内搜索、发送（双通道二分支）、
 * AI 草稿（503 引导文案）、未读分隔线、WebSocket 实时追加。
 *
 * 消息流规则：
 *  - 按时间正序渲染；`before` 往前翻更早的消息；
 *  - WS 只追加当前 dialog 的消息（按 id 去重），其它会话的推送不会混进来；
 *  - 打开会话时若有未读数，在「第一条未读」前面插入分隔线，标记已读后消失。
 */
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import dayjs from 'dayjs';
import { api, ApiError } from '../../api/client';
import { dialogApi, messageApi } from '../../api/endpoints';
import type { DialogOut, MessageListResponse, MessageOut } from '../../api/types';
import { useWebSocket } from '../../hooks/useWebSocket';
import { toast } from '../../utils/feedback';
import { IM_PAGE_SIZE, type ImListItem } from './types';

interface MessageParams {
  limit: number;
  before?: string;
  q?: string;
}

/**
 * 会话内消息查询。api/endpoints 的 dialogApi.messages 只透传 limit/before（q 不在其类型里），
 * 这里直接用 client 的 api.get 把 q= 带过去（GET /api/dialogs/{id}/messages?q=…）。
 */
function fetchMessages(dialogId: string, params: MessageParams, silent = true): Promise<MessageListResponse> {
  return api.get<MessageListResponse>(`/api/dialogs/${dialogId}/messages`, { ...params }, { silent });
}

export interface UnreadMarker {
  /** 第一条未读消息的 id，分隔线渲染在它前面 */
  firstId: string;
  count: number;
}

function dateLabel(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = dayjs(iso);
  if (!d.isValid()) return '';
  const now = dayjs();
  if (d.isSame(now, 'day')) return '今天';
  if (d.isSame(now.subtract(1, 'day'), 'day')) return '昨天';
  if (d.isSame(now, 'year')) return d.format('M月D日');
  return d.format('YYYY年M月D日');
}

function mergeMessages(prev: MessageOut[], next: MessageOut[]): MessageOut[] {
  const seen = new Set(prev.map((item) => item.id));
  const extra = next.filter((item) => !seen.has(item.id));
  if (!extra.length) return prev;
  const merged = [...prev, ...extra];
  merged.sort((a, b) => dayjs(a.created_at ?? 0).valueOf() - dayjs(b.created_at ?? 0).valueOf());
  return merged;
}

export interface ChatRoomState {
  dialog: DialogOut | null;
  messages: MessageOut[];
  items: ImListItem[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  wsStatus: 'connecting' | 'open' | 'closed';
  /** 会话内搜索 */
  searchMode: boolean;
  searchTotal: number;
  searchQ: string;
  setSearchQ: (q: string) => void;
  clearSearch: () => void;
  /** 未读分隔线 */
  unreadMarker: UnreadMarker | null;
  markRead: () => Promise<void>;
  /** 同步历史消息（用户号通道） */
  syncHistory: () => Promise<void>;
  /** 输入与发送 */
  text: string;
  setText: (v: string) => void;
  instruction: string;
  setInstruction: (v: string) => void;
  draftId: string | null;
  drafting: boolean;
  aiGuide: string | null;
  dismissAiGuide: () => void;
  generateDraft: () => Promise<void>;
  sendError: string | null;
  dismissSendError: () => void;
  sending: boolean;
  send: () => Promise<void>;
  resend: (message: MessageOut) => Promise<void>;
  discardDraft: () => Promise<void>;
  /** 上翻与滚动 */
  loadEarlier: () => void;
  scrollRef: RefObject<HTMLDivElement>;
  scrollToBottom: (smooth?: boolean) => void;
}

export function useChatRoom(
  dialog: DialogOut | null,
  onListPatch: (patch: Partial<DialogOut>) => void,
): ChatRoomState {
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [searchQ, setSearchQState] = useState('');
  const [searchTotal, setSearchTotal] = useState(0);

  const [unreadMarker, setUnreadMarker] = useState<UnreadMarker | null>(null);

  const [text, setText] = useState('');
  const [instruction, setInstruction] = useState('');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [aiGuide, setAiGuide] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const dialogIdRef = useRef<string | null>(null);
  const unreadAtOpenRef = useRef(0);
  const loadedOnceRef = useRef(false);
  const seqRef = useRef(0);
  const onListPatchRef = useRef(onListPatch);
  onListPatchRef.current = onListPatch;

  const { status: wsStatus, subscribe, unsubscribe, onEvent } = useWebSocket(true);

  const searchMode = Boolean(searchQ.trim());

  const scrollToBottom = useCallback((smooth = false) => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  // ---------- 加载最新一页（含会话内搜索 q=） ----------

  const loadLatest = useCallback(
    async (q?: string) => {
      if (!dialog) return;
      const seq = (seqRef.current += 1);
      setLoading(true);
      try {
        const params: MessageParams = { limit: IM_PAGE_SIZE };
        if (q?.trim()) params.q = q.trim();
        const res = await fetchMessages(dialog.id, params);
        if (seq !== seqRef.current) return;
        setMessages(res.items);
        setHasMore(Boolean(res.has_more));
        setSearchTotal(res.total);
        setError(null);
        loadedOnceRef.current = true;
        if (q?.trim()) return; // 搜索模式不处理未读分隔线
        if (unreadAtOpenRef.current > 0) {
          const index = Math.max(res.items.length - unreadAtOpenRef.current, 0);
          const first = res.items[index];
          setUnreadMarker(first ? { firstId: first.id, count: unreadAtOpenRef.current } : null);
        }
        requestAnimationFrame(() => scrollToBottom());
      } catch (err) {
        if (seq !== seqRef.current) return;
        setError((err as Error)?.message || '消息加载失败');
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    },
    [dialog, scrollToBottom],
  );

  // ---------- 切换会话 / 进入搜索 ----------

  useEffect(() => {
    dialogIdRef.current = dialog?.id ?? null;
    if (!dialog) return;
    unreadAtOpenRef.current = dialog.unread_count;
    setMessages([]);
    setHasMore(false);
    setError(null);
    setUnreadMarker(null);
    setText('');
    setInstruction('');
    setDraftId(null);
    setAiGuide(null);
    setSendError(null);
    setSearchQState('');
    void loadLatest();
    // 打开即视为已读（服务端清零 + 列表角标消失）；未读分隔线保留到用户点「标记已读」
    if (dialog.unread_count > 0) {
      dialogApi
        .read(dialog.id)
        .then(() => onListPatchRef.current({ unread_count: 0 }))
        .catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dialog?.id]);

  const setSearchQ = useCallback(
    (q: string) => {
      setSearchQState(q);
      if (dialog && q.trim()) {
        setMessages([]);
        setError(null);
        void loadLatest(q);
      } else if (dialog) {
        setMessages([]);
        setError(null);
        void loadLatest();
      }
    },
    [dialog, loadLatest],
  );

  const clearSearch = useCallback(() => setSearchQ(''), [setSearchQ]);

  // ---------- WebSocket：只追加当前会话，多会话不串 ----------

  useEffect(() => {
    const id = dialog?.id ?? null;
    if (!id) return;
    subscribe([id]);
    return () => unsubscribe([id]);
  }, [dialog?.id, subscribe, unsubscribe]);

  useEffect(() => {
    if (!dialog) return;
    const off = onEvent((event) => {
      if (event.kind !== 'message' || event.dialog_id !== dialog.id) return;
      const incoming = event.message;
      setMessages((prev) => (prev.some((item) => item.id === incoming.id) ? prev : [...prev, incoming]));
      // 当前会话的新消息视为已读：列表里未读归零，预览跟着走
      onListPatchRef.current({
        unread_count: 0,
        last_message_at: incoming.created_at ?? undefined,
        last_message_preview: incoming.body || (incoming.has_media ? '[媒体]' : undefined),
      });
      requestAnimationFrame(() => scrollToBottom(true));
    });
    return off;
  }, [dialog, onEvent, scrollToBottom]);

  // 断线重连成功后静默补拉一次，避免漏掉断开期间的消息
  useEffect(() => {
    if (wsStatus !== 'open' || !dialog || !loadedOnceRef.current) return;
    if (searchMode) return;
    const seq = (seqRef.current += 1);
    fetchMessages(dialog.id, { limit: IM_PAGE_SIZE })
      .then((res) => {
        if (seq !== seqRef.current) return;
        setMessages((prev) => mergeMessages(prev, res.items));
        setHasMore(Boolean(res.has_more));
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsStatus, dialog?.id]);

  // ---------- 上翻更早 ----------

  const loadEarlier = useCallback(() => {
    if (!dialog || loadingMore) return;
    const earliest = messages[0]?.created_at ?? undefined;
    if (!earliest) return;
    const q = searchMode ? searchQ.trim() : '';
    const prevHeight = scrollRef.current?.scrollHeight ?? 0;
    const seq = (seqRef.current += 1);
    setLoadingMore(true);
    const params: MessageParams = { limit: IM_PAGE_SIZE, before: earliest };
    if (q) params.q = q;
    fetchMessages(dialog.id, params)
      .then((res) => {
        if (seq !== seqRef.current) return;
        setMessages((prev) => mergeMessages(prev, res.items));
        setHasMore(Boolean(res.has_more));
        if (searchMode) setSearchTotal(res.total);
        // 保持视口位置：上翻前记住 scrollHeight，插入后把新增高度滚掉
        requestAnimationFrame(() => {
          const node = scrollRef.current;
          if (node) node.scrollTop = node.scrollHeight - prevHeight;
        });
      })
      .catch(() => undefined)
      .finally(() => {
        if (seq === seqRef.current) setLoadingMore(false);
      });
  }, [dialog, loadingMore, messages, searchMode, searchQ]);

  // ---------- 未读清零 ----------

  const markRead = useCallback(async () => {
    if (!dialog) return;
    try {
      await dialogApi.read(dialog.id);
      setUnreadMarker(null);
      onListPatchRef.current({ unread_count: 0 });
    } catch {
      /* client 已统一提示 */
    }
  }, [dialog]);

  // ---------- 同步历史消息 ----------

  const syncHistory = useCallback(async () => {
    if (!dialog) return;
    try {
      const res = await dialogApi.sync(dialog.id, 50);
      toast.success(res.message || '已提交同步历史消息任务');
    } catch {
      /* client 已统一提示（Bot 通道的中文原因也在这里弹） */
    }
  }, [dialog]);

  // ---------- 发送（用户号排队 / Bot 直发，409/400 中文原因内联展示） ----------

  const send = useCallback(async () => {
    if (!dialog || !text.trim()) return;
    setSending(true);
    setSendError(null);
    try {
      const res = await messageApi.send(dialog.id, text.trim(), draftId);
      setMessages((prev) => (prev.some((item) => item.id === res.message.id) ? prev : [...prev, res.message]));
      setText('');
      setDraftId(null);
      setUnreadMarker(null);
      onListPatchRef.current({
        unread_count: 0,
        last_message_at: res.message.created_at ?? undefined,
        last_message_preview: res.message.body,
      });
      requestAnimationFrame(() => scrollToBottom(true));
      if (res.status === 'pending') {
        toast.info(res.detail || '已排队，等待 Worker 发出');
      } else {
        toast.success(res.detail || '已发送');
      }
    } catch (err) {
      const apiError = err as ApiError;
      // 二分支提示：用户号非 healthy → 409；Bot 直发失败 → 409/400，detail 都是中文原因
      setSendError(apiError.friendlyMessage || '发送失败，请稍后重试');
    } finally {
      setSending(false);
    }
  }, [dialog, text, draftId, scrollToBottom]);

  /** 失败消息重发：重新走一次发送接口（生成一条新的 outgoing 消息） */
  const resend = useCallback(
    async (message: MessageOut) => {
      if (!dialog || !message.body.trim()) return;
      try {
        await messageApi.send(dialog.id, message.body.trim());
        toast.success('已重新提交发送');
      } catch (err) {
        const apiError = err as ApiError;
        setSendError(apiError.friendlyMessage || '重发失败，请稍后重试');
      }
    },
    [dialog],
  );

  // ---------- AI 草稿（503 → 中文引导文案，不是报错弹窗） ----------

  const generateDraft = useCallback(async () => {
    if (!dialog) return;
    setDrafting(true);
    setAiGuide(null);
    try {
      const draft = await dialogApi.draft(dialog.id, instruction.trim(), { silent: true });
      setText(draft.body);
      setDraftId(draft.id);
      toast.info('AI 草稿已生成，点「发送」才会发出');
    } catch (err) {
      const apiError = err as ApiError;
      if (apiError.status === 503) {
        setAiGuide(
          'AI 草稿未启用：请在 backend/.env 中配置 AI_ENABLED=true、AI_API_KEY、AI_BASE_URL、AI_MODEL 后重启后端服务。'
          + `（后端返回：${apiError.detail || apiError.message}）`,
        );
      } else {
        setAiGuide(`AI 草稿生成失败：${apiError.friendlyMessage}`);
      }
    } finally {
      setDrafting(false);
    }
  }, [dialog, instruction]);

  const discardDraft = useCallback(async () => {
    const id = draftId;
    setDraftId(null);
    setText('');
    if (!id) return;
    try {
      await dialogApi.discardDraft(id);
      toast.success('已丢弃草稿');
    } catch {
      /* client 已统一提示 */
    }
  }, [draftId]);

  // ---------- 渲染分组（日期分隔 + 未读分隔 + 气泡） ----------

  const items = useMemo<ImListItem[]>(() => {
    const list: ImListItem[] = [];
    let lastDay = '';
    messages.forEach((message) => {
      if (unreadMarker && message.id === unreadMarker.firstId) {
        list.push({ key: `unread-${message.id}`, kind: 'unread', count: unreadMarker.count });
      }
      const day = dateLabel(message.created_at);
      if (day && day !== lastDay) {
        lastDay = day;
        list.push({ key: `date-${day}-${message.id}`, kind: 'date', text: day });
      }
      list.push({ key: message.id, kind: 'message', message });
    });
    return list;
  }, [messages, unreadMarker]);

  return {
    dialog,
    messages,
    items,
    hasMore,
    loading,
    loadingMore,
    error,
    wsStatus,
    searchMode,
    searchTotal,
    searchQ,
    setSearchQ,
    clearSearch,
    unreadMarker,
    markRead,
    syncHistory,
    text,
    setText,
    instruction,
    setInstruction,
    draftId,
    drafting,
    aiGuide,
    dismissAiGuide: () => setAiGuide(null),
    sendError,
    dismissSendError: () => setSendError(null),
    sending,
    send,
    resend,
    generateDraft,
    discardDraft,
    loadEarlier,
    scrollRef,
    scrollToBottom,
  };
}

export type { ChatRoomState as ChatRoom };
