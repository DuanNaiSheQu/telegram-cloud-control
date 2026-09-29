/**
 * AccountAvatar —— 账号头像：优先显示该号在 Telegram 上的真实头像，没有才回退首字母。
 *
 * 头像是 Worker 在连接成功后下载并缓存的（`materials/avatars/<id>.jpg`），接口只读文件；
 * 接口要带 `Authorization`，`<img src>` 带不了，所以这里用 fetch 取 blob 再转 objectURL。
 * 拉不到（还没同步 / 该号没设头像）就安静地回退成首字母，不显示破图。
 */
import { Avatar } from 'antd';
import { useEffect, useState } from 'react';
import { TOKEN_KEY } from '../../api/client';

/** 同一次会话内缓存，避免列表滚动重复拉同一张头像 */
const cache = new Map<string, string | null>();

export interface AccountAvatarProps {
  accountId: string;
  /** 回退显示的文字（一般取资料名 / 用户名 / 手机号的首字母） */
  fallback: string;
  size?: number;
  title?: string;
}

export default function AccountAvatar({ accountId, fallback, size = 24, title }: AccountAvatarProps) {
  const [url, setUrl] = useState<string | null>(() => cache.get(accountId) ?? null);

  useEffect(() => {
    if (cache.has(accountId)) {
      setUrl(cache.get(accountId) ?? null);
      return;
    }
    let alive = true;
    const token = window.localStorage.getItem(TOKEN_KEY);
    void fetch(`/api/accounts/${accountId}/avatar`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
      .then((res) => (res.ok ? res.blob() : Promise.reject(new Error(String(res.status)))))
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        cache.set(accountId, objectUrl);
        if (alive) setUrl(objectUrl);
      })
      .catch(() => {
        cache.set(accountId, null); // 记成「没有头像」，避免每次渲染都重试
        if (alive) setUrl(null);
      });
    return () => {
      alive = false;
    };
  }, [accountId]);

  if (url) {
    return (
      <span title={title} style={{ display: 'inline-flex' }}>
        <Avatar size={size} src={url} />
      </span>
    );
  }
  return (
    <span title={title} style={{ display: 'inline-flex' }}>
      <Avatar
        size={size}
        style={{ background: 'var(--tg-color-primary-bg)', color: 'var(--tg-color-primary)', flexShrink: 0 }}
      >
        {fallback}
      </Avatar>
    </span>
  );
}
