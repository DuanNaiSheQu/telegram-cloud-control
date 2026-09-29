/**
 * 消息流渲染：按时间正序的气泡 + 日期分隔 + 未读分隔线 + 媒体占位 + 失败重发。
 * 滚动行为：贴底状态跟踪、跳到底部按钮、滚到顶部自动加载更早。
 */
import { useCallback, useEffect, useState, type RefObject } from 'react';
import { Button, Spin, Tooltip } from 'antd';
import {
  CloudSyncOutlined,
  FileImageOutlined,
  VerticalAlignBottomOutlined,
} from '@ant-design/icons';
import { EmptyState, ErrorState, MessageStatusTag } from '../../components';
import type { MessageOut } from '../../api/types';
import type { ImListItem } from './types';

interface MessageListProps {
  items: ImListItem[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  onRetry: () => void;
  onLoadEarlier: () => void;
  onResend: (message: MessageOut) => void;
  onSync: () => void;
  onMarkRead: () => void;
  searchMode: boolean;
  searchQ: string;
  clearSearch: () => void;
  scrollRef: RefObject<HTMLDivElement>;
  scrollToBottom: (smooth?: boolean) => void;
}

function senderInitial(name: string): string {
  const trimmed = (name || '对').trim();
  return trimmed ? Array.from(trimmed)[0] : '对';
}

export function MessageList({
  items,
  hasMore,
  loading,
  loadingMore,
  error,
  onRetry,
  onLoadEarlier,
  onResend,
  onSync,
  onMarkRead,
  searchMode,
  searchQ,
  clearSearch,
  scrollRef,
  scrollToBottom,
}: MessageListProps) {
  const [atBottom, setAtBottom] = useState(true);

  const handleScroll = useCallback(() => {
    const node = scrollRef.current;
    if (!node) return;
    setAtBottom(node.scrollHeight - node.scrollTop - node.clientHeight < 120);
    if (node.scrollTop < 40 && hasMore && !loadingMore) onLoadEarlier();
  }, [scrollRef, hasMore, loadingMore, onLoadEarlier]);

  // 新消息进来时如果本来贴底，跟着滚到底
  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const wasAtBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 120;
    if (wasAtBottom) node.scrollTop = node.scrollHeight;
  }, [items.length, scrollRef]);

  if (error) {
    return (
      <div className="im-messages">
        <div style={{ padding: 'var(--tg-space-giant)' }}>
          <ErrorState error={error} onRetry={onRetry} compact />
        </div>
      </div>
    );
  }

  return (
    <div className="im-messages" ref={scrollRef} onScroll={handleScroll}>
      {loading && !items.length ? (
        <div className="im-chat-empty">
          <Spin size="small" />
        </div>
      ) : null}

      {!loading && !items.length && searchMode ? (
        <div className="im-chat-empty">
          <EmptyState
            compact
            art="search"
            title={`没有匹配「${searchQ.trim()}」的消息`}
            description="换个关键词试试。"
            action={<Button size="small" onClick={clearSearch}>退出搜索</Button>}
          />
        </div>
      ) : null}

      {!loading && !items.length && !searchMode ? (
        <div className="im-chat-empty">
          <EmptyState
            compact
            art="message"
            title="这个会话还没有消息"
            description="点「同步历史消息」把云端聊天记录拉下来。"
            action={
              <Button size="small" type="primary" icon={<CloudSyncOutlined />} onClick={onSync}>
                同步历史消息
              </Button>
            }
          />
        </div>
      ) : null}

      {hasMore && items.length ? (
        <div className="im-load-earlier">
          <Button size="small" loading={loadingMore} onClick={onLoadEarlier}>
            加载更早的消息
          </Button>
        </div>
      ) : null}

      {items.map((item) => {
        if (item.kind === 'date') {
          return (
            <div className="im-date-sep" key={item.key}>
              <span>{item.text}</span>
            </div>
          );
        }
        if (item.kind === 'unread') {
          return (
            <div className="im-unread-sep" key={item.key}>
              <button type="button" onClick={onMarkRead} title="点击标记为已读">
                {item.count} 条新消息 · 标记已读
              </button>
            </div>
          );
        }
        const message = item.message;
        const outgoing = message.direction === 'outgoing';
        const failed = outgoing && message.status === 'failed';
        const time = message.created_at ? dayjsFormat(message.created_at) : '';
        return (
          <div
            key={item.key}
            className={[
              'im-msg-row',
              outgoing ? 'is-out' : 'is-in',
              failed ? 'is-failed' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {!outgoing ? (
              <div className="im-avatar" title={message.sender_name || '（Telegram 未提供发送者）'}>
                {senderInitial(message.sender_name)}
              </div>
            ) : null}
            <div className="im-bubble">
              <div className="im-bubble-head">
                {outgoing ? (
                  <span>我</span>
                ) : (
                  <span>{message.sender_name || '（发送者未知）'}</span>
                )}
                {message.sender_tg_id && !outgoing ? <span>ID {message.sender_tg_id}</span> : null}
              </div>
              {message.has_media ? (
                <div className="im-media-card">
                  <FileImageOutlined />
                  <span>{message.media_type || '媒体'} 消息</span>
                </div>
              ) : null}
              {message.body ? <div className="im-bubble-body">{message.body}</div> : null}
              <div className="im-bubble-foot">
                {failed ? <span>发送失败</span> : null}
                <span>{time}</span>
                {outgoing && !failed ? (
                  <MessageStatusTag status={message.status} label={message.status_label} size="sm" showDot={false} />
                ) : null}
                {failed ? (
                  <Tooltip title="重新走一次发送">
                    <button type="button" className="im-retry-btn" onClick={() => onResend(message)}>
                      重发
                    </button>
                  </Tooltip>
                ) : null}
              </div>
            </div>
          </div>
        );
      })}

      {!atBottom && items.length ? (
        <button
          type="button"
          className="im-jump-bottom"
          aria-label="跳到底部"
          title="跳到底部"
          onClick={() => scrollToBottom(true)}
        >
          <VerticalAlignBottomOutlined />
        </button>
      ) : null}

      {loadingMore ? (
        <div className="im-load-earlier">
          <Spin size="small" />
        </div>
      ) : null}
    </div>
  );
}

function dayjsFormat(iso: string): string {
  // 轻量时间展示（气泡内只显示时:分）
  return new Date(iso).toLocaleTimeString('zh-Hans', { hour: '2-digit', minute: '2-digit' });
}
