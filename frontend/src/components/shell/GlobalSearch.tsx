/**
 * GlobalSearch —— 全局搜索（顶栏入口 + Ctrl/⌘+K 唤起）。
 *
 * props 契约：
 * ┌──────────┬──────────────────────────────────────────────────────────────────┐
 * │ open     │ boolean                                                          │
 * │ onClose  │ () => void                                                       │
 * └──────────┴──────────────────────────────────────────────────────────────────┘
 * 搜索范围（全部 silent，后端没起时不弹错误、不白屏）：
 *   1. 页面导航（本地匹配侧栏）
 *   2. 账号（GET /api/accounts?keyword=）
 *   3. 会话（GET /api/dialogs?keyword=）
 *   4. 消息正文（GET /api/messages?q=，≥2 个字符才查）
 * 键盘：↑↓ 选择，Enter 打开，Esc 关闭。
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input, Modal, Spin, Typography } from 'antd';
import { ApiOutlined, MessageOutlined, SearchOutlined, UserOutlined } from '@ant-design/icons';
import { NAV_ITEMS } from './nav';
import { accountApi, dialogApi, messageApi } from '../../api/endpoints';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { useAsyncData } from '../../hooks/useAsyncData';
import StatusBadge from '../StatusBadge';
import { previewText } from '../../utils/format';

export interface GlobalSearchProps {
  open: boolean;
  onClose: () => void;
}

interface ResultItem {
  key: string;
  kind: 'page' | 'account' | 'dialog' | 'message';
  title: string;
  desc?: string;
  extra?: React.ReactNode;
  icon: React.ReactNode;
  go: () => void;
}

const KIND_LABEL: Record<ResultItem['kind'], string> = {
  page: '页面',
  account: '账号',
  dialog: '会话',
  message: '消息',
};

export function GlobalSearch({ open, onClose }: GlobalSearchProps) {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const q = keyword.trim();
  const debounced = useDebouncedValue(q, 250);

  useEffect(() => {
    if (!open) {
      setKeyword('');
      setActiveIndex(0);
    }
  }, [open]);

  const accounts = useAsyncData(
    () =>
      debounced
        ? accountApi.list({ keyword: debounced, page_size: 6 }, { silent: true })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 0 }),
    [debounced],
    { silentError: true },
  );

  const dialogs = useAsyncData(
    () =>
      debounced
        ? dialogApi.list({ keyword: debounced, page_size: 6 }, { silent: true })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 0 }),
    [debounced],
    { silentError: true },
  );

  const messages = useAsyncData(
    () =>
      debounced.length >= 2
        ? messageApi.search({ q: debounced, page_size: 5 }, { silent: true })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 0 }),
    [debounced],
    { silentError: true },
  );

  const results = useMemo<ResultItem[]>(() => {
    const items: ResultItem[] = [];
    const lower = q.toLowerCase();

    NAV_ITEMS.filter(
      (item) => !q || item.label.toLowerCase().includes(lower) || (item.description ?? '').includes(q),
    )
      .slice(0, 6)
      .forEach((item) => {
        items.push({
          key: `page:${item.path}`,
          kind: 'page',
          title: item.label,
          desc: item.description,
          icon: item.icon,
          go: () => navigate(item.path),
        });
      });

    (accounts.data?.items ?? []).forEach((account) => {
      items.push({
        key: `account:${account.id}`,
        kind: 'account',
        title: account.display_name || account.phone_masked,
        desc: `${account.phone_masked}${account.group_name ? ` · ${account.group_name}` : ''}`,
        extra: <StatusBadge status={account.status} label={account.status_label} size="sm" showDot={false} />,
        icon: <UserOutlined />,
        go: () => navigate(`/accounts?keyword=${encodeURIComponent(account.phone_masked)}`),
      });
    });

    (dialogs.data?.items ?? []).forEach((dialog) => {
      items.push({
        key: `dialog:${dialog.id}`,
        kind: 'dialog',
        title: dialog.title || dialog.peer_display,
        desc: `${dialog.channel_label} · ${dialog.kind_label}${dialog.last_message_preview ? ` · ${previewText(dialog.last_message_preview, 30)}` : ''}`,
        extra: dialog.unread_count ? <span className="tg-muted">{dialog.unread_count} 条未读</span> : null,
        icon: <MessageOutlined />,
        go: () => navigate(`/dialogs?dialog_id=${dialog.id}`),
      });
    });

    (messages.data?.items ?? []).forEach((message) => {
      items.push({
        key: `message:${message.id}`,
        kind: 'message',
        title: previewText(message.body, 60),
        desc: `${message.direction_label} · ${message.sender_name || '未知发送人'}`,
        icon: <ApiOutlined />,
        go: () => navigate(`/dialogs?dialog_id=${message.dialog_id}`),
      });
    });

    return items;
  }, [accounts.data, dialogs.data, messages.data, navigate, q]);

  useEffect(() => {
    setActiveIndex(0);
  }, [debounced]);

  const loading = accounts.loading || dialogs.loading || messages.loading;

  const open_ = (item?: ResultItem) => {
    const target = item ?? results[activeIndex];
    if (!target) return;
    target.go();
    onClose();
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      open_();
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width={640}
      destroyOnHidden
      className="tg-search-modal"
      styles={{ body: { paddingTop: 'var(--tg-space-md)' } }}
    >
      <Input
        autoFocus
        allowClear
        size="large"
        className="tg-search-input"
        prefix={<SearchOutlined style={{ color: 'var(--tg-color-text-tertiary)' }} />}
        placeholder="搜索账号、会话、消息，或直接跳到页面…"
        value={keyword}
        onChange={(event) => setKeyword(event.target.value)}
        onKeyDown={handleKeyDown}
        suffix={loading ? <Spin size="small" /> : null}
      />

      <div className="tg-search-results">
        {!q ? (
          <div className="tg-stack" style={{ gap: 'var(--tg-space-xs)' }}>
            <div className="tg-search-group-title">常用页面</div>
            {results.map((item, index) => (
              <div
                key={item.key}
                className={['tg-search-item', index === activeIndex ? 'is-active' : ''].filter(Boolean).join(' ')}
                onClick={() => open_(item)}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <span className="app-nav-icon" style={{ color: 'var(--tg-color-text-tertiary)' }}>
                  {item.icon}
                </span>
                <div className="tg-search-item-main">
                  <div className="tg-search-item-title">{item.title}</div>
                  {item.desc ? <div className="tg-search-item-desc">{item.desc}</div> : null}
                </div>
              </div>
            ))}
          </div>
        ) : results.length === 0 ? (
          <Typography.Text type="secondary" style={{ display: 'block', padding: 'var(--tg-space-xxl) 0', textAlign: 'center' }}>
            {loading ? '搜索中…' : `没有匹配「${q}」的结果`}
          </Typography.Text>
        ) : (
          results.map((item, index) => (
            <div
              key={item.key}
              className={['tg-search-item', index === activeIndex ? 'is-active' : ''].filter(Boolean).join(' ')}
              onClick={() => open_(item)}
              onMouseEnter={() => setActiveIndex(index)}
            >
              <span className="app-nav-icon" style={{ color: 'var(--tg-color-text-tertiary)' }}>
                {item.icon}
              </span>
              <div className="tg-search-item-main">
                <div className="tg-search-item-title">{item.title}</div>
                {item.desc ? <div className="tg-search-item-desc">{item.desc}</div> : null}
              </div>
              {item.extra}
              <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
                {KIND_LABEL[item.kind]}
              </span>
            </div>
          ))
        )}
      </div>

      <div className="tg-search-hint">
        <span>
          <span className="tg-kbd">↑</span> <span className="tg-kbd">↓</span> 选择
        </span>
        <span>
          <span className="tg-kbd">Enter</span> 打开
        </span>
        <span>
          <span className="tg-kbd">Esc</span> 关闭
        </span>
        <span style={{ marginLeft: 'auto' }}>消息正文搜索至少输入 2 个字符</span>
      </div>
    </Modal>
  );
}

export default GlobalSearch;
