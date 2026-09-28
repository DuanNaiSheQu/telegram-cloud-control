/**
 * useBotHealth —— Bots 页的 Token 有效性体检。
 * 页面加载后逐个调 GET /api/bots/{id}/check（getMe），400/401 = Token 无效 →
 * 列表行标黄。结果按 bot id 缓存在模块级，避免每次刷新都打一批 getMe；
 * 「重新校验」成功后页面会手动更新对应项。
 * 注意：check 端点要求 admin，operator 登录时不体检（不给黄标）。
 */
import { useEffect, useState } from 'react';
import { api, ApiError } from '../../api/client';
import type { BotOut } from '../../api/types';

export type BotHealth = 'ok' | 'invalid' | 'checking';

const healthCache = new Map<string, BotHealth>();

export function setBotHealthCache(botId: string, health: BotHealth): void {
  healthCache.set(botId, health);
}

export function useBotHealth(
  bots: BotOut[],
  enabled: boolean,
  version: number,
): Record<string, BotHealth> {
  const [health, setHealth] = useState<Record<string, BotHealth>>({});

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const run = async () => {
      const next: Record<string, BotHealth> = {};
      for (const bot of bots) {
        const cached = healthCache.get(bot.id);
        if (cached) {
          next[bot.id] = cached;
          setHealth({ ...next });
          continue;
        }
        try {
          await api.get<unknown>(`/api/bots/${bot.id}/check`, undefined, {
            silent: true,
            retries: 0,
          });
          healthCache.set(bot.id, 'ok');
        } catch (err) {
          const status = err instanceof ApiError ? err.status : 0;
          // 400（Telegram 拒绝/格式错/解密失败）与 401 视为无效；网络失败不误判
          healthCache.set(bot.id, status === 400 || status === 401 ? 'invalid' : 'ok');
        }
        if (cancelled) return;
        next[bot.id] = healthCache.get(bot.id) ?? 'ok';
        setHealth({ ...next });
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // 体检触发：Bot 列表变化 / 手动校验后 version 递增
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bots.map((b) => b.id).join(','), enabled, version]);

  return health;
}
