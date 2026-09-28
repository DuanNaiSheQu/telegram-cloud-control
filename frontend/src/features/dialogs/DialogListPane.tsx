/**
 * 会话列表左栏：关键词搜索 + 折叠筛选（通道/类型/账号/Bot/只看未读）+ 排序切换 +
 * 滚动到底自动加载下一页；每条含渠道色条、未读角标、最后消息预览。
 */
import { useEffect, useRef, useState } from 'react';
import { Button, Input, Popover, Select, Switch, Tooltip } from 'antd';
import {
  FilterOutlined,
  ReloadOutlined,
  SortAscendingOutlined,
  SortDescendingOutlined,
} from '@ant-design/icons';
import { EmptyState, ErrorState, RelativeTime, SoftTag } from '../../components';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { previewText } from '../../utils/format';
import { DIALOG_CHANNEL_LABELS, DIALOG_KIND_LABELS } from '../../constants';
import type { DialogChannel, DialogKind, DialogOut, WsStatus } from '../../api/types';
import type { DialogListFilters } from './useDialogList';
import { WS_STATUS_TEXT } from '../../hooks/useWebSocket';

export interface SelectOptionLike {
  value: string;
  label: string;
}

interface DialogListPaneProps {
  items: DialogOut[];
  total: number;
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  filters: DialogListFilters;
  onFiltersChange: (patch: Partial<DialogListFilters>) => void;
  onResetFilters: () => void;
  activeCount: number;
  sortOrder: 'desc' | 'asc';
  onToggleSort: () => void;
  onReload: () => void;
  onLoadMore: () => void;
  activeId: string | null;
  onOpen: (dialog: DialogOut) => void;
  accountOptions: SelectOptionLike[];
  botOptions: SelectOptionLike[];
  wsStatus: WsStatus;
}

