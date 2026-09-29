/**
 * AccountAvatar —— 账号头像：优先显示该号在 Telegram 上的真实头像，没有才回退首字母。
 *
 * 头像是 Worker 在连接成功后下载并缓存的（`materials/avatars/<id>.jpg`），接口只读文件；
 * 接口要带 `Authorization`，`<img src>` 带不了，所以这里用 fetch 取 blob 再转 objectURL。
 * 拉不到（还没同步 / 该号没设头像）就安静地回退成首字母，不显示破图。
 *
 * 「还没有头像」这个结论只保鲜 MISS_TTL_MS：Worker 可能过一会儿才把头像补上，
 * 检测按钮跑完也会主动 `forgetAvatar()`，让对应的头像位立刻重拉一次。
 */
import { Avatar } from 'antd';
import { useEffect, useState } from 'react';
import { TOKEN_KEY } from '../../api/client';

interface CacheEntry {
  url: string | null;
  at: number;
}

/** 同一次会话内缓存，避免列表滚动重复拉同一张头像 */
const cache = new Map<string, CacheEntry>();
/** 「没有头像」结论的保鲜期：过了就允许重拉，别让后来同步好的号一直空着 */
const MISS_TTL_MS = 60_000;
/** 订阅者：forgetAvatar() 通知对应账号的组件马上重拉 */
const listeners = new Set<(accountId: string) => void>();

/** 忘掉某个号的头像结论并通知界面重拉（检测 / 换头像之后调用） */
export function forgetAvatar(accountId: string): void {
  const hit = cache.get(accountId);
  if (hit?.url) URL.revokeObjectURL(hit.url);
  cache.delete(accountId);
  listeners.forEach((notify) => notify(accountId));
}

export interface AccountAvatarProps {
  accountId: string;
  /** 回退显示的文字（一般取资料名 / 用户名 / 手机号的首字母） */
  fallback: string;
  size?: number;
  title?: string;
}

export default function AccountAvatar({ accountId, fallback, size = 24, title }: AccountAvatarProps) {
  const [url, setUrl] = useState<string | null>(() => cache.get(accountId)?.url ?? null);
  const [nonce, setNonce] = useState(0);

  // forgetAvatar() 之后本组件重拉一次
  useEffect(() => {
    const notify = (changed: string) => {
      if (changed === accountId) setNonce((n) => n + 1);
    };
    listeners.add(notify);
    return () => {
      listeners.delete(notify);
    };
  }, [accountId]);

  useEffect(() => {
    const hit = cache.get(accountId);
    if (hit && (hit.url || Date.now() - hit.at < MISS_TTL_MS)) {
      setUrl(hit.url);
      return;
    }
    let alive = true;
    const token = window.localStorage.getItem(TOKEN_KEY);
    void fetch(`/api/accounts/${accountId}/avatar`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    })
      .then((res) => {
        // 后端对「还没有头像」返回 1x1 占位图（200）；靠响应头识别，别把它当头像渲染
        if (!res.ok) throw new Error(String(res.status));
        if (res.headers.get('X-Avatar-Placeholder')) throw new Error('no-avatar');
        return res.blob();
      })
      .then((blob) => {
        const objectUrl = URL.createObjectURL(blob);
        cache.set(accountId, { url: objectUrl, at: Date.now() });
        if (alive) setUrl(objectUrl);
      })
      .catch(() => {
        cache.set(accountId, { url: null, at: Date.now() }); // 记成「没有头像」，保鲜期内不重试
        if (alive) setUrl(null);
      });
    return () => {
      alive = false;
    };
  }, [accountId, nonce]);

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
