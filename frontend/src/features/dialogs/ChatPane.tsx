/**
 * 聊天右栏：会话头（信息/同步/标记已读/会话内搜索/WS 状态）+
 * 消息流（MessageList）+ 输入区（AI 草稿、发送、Ctrl/⌘+Enter、二分支失败提示）。
 */
import { useEffect, useState } from 'react';
import { Alert, Button, Input, Space, Tooltip, Typography } from 'antd';
import {
  CheckOutlined,
  CloudSyncOutlined,
  InfoCircleOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
} from '@ant-design/icons';
import { DetailDrawer, CopyableText, EmptyState, SoftTag, StatusBadge } from '../../components';
import { api } from '../../api/client';
import { DIALOG_CHANNEL_LABELS, DIALOG_KIND_LABELS } from '../../constants';
import { formatTime } from '../../utils/format';
import type { AccountOut } from '../../api/types';
import type { ChatRoomState } from './useChatRoom';
import { MessageList } from './MessageList';
import { WS_STATUS_TEXT } from '../../hooks/useWebSocket';

interface ChatPaneProps {
  room: ChatRoomState;
}

const { Text } = Typography;

export function ChatPane({ room }: ChatPaneProps) {
  const dialog = room.dialog;
  const [infoOpen, setInfoOpen] = useState(false);
  const [account, setAccount] = useState<AccountOut | null>(null);

  // 用户号会话：拉一下账号状态，输入区实时展示校验提示
  useEffect(() => {
    setAccount(null);
    if (!dialog?.account_id) return;
    api
      .get<AccountOut>(`/api/accounts/${dialog.account_id}`, undefined, { silent: true })
      .then(setAccount)
      .catch(() => setAccount(null));
  }, [dialog?.account_id]);

  if (!dialog) {
    return (
      <div className="im-chat-pane">
        <div className="im-chat-empty">
          <EmptyState
            art="inbox"
            title="从左边选择一个会话"
            description="打开后可以查看聊天记录、回消息、生成 AI 草稿；新消息会实时推送。"
          />
        </div>
      </div>
    );
  }

  const isBot = dialog.channel === 'bot';

  const infoSections = [
    {
      title: '会话信息',
      items: [
        { label: '通道', value: <SoftTag tone={isBot ? 'info' : 'primary'} size="sm">{dialog.channel_label || DIALOG_CHANNEL_LABELS[dialog.channel]}</SoftTag> },
        { label: '类型', value: dialog.kind_label || DIALOG_KIND_LABELS[dialog.kind] },
        { label: 'Telegram chat_id', value: <CopyableText value={dialog.tg_chat_id} mono /> },
        { label: '用户名', value: dialog.username || undefined },
        { label: '成员数', value: dialog.member_count ?? undefined },
        { label: '置顶', value: dialog.is_pinned ? '是' : '否' },
        { label: '未读', value: dialog.unread_count },
        { label: '最后消息时间', value: formatTime(dialog.last_message_at) },
        { label: '最后消息预览', value: dialog.last_message_preview || undefined, span: 'full' as const },
      ],
    },
    {
      title: '归属',
      items: [
        {
          label: '账号',
          value: dialog.account_label ? (
            <Space size={4}>
              <span>{dialog.account_label}</span>
              {dialog.account_id ? <CopyableText value={dialog.account_id} mono maxLength={20} /> : null}
            </Space>
          ) : undefined,
        },
        {
          label: 'Bot',
          value: dialog.bot_label ? (
            <Space size={4}>
              <span>@{dialog.bot_label}</span>
              {dialog.bot_id ? <CopyableText value={dialog.bot_id} mono maxLength={20} /> : null}
            </Space>
          ) : undefined,
        },
      ],
    },
  ];

  return (
    <div className="im-chat-pane">
      {/* ---------- 会话头 ---------- */}
      <div className="im-chat-header">
        <div className="im-chat-title-wrap">
          <div className="im-chat-title">
            <Text strong ellipsis style={{ maxWidth: 320, fontSize: 'var(--tg-font-size)' }}>
              {dialog.title || dialog.peer_display || `会话 ${dialog.tg_chat_id}`}
            </Text>
            <SoftTag tone={isBot ? 'info' : 'primary'} size="sm">
              {dialog.channel_label || DIALOG_CHANNEL_LABELS[dialog.channel]}
            </SoftTag>
            <SoftTag tone="neutral" size="sm">
              {dialog.kind_label || DIALOG_KIND_LABELS[dialog.kind]}
            </SoftTag>
            {dialog.kind === 'group' && dialog.member_count ? (
              <span className="im-chat-meta">{dialog.member_count} 人</span>
            ) : null}
          </div>
          <div className="im-chat-meta">
            {dialog.account_label ? `账号 ${dialog.account_label}` : ''}
            {dialog.bot_label ? `Bot @${dialog.bot_label}` : ''}
            {` · chat_id ${dialog.tg_chat_id}`}
            {dialog.username ? ` · @${dialog.username}` : ''}
          </div>
        </div>

        <div className="im-chat-actions">
          <Tooltip title={WS_STATUS_TEXT[room.wsStatus]}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                display: 'inline-block',
                background:
                  room.wsStatus === 'open' ? 'var(--tg-color-success)' : 'var(--tg-color-warning)',
              }}
            />
          </Tooltip>
          <Input
            allowClear
            size="small"
            prefix={<SearchOutlined style={{ color: 'var(--tg-color-text-tertiary)' }} />}
            placeholder="在本会话内搜索"
            style={{ width: 180 }}
            value={room.searchQ}
            onChange={(event) => room.setSearchQ(event.target.value)}
          />
          <Button size="small" icon={<CheckOutlined />} onClick={() => void room.markRead()}>
            标记已读
          </Button>
          <Tooltip title={isBot ? 'Bot 通道不支持补拉历史：Telegram Bot API 没有历史消息接口' : '排队一条同步任务，把云端历史消息拉下来'}>
            <Button
              size="small"
              icon={<CloudSyncOutlined />}
              disabled={isBot}
              onClick={() => void room.syncHistory()}
            >
              同步历史
            </Button>
          </Tooltip>
          <Button size="small" icon={<InfoCircleOutlined />} onClick={() => setInfoOpen(true)}>
            会话信息
          </Button>
        </div>
      </div>

      {/* ---------- 消息流 ---------- */}
      {room.searchMode ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--tg-space-md)',
            padding: 'var(--tg-space-xs) var(--tg-space-xl)',
            background: 'var(--tg-color-bg-card)',
            borderBottom: '1px solid var(--tg-color-border-subtle)',
            fontSize: 'var(--tg-font-size-sm)',
            color: 'var(--tg-color-text-secondary)',
          }}
        >
          <SearchOutlined />
          在「{dialog.title || dialog.peer_display}」内搜索「{room.searchQ.trim()}」：找到 {room.searchTotal} 条
          <Button type="link" size="small" onClick={room.clearSearch}>
            退出搜索
          </Button>
        </div>
      ) : null}

      <MessageList
        items={room.items}
        hasMore={room.hasMore}
        loading={room.loading}
        loadingMore={room.loadingMore}
        error={room.error}
        onRetry={() => {
          room.clearSearch();
        }}
        onLoadEarlier={room.loadEarlier}
        onResend={(message) => void room.resend(message)}
        onSync={() => void room.syncHistory()}
        onMarkRead={() => void room.markRead()}
        searchMode={room.searchMode}
        searchQ={room.searchQ}
        clearSearch={room.clearSearch}
        scrollRef={room.scrollRef}
        scrollToBottom={room.scrollToBottom}
      />

      {/* ---------- 输入区 ---------- */}
      <div className="im-composer">
        {room.sendError ? (
          <Alert
            type="error"
            showIcon
            closable
            onClose={room.dismissSendError}
            message="发送失败"
            description={room.sendError}
          />
        ) : null}

        {room.aiGuide ? (
          <Alert
            type="info"
            showIcon
            closable
            onClose={room.dismissAiGuide}
            message="AI 草稿"
            description={room.aiGuide}
          />
        ) : null}

        {room.draftId ? (
          <Alert
            type="warning"
            showIcon
            message="AI 草稿已填入输入框，点「发送」才会发出去"
            description="丢弃后草稿作废；发送成功会在操作记录里留下是谁点的发送。"
            action={
              <Button size="small" onClick={() => void room.discardDraft()}>
                丢弃草稿
              </Button>
            }
          />
        ) : null}

        {room.unreadMarker ? (
          <Alert
            type="info"
            showIcon
            message={`有 ${room.unreadMarker.count} 条未读消息`}
            description="消息流里有分隔线标出未读起点，点击分隔线即可标记已读。"
          />
        ) : null}

        <div className="im-composer-hints">
          {account ? (
            <Space size={4}>
              <span className="im-composer-note">账号状态</span>
              <StatusBadge status={account.status} label={account.status_label} size="sm" />
            </Space>
          ) : null}
          <span className="im-composer-note">
            {isBot
              ? 'Bot 通道：点发送由 API 直接发出；发送失败原因会显示在上方。'
              : '用户号通道：发送会写成待发送任务，等持有租约的 Worker 发出；账号状态异常时发送会被拒绝。'}
          </span>
        </div>

        <Input.TextArea
          value={room.text}
          onChange={(event) => room.setText(event.target.value)}
          placeholder={
            isBot
              ? '输入回复内容，Bot 会直接发出（Ctrl/⌘ + Enter 发送）'
              : '输入回复内容，发送后排队等待 Worker 发出（Ctrl/⌘ + Enter 发送）'
          }
          autoSize={{ minRows: 2, maxRows: 6 }}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
              event.preventDefault();
              void room.send();
            }
          }}
        />

        <div className="im-composer-toolbar">
          <Input
            size="small"
            style={{ width: 260 }}
            value={room.instruction}
            onChange={(event) => room.setInstruction(event.target.value)}
            placeholder="给 AI 的要求（可选），例如：用中文礼貌回复"
            prefix={<RobotOutlined />}
          />
          <Button icon={<RobotOutlined />} loading={room.drafting} onClick={() => void room.generateDraft()}>
            AI 草稿
          </Button>
          <div className="im-composer-spacer" />
          <span className="im-composer-note">Ctrl/⌘ + Enter 快捷发送</span>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={room.sending}
            disabled={!room.text.trim()}
            onClick={() => void room.send()}
          >
            发送
          </Button>
        </div>
      </div>

      {/* ---------- 会话信息抽屉 ---------- */}
      <DetailDrawer
        open={infoOpen}
        onClose={() => setInfoOpen(false)}
        title={dialog.title || dialog.peer_display || `会话 ${dialog.tg_chat_id}`}
        subtitle={dialog.channel_label || DIALOG_CHANNEL_LABELS[dialog.channel]}
        width={560}
        sections={infoSections}
        footer={
          <Space>
            <Button icon={<CheckOutlined />} onClick={() => void room.markRead()}>
              标记已读
            </Button>
            <Tooltip title={isBot ? 'Bot 通道不支持补拉历史' : '排队同步该会话的历史消息'}>
              <Button
                type="primary"
                icon={<CloudSyncOutlined />}
                disabled={isBot}
                onClick={() => void room.syncHistory()}
              >
                同步历史消息
              </Button>
            </Tooltip>
          </Space>
        }
      />
    </div>
  );
}