export function DialogListPane({
  items,
  total,
  loading,
  loadingMore,
  error,
  filters,
  onFiltersChange,
  onResetFilters,
  activeCount,
  sortOrder,
  onToggleSort,
  onReload,
  onLoadMore,
  activeId,
  onOpen,
  accountOptions,
  botOptions,
  wsStatus,
}: DialogListPaneProps) {
  const [keywordInput, setKeywordInput] = useState(filters.keyword);
  const [filterOpen, setFilterOpen] = useState(false);
  const debouncedKeyword = useDebouncedValue(keywordInput, 400);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // 关键词防抖后才会触发查询（避免每敲一个字就请求一次）
  useEffect(() => {
    if (debouncedKeyword.trim() === filters.keyword.trim()) return;
    onFiltersChange({ keyword: debouncedKeyword });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedKeyword]);

  // 滚动到底自动加载下一页
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !loading && !loadingMore && items.length < total) {
          onLoadMore();
        }
      },
      { root: node.parentElement, rootMargin: '120px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [loading, loadingMore, items.length, total, onLoadMore]);

  const filterPopover = (
    <div style={{ width: 264, display: 'flex', flexDirection: 'column', gap: 'var(--tg-space-md)' }}>
      <Select
        allowClear
        size="small"
        placeholder="通道"
        value={filters.channel || undefined}
        onChange={(value) => onFiltersChange({ channel: (value as DialogChannel) ?? '' })}
        options={[
          { value: 'user_account', label: '用户号' },
          { value: 'bot', label: 'Bot' },
        ]}
      />
      <Select
        allowClear
        size="small"
        placeholder="类型"
        value={filters.kind || undefined}
        onChange={(value) => onFiltersChange({ kind: (value as DialogKind) ?? '' })}
        options={[
          { value: 'group', label: '群聊' },
          { value: 'private', label: '私信' },
        ]}
      />
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        size="small"
        placeholder="账号"
        value={filters.account_id ?? undefined}
        onChange={(value) => onFiltersChange({ account_id: value ?? null })}
        options={accountOptions}
      />
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        size="small"
        placeholder="Bot"
        value={filters.bot_id ?? undefined}
        onChange={(value) => onFiltersChange({ bot_id: value ?? null })}
        options={botOptions}
      />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ color: 'var(--tg-color-text-secondary)', fontSize: 'var(--tg-font-size-sm)' }}>
          只看未读
        </span>
        <Switch
          size="small"
          checked={filters.only_unread}
          onChange={(checked) => onFiltersChange({ only_unread: checked })}
        />
      </div>
      {activeCount > 0 ? (
        <Button size="small" block onClick={onResetFilters}>
          清空筛选
        </Button>
      ) : null}
    </div>
  );

  const wsText = WS_STATUS_TEXT[wsStatus];

  return (
    <div className="im-list-pane">
      <div className="im-list-toolbar">
        <Input
          allowClear
          size="small"
          placeholder="搜索会话（标题 / 对方 / 正文）"
          value={keywordInput}
          onChange={(event) => setKeywordInput(event.target.value)}
        />
        <div className="im-list-tools">
          <Popover
            open={filterOpen}
            onOpenChange={setFilterOpen}
            trigger="click"
            placement="bottomLeft"
            content={filterPopover}
          >
            <Tooltip title="筛选">
              <Button size="small" icon={<FilterOutlined />} style={{ position: 'relative' }}>
                筛选
                {activeCount > 0 ? <span className="im-filter-badge">{activeCount}</span> : null}
              </Button>
            </Tooltip>
          </Popover>
          <Tooltip title={sortOrder === 'desc' ? '按最后消息时间：最新在前' : '按最后消息时间：最早在前'}>
            <Button
              size="small"
              icon={sortOrder === 'desc' ? <SortDescendingOutlined /> : <SortAscendingOutlined />}
              onClick={onToggleSort}
            >
              {sortOrder === 'desc' ? '最新' : '最早'}
            </Button>
          </Tooltip>
          <Tooltip title="刷新">
            <Button size="small" type="text" icon={<ReloadOutlined />} loading={loading} onClick={onReload} aria-label="刷新" />
          </Tooltip>
        </div>
        <div className="im-list-meta">
          <span>
            共 {total} 个会话
            {filters.only_unread ? '（只看未读）' : ''}
            {filters.keyword.trim() ? ` · 含「${filters.keyword.trim()}」` : ''}
          </span>
          <span className="im-ws-dot">
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: wsStatus === 'open' ? 'var(--tg-color-success)' : 'var(--tg-color-warning)',
              }}
            />
            {wsText}
          </span>
        </div>
      </div>

      <div className="im-list-scroll">
        {error ? (
          <div style={{ padding: 'var(--tg-space-giant)' }}>
            <ErrorState compact error={error} onRetry={onReload} />
          </div>
        ) : null}

        {!error && loading && !items.length ? (
          <div className="im-list-empty" style={{ textAlign: 'center', color: 'var(--tg-color-text-tertiary)' }}>
            加载中…
          </div>
        ) : null}

        {!error && !loading && !items.length ? (
          <div className="im-list-empty">
            <EmptyState
              compact
              art={activeCount > 0 || filters.keyword.trim() ? 'search' : 'inbox'}
              title={activeCount > 0 || filters.keyword.trim() ? '没有符合条件的会话' : '还没有会话'}
              description={
                activeCount > 0 || filters.keyword.trim()
                  ? '换个关键词或清空筛选看看。'
                  : '账号登录后会自动同步它的群聊与私信。'
              }
              action={
                activeCount > 0 || filters.keyword.trim() ? (
                  <Button size="small" onClick={onResetFilters}>
                    清空筛选
                  </Button>
                ) : undefined
              }
            />
          </div>
        ) : null}

        {items.map((dialog) => {
          const isBot = dialog.channel === 'bot';
          return (
            <div
              key={dialog.id}
              className={[
                'im-dialog-item',
                dialog.id === activeId ? 'is-active' : '',
                isBot ? 'is-bot' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              role="button"
              tabIndex={0}
              onClick={() => onOpen(dialog)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpen(dialog);
                }
              }}
            >
              <span className={['im-channel-dot', isBot ? 'is-bot' : ''].filter(Boolean).join(' ')} />
              <div className="im-dialog-main">
                <div className="im-dialog-title-row">
                  <span className="im-dialog-title">
                    {dialog.title || dialog.peer_display || `会话 ${dialog.tg_chat_id}`}
                  </span>
                  <SoftTag tone={isBot ? 'info' : 'primary'} size="sm">
                    {dialog.channel_label || DIALOG_CHANNEL_LABELS[dialog.channel]}
                  </SoftTag>
                  <SoftTag tone="neutral" size="sm">
                    {dialog.kind_label || DIALOG_KIND_LABELS[dialog.kind]}
                  </SoftTag>
                </div>
                <div className="im-dialog-preview">
                  {previewText(dialog.last_message_preview, 40) || '暂无消息'}
                </div>
                <div className="im-dialog-sub">
                  {dialog.account_label ||
                    (dialog.bot_label ? `@${dialog.bot_label}` : '—')}
                  {dialog.member_count ? ` · ${dialog.member_count} 人` : ''}
                  {dialog.username ? ` · @${dialog.username}` : ''}
                </div>
              </div>
              <div className="im-dialog-meta">
                <RelativeTime
                  value={dialog.last_message_at}
                  refreshMs={60_000}
                  className="tg-muted"
                  style={{ fontSize: 'var(--tg-font-size-xs)' }}
                />
                {dialog.unread_count > 0 ? (
                  <span className="im-unread-badge">{dialog.unread_count}</span>
                ) : null}
              </div>
            </div>
          );
        })}

        <div ref={sentinelRef} style={{ height: 1 }} />
      </div>

      <div className="im-list-footer">
        {loadingMore ? (
          '加载中…'
        ) : items.length < total ? (
          <Button type="link" size="small" onClick={onLoadMore}>
            加载更多（已显示 {items.length} / {total}）
          </Button>
        ) : items.length > 0 ? (
          '已加载全部会话'
        ) : null}
      </div>
    </div>
  );
}
