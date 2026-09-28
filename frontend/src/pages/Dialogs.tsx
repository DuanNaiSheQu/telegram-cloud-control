import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import {
  CloudSyncOutlined,
  FileImageOutlined,
  ReloadOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { accountApi, asList, botApi, dialogApi, messageApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { useWebSocket } from '../hooks/useWebSocket';
import { DIALOG_CHANNEL_LABELS, DIALOG_KIND_LABELS } from '../constants';
import { formatFromNow, formatTime, previewText } from '../utils/format';
import { notifyError, notifyInfo, notifySuccess } from '../utils/feedback';
import { MessageStatusTag } from '../components/TaskStatusTag';
import type { DialogListQuery, DialogOut, MessageOut } from '../api/types';

const PAGE_SIZE_STEP = 20;

function sortAscending(list: MessageOut[]): MessageOut[] {
  return [...list].sort(
    (a, b) => dayjs(a.created_at ?? 0).valueOf() - dayjs(b.created_at ?? 0).valueOf(),
  );
}

export default function Dialogs() {
  const [filters, setFilters] = useState<DialogListQuery>({ page: 1, page_size: PAGE_SIZE_STEP });
  const dialogList = useAsyncData(() => dialogApi.list(filters), [JSON.stringify(filters)]);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);
  const bots = useAsyncData(() => botApi.list(), []);

  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeDialog, setActiveDialog] = useState<DialogOut | null>(null);
  const [messages, setMessages] = useState<MessageOut[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [text, setText] = useState('');
  const [instruction, setInstruction] = useState('');
  const [draftId, setDraftId] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);

  const activeIdRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const setDialogListData = dialogList.setData;

  const { status: wsStatus, subscribe, unsubscribe, onEvent } = useWebSocket(true);

  const dialogs = dialogList.data?.items ?? [];

  const scrollToBottom = useCallback((smooth = false) => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  /** 列表里的未读数/预览本地更新（WS 推送时不用整表刷新） */
  const patchDialogInList = useCallback(
    (dialogId: string, patch: Partial<DialogOut>) => {
      setDialogListData((prev) =>
        prev
          ? { ...prev, items: prev.items.map((item) => (item.id === dialogId ? { ...item, ...patch } : item)) }
          : prev,
      );
    },
    [setDialogListData],
  );

  /** WS：只推当前打开的会话 */
  useEffect(() => {
    const off = onEvent((event) => {
      if (event.kind !== 'message') return;
      const incoming = event.message;
      const isActive = event.dialog_id === activeIdRef.current;
      if (isActive) {
        setMessages((prev) => (prev.some((item) => item.id === incoming.id) ? prev : [...prev, incoming]));
        requestAnimationFrame(() => scrollToBottom(true));
      }
      const patch: Partial<DialogOut> = {};
      if (incoming.body) patch.last_message_preview = incoming.body;
      else if (incoming.has_media) patch.last_message_preview = '[媒体]';
      if (incoming.created_at) patch.last_message_at = incoming.created_at;
      if (isActive) {
        patch.unread_count = 0;
      } else if (incoming.direction === 'incoming') {
        // 没打开的会话：本地把未读数加上去
        setDialogListData((prev) =>
          prev
            ? {
                ...prev,
                items: prev.items.map((item) =>
                  item.id === event.dialog_id ? { ...item, unread_count: item.unread_count + 1 } : item,
                ),
              }
            : prev,
        );
      }
      if (Object.keys(patch).length) patchDialogInList(event.dialog_id, patch);
    });
    return off;
  }, [onEvent, patchDialogInList, scrollToBottom, setDialogListData]);

  /** 打开会话时订阅它的推送 */
  useEffect(() => {
    activeIdRef.current = activeId;
    if (!activeId) return;
    subscribe([activeId]);
    return () => unsubscribe([activeId]);
  }, [activeId, subscribe, unsubscribe]);

  const openDialog = async (dialog: DialogOut) => {
    setActiveId(dialog.id);
    setActiveDialog(dialog);
    setMessages([]);
    setHasMore(false);
    setText('');
    setDraftId(null);
    setMessagesLoading(true);
    try {
      const res = await dialogApi.messages(dialog.id, { limit: 50 });
      setMessages(sortAscending(asList<MessageOut>(res.items)));
      setHasMore(Boolean(res.has_more));
      if (res.dialog) setActiveDialog(res.dialog);
      requestAnimationFrame(() => scrollToBottom());
      if (dialog.unread_count > 0) {
        try {
          await dialogApi.read(dialog.id);
          patchDialogInList(dialog.id, { unread_count: 0 });
        } catch {
          /* client 已统一提示 */
        }
      }
    } catch {
      /* client 已统一提示 */
    } finally {
      setMessagesLoading(false);
    }
  };

  const reloadMessages = async () => {
    if (!activeId) return;
    setMessagesLoading(true);
    try {
      const res = await dialogApi.messages(activeId, { limit: 50 });
      setMessages(sortAscending(asList<MessageOut>(res.items)));
      setHasMore(Boolean(res.has_more));
      requestAnimationFrame(() => scrollToBottom());
    } catch {
      /* client 已统一提示 */
    } finally {
      setMessagesLoading(false);
    }
  };

  const loadEarlier = async () => {
    if (!activeId || !messages.length) return;
    const earliest = messages[0]?.created_at ?? undefined;
    setMessagesLoading(true);
    try {
      const res = await dialogApi.messages(activeId, { limit: 50, before: earliest });
      setMessages((prev) => sortAscending([...asList<MessageOut>(res.items), ...prev]));
      setHasMore(Boolean(res.has_more));
    } catch {
      /* client 已统一提示 */
    } finally {
      setMessagesLoading(false);
    }
  };

  const handleSync = async () => {
    if (!activeId) return;
    setSyncing(true);
    try {
      const res = await dialogApi.sync(activeId, 50);
      notifySuccess(res.message || '已提交同步历史消息任务，稍后点「刷新」查看');
      void dialogList.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setSyncing(false);
    }
  };

  const handleDraft = async () => {
    if (!activeId) return;
    setDrafting(true);
    try {
      const draft = await dialogApi.draft(activeId, instruction.trim());
      setText(draft.body);
      setDraftId(draft.id);
      notifyInfo('草稿已生成，点发送才发出');
    } catch {
      /* client 已统一提示 */
    } finally {
      setDrafting(false);
    }
  };

  const handleDiscardDraft = async () => {
    if (!draftId) {
      setText('');
      return;
    }
    try {
      await dialogApi.discardDraft(draftId);
      notifySuccess('草稿已丢弃');
    } catch {
      /* client 已统一提示 */
    } finally {
      setDraftId(null);
      setText('');
    }
  };

  const handleSend = async () => {
    if (!activeId || !text.trim()) {
      notifyError('请输入要发送的内容');
      return;
    }
    setSending(true);
    try {
      const res = await messageApi.send(activeId, text.trim(), draftId);
      setMessages((prev) =>
        prev.some((item) => item.id === res.message.id) ? prev : [...prev, res.message],
      );
      setText('');
      setDraftId(null);
      patchDialogInList(activeId, {
        last_message_preview: res.message.body,
        last_message_at: res.message.created_at ?? undefined,
      });
      requestAnimationFrame(() => scrollToBottom(true));
      if (res.status === 'pending') {
        notifyInfo(res.detail || '已提交，等待员工确认发送');
      } else {
        notifySuccess(res.detail || '已发送');
      }
    } catch {
      /* client 已统一提示 */
    } finally {
      setSending(false);
    }
  };

  const filtersNode = useMemo(
    () => (
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space wrap size={8}>
          <Select
            allowClear
            size="small"
            placeholder="通道"
            style={{ width: 110 }}
            value={filters.channel || undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, channel: value ?? '', page: 1 }))}
            options={[
              { value: 'user_account', label: '用户号' },
              { value: 'bot', label: 'Bot' },
            ]}
          />
          <Select
            allowClear
            size="small"
            placeholder="类型"
            style={{ width: 100 }}
            value={filters.kind || undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, kind: value ?? '', page: 1 }))}
            options={[
              { value: 'group', label: '群聊' },
              { value: 'private', label: '私信' },
            ]}
          />
          <span style={{ fontSize: 12 }}>
            只看未读{' '}
            <Switch
              size="small"
              checked={Boolean(filters.only_unread)}
              onChange={(checked) => setFilters((prev) => ({ ...prev, only_unread: checked, page: 1 }))}
            />
          </span>
        </Space>
        <Space wrap size={8}>
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            size="small"
            placeholder="账号"
            style={{ width: 150 }}
            value={filters.account_id ?? undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, account_id: value ?? null, page: 1 }))}
            options={(accounts.data?.items ?? []).map((item) => ({
              value: item.id,
              label: item.phone_masked,
            }))}
          />
          <Select
            allowClear
            size="small"
            placeholder="Bot"
            style={{ width: 150 }}
            value={filters.bot_id ?? undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, bot_id: value ?? null, page: 1 }))}
            options={(bots.data ?? []).map((bot) => ({
              value: bot.id,
              label: bot.bot_username ? `@${bot.bot_username}` : bot.name,
            }))}
          />
        </Space>
        <Input.Search
          allowClear
          size="small"
          placeholder="会话标题 / 关键词"
          onSearch={(value) => setFilters((prev) => ({ ...prev, keyword: value.trim(), page: 1 }))}
        />
      </Space>
    ),
    [filters, accounts.data, bots.data],
  );

  return (
    <div className="dialog-page">
      <div className="dialog-list-pane">
        <div className="dialog-list-filters">
          {filtersNode}
          <Space size={8} style={{ marginTop: 8 }}>
            <Button
              size="small"
              icon={<ReloadOutlined />}
              loading={dialogList.loading}
              onClick={() => void dialogList.reload()}
            >
              刷新
            </Button>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              共 {dialogList.data?.total ?? 0} 个会话
            </Typography.Text>
          </Space>
        </div>

        <div className="dialog-list-scroll">
          {dialogList.loading && !dialogs.length ? (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <Spin />
            </div>
          ) : null}
          {!dialogList.loading && !dialogs.length ? (
            <Empty style={{ padding: 24 }} description="没有符合条件的会话" />
          ) : null}
          {dialogs.map((dialog) => (
            <div
              key={dialog.id}
              className={`dialog-item${dialog.id === activeId ? ' active' : ''}`}
              onClick={() => void openDialog(dialog)}
            >
              <div className="dialog-item-main">
                <div className="dialog-item-title">
                  <span className="ellipsis" style={{ maxWidth: 190 }}>
                    {dialog.title || dialog.peer_display || `会话 ${dialog.tg_chat_id}`}
                  </span>
                  <Tag color={dialog.channel === 'bot' ? 'purple' : 'blue'} style={{ marginInlineEnd: 0 }}>
                    {dialog.channel_label || DIALOG_CHANNEL_LABELS[dialog.channel]}
                  </Tag>
                  <Tag style={{ marginInlineEnd: 0 }}>
                    {dialog.kind_label || DIALOG_KIND_LABELS[dialog.kind]}
                  </Tag>
                </div>
                <div className="dialog-item-preview">
                  {previewText(dialog.last_message_preview, 34) || '暂无消息'}
                </div>
                <div className="dialog-item-preview" style={{ marginTop: 2 }}>
                  {dialog.account_label || (dialog.bot_label ? `@${dialog.bot_label}` : '—')}
                  {dialog.member_count ? ` · ${dialog.member_count} 人` : ''}
                </div>
              </div>
              <div className="dialog-item-meta">
                <span>{dialog.last_message_at ? formatFromNow(dialog.last_message_at) : ''}</span>
                {dialog.unread_count > 0 ? <Badge count={dialog.unread_count} /> : null}
              </div>
            </div>
          ))}
        </div>

        <div className="dialog-list-footer">
          <Button
            size="small"
            disabled={dialogs.length >= (dialogList.data?.total ?? 0)}
            onClick={() =>
              setFilters((prev) => ({ ...prev, page_size: (prev.page_size ?? PAGE_SIZE_STEP) + PAGE_SIZE_STEP }))
            }
          >
            加载更多
          </Button>
        </div>
      </div>

      <div className="chat-pane">
        {activeDialog ? (
          <>
            <div className="chat-header">
              <Space direction="vertical" size={0} style={{ minWidth: 0 }}>
                <Space size={6}>
                  <Typography.Text strong className="ellipsis" style={{ maxWidth: 320 }}>
                    {activeDialog.title || activeDialog.peer_display || `会话 ${activeDialog.tg_chat_id}`}
                  </Typography.Text>
                  <Tag color={activeDialog.channel === 'bot' ? 'purple' : 'blue'}>
                    {activeDialog.channel_label || DIALOG_CHANNEL_LABELS[activeDialog.channel]}
                  </Tag>
                  <Tag>{activeDialog.kind_label || DIALOG_KIND_LABELS[activeDialog.kind]}</Tag>
                </Space>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {activeDialog.account_label ? `账号 ${activeDialog.account_label}` : ''}
                  {activeDialog.bot_label ? `Bot @${activeDialog.bot_label}` : ''}
                  {` · chat_id ${activeDialog.tg_chat_id}`}
                  {activeDialog.username ? ` · @${activeDialog.username}` : ''}
                </Typography.Text>
              </Space>
              <Space>
                <Tooltip title={wsStatus === 'open' ? '新消息会实时追加' : '实时连接断开，正在重连'}>
                  <Badge
                    status={wsStatus === 'open' ? 'success' : wsStatus === 'connecting' ? 'processing' : 'error'}
                  />
                </Tooltip>
                <Button size="small" icon={<ReloadOutlined />} onClick={() => void reloadMessages()}>
                  刷新
                </Button>
                <Button size="small" icon={<CloudSyncOutlined />} loading={syncing} onClick={() => void handleSync()}>
                  同步历史消息
                </Button>
              </Space>
            </div>

            <div className="chat-messages" ref={scrollRef}>
              {hasMore ? (
                <div style={{ textAlign: 'center', marginBottom: 12 }}>
                  <Button size="small" loading={messagesLoading} onClick={() => void loadEarlier()}>
                    加载更早的消息
                  </Button>
                </div>
              ) : null}
              {messagesLoading && !messages.length ? (
                <div style={{ textAlign: 'center' }}>
                  <Spin />
                </div>
              ) : null}
              {!messagesLoading && !messages.length ? (
                <div className="chat-empty">这个会话还没有消息，点「同步历史消息」拉一次</div>
              ) : null}
              {messages.map((message) => {
                const outgoing = message.direction === 'outgoing';
                return (
                  <div key={message.id} className={`chat-bubble-row${outgoing ? ' outgoing' : ''}`}>
                    <div className="chat-bubble">
                      <div className="chat-bubble-meta">
                        <span>
                          {outgoing ? '我' : message.sender_name || '对方'}
                          {message.sender_tg_id && !outgoing ? ` (${message.sender_tg_id})` : ''}
                        </span>
                        <span>{formatTime(message.created_at, 'MM-DD HH:mm:ss')}</span>
                        {message.has_media ? (
                          <Tag icon={<FileImageOutlined />} color="cyan" style={{ marginInlineEnd: 0 }}>
                            {message.media_type || '媒体'}
                          </Tag>
                        ) : null}
                        {outgoing ? (
                          <MessageStatusTag status={message.status} label={message.status_label} />
                        ) : null}
                      </div>
                      <div>{message.body || (message.has_media ? '[媒体消息]' : '')}</div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="chat-composer">
              {activeDialog.channel === 'user_account' ? (
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 8 }}
                  message="这条会话走用户号：发送会写成待发送任务，等持有租约的 Worker 发出后才变「已发送」。"
                />
              ) : null}
              {draftId ? (
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginBottom: 8 }}
                  message="AI 草稿已填入输入框，点「发送」才会发出去"
                  action={
                    <Button size="small" onClick={() => void handleDiscardDraft()}>
                      丢弃草稿
                    </Button>
                  }
                />
              ) : null}
              <Input.TextArea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder={
                  activeDialog.channel === 'user_account'
                    ? '输入回复内容，发送后等员工确认（Ctrl/⌘ + Enter 也可以发送）'
                    : '输入回复内容，Bot 会直接发出（Ctrl/⌘ + Enter 也可以发送）'
                }
                autoSize={{ minRows: 2, maxRows: 6 }}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                    event.preventDefault();
                    void handleSend();
                  }
                }}
              />
              <Space style={{ marginTop: 8, width: '100%' }} wrap>
                <Input
                  size="small"
                  style={{ width: 260 }}
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder="给 AI 的要求（可选），例如：用中文礼貌回复"
                  prefix={<RobotOutlined />}
                />
                <Button icon={<RobotOutlined />} loading={drafting} onClick={() => void handleDraft()}>
                  AI 草稿
                </Button>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={sending}
                  disabled={!text.trim()}
                  onClick={() => void handleSend()}
                >
                  发送
                </Button>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  草稿停在输入框，员工点发送才出去；操作记录里会留下是谁点的。
                </Typography.Text>
              </Space>
            </div>
          </>
        ) : (
          <div className="chat-empty">
            <Space direction="vertical" align="center">
              <UserOutlined style={{ fontSize: 28 }} />
              <Typography.Text type="secondary">从左边选一个群聊或私信开始处理</Typography.Text>
            </Space>
          </div>
        )}
      </div>
    </div>
  );
}
