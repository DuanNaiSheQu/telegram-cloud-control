/**
 * 外壳数据：侧栏角标 + 顶栏连接状态 + 通知铃铛。
 *
 * 数据来源：
 *  - GET /api/dashboard（每 30s 静默轮询；字段与 API_CONTRACT v1 一致）
 *  - GET /api/notifications（后端未就绪时自动回退为「按 dashboard 派生」的提醒）
 * 全部 silent：后端没起时不弹错误提示、不白屏，只是角标为 0。
 */
import { useCallback, useMemo, useState } from 'react';
import { readJson, writeJson } from '../../utils/storage';

/** 已读通知的本地记忆（通知是按状态实时派生的，没有后端表可记） */
const NOTICE_READ_KEY = 'tgcc_read_notices';
/** 最多记多少条，防止 localStorage 无限增长 */
const NOTICE_READ_LIMIT = 200;
import { dashboardApi, notificationApi } from '../../api/endpoints';
import { ApiError } from '../../api/client';
import { useAsyncData, useInterval, useVisibilityRefresh } from '../../hooks/useAsyncData';
import type { DashboardOut, NotificationOut, WorkerStatus } from '../../api/types';

const DASHBOARD_INTERVAL_MS = 30_000;
const NOTIFICATION_INTERVAL_MS = 60_000;

export interface ShellCounts {
  online: number;
  abnormal: number;
  unread: number;
  failed: number;
  pending: number;
  running: number;
  overdue: number;
  stuck: number;
  totalAccounts: number;
  totalDialogs: number;
}

export interface ShellData {
  dashboard: DashboardOut | null;
  counts: ShellCounts;
  workers: WorkerStatus[];
  /** Worker 心跳超时数量（看板告警口径） */
  staleWorkers: number;
  generatedAt?: string | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
  notifications: NotificationOut[];
  unreadNotifications: number;
  notificationsAreDerived: boolean;
  notificationsLoading: boolean;
  refreshNotifications: () => void;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

const EMPTY_COUNTS: ShellCounts = {
  online: 0,
  abnormal: 0,
  unread: 0,
  failed: 0,
  pending: 0,
  running: 0,
  overdue: 0,
  stuck: 0,
  totalAccounts: 0,
  totalDialogs: 0,
};

export function useShellData(): ShellData {
  const dashboard = useAsyncData<DashboardOut>(() => dashboardApi.get(), [], { silentError: true });

  useInterval(() => {
    void dashboard.reload();
  }, DASHBOARD_INTERVAL_MS);
  useVisibilityRefresh(() => {
    void dashboard.reload();
  });

  const notificationsQuery = useAsyncData<NotificationOut[]>(
    async () => {
      const result = await notificationApi.list({ page_size: 10, sort: 'created_at', order: 'desc' });
      return result.items ?? [];
    },
    [],
    { silentError: true },
  );

  useInterval(() => {
    void notificationsQuery.reload();
  }, NOTIFICATION_INTERVAL_MS);

  const data = dashboard.data;

  const counts = useMemo<ShellCounts>(
    () =>
      data
        ? {
            online: data.online_accounts ?? 0,
            abnormal: data.abnormal_accounts ?? 0,
            unread: data.unread_dialogs ?? 0,
            failed: data.tasks_failed ?? 0,
            pending: data.tasks_pending ?? 0,
            running: data.tasks_running ?? 0,
            overdue: data.tasks_overdue ?? 0,
            stuck: data.tasks_stuck ?? 0,
            totalAccounts: data.total_accounts ?? 0,
            totalDialogs: data.total_dialogs ?? 0,
          }
        : EMPTY_COUNTS,
    [data],
  );

  const workers = data?.workers ?? [];
  const staleWorkers = workers.filter((worker) => worker.stale).length;

  const notificationsError = notificationsQuery.error;
  const apiMissing = notificationsError ? /404|不存在/.test(notificationsError) : false;

  /** 后端通知接口还没上时：用 dashboard 的事实派生提醒（不编造数据） */
  const derived = useMemo<NotificationOut[]>(() => {
    const items: NotificationOut[] = [];
    const stamp = data?.generated_at ?? new Date().toISOString();
    if (counts.failed > 0) {
      items.push({
        id: `derived-failed:${counts.failed}`,
        kind: 'task_failed',
        kind_label: '任务失败',
        level: 'error',
        title: `${counts.failed} 个任务失败`,
        body: '到任务中心看失败原因，可单条重试。',
        link: '/tasks?status=failed',
        read: false,
        created_at: stamp,
      });
    }
    if (counts.abnormal > 0) {
      items.push({
        id: `derived-abnormal:${counts.abnormal}`,
        kind: 'account_abnormal',
        kind_label: '账号异常',
        level: 'warning',
        title: `${counts.abnormal} 个账号异常`,
        body: '要验证码 / 冻结 / 失效的号不再替它执行发送。',
        link: '/accounts',
        read: false,
        created_at: stamp,
      });
    }
    if (staleWorkers > 0) {
      items.push({
        id: `derived-worker:${staleWorkers}`,
        kind: 'worker_lost',
        kind_label: 'Worker 心跳',
        level: 'warning',
        title: `${staleWorkers} 个 Worker 超过 60 秒没有心跳`,
        body: '先看 Worker 进程是否还在；单个号异常只清它的租约，不要重启全部连接。',
        link: '/',
        read: false,
        created_at: stamp,
      });
    }
    if (counts.overdue > 0) {
      items.push({
        id: `derived-overdue:${counts.overdue}`,
        kind: 'task_overdue',
        kind_label: '任务逾期',
        level: 'warning',
        title: `${counts.overdue} 个任务到期未执行`,
        body: '检查 Worker 是否在认领任务。',
        link: '/tasks',
        read: false,
        created_at: stamp,
      });
    }
    return items;
  }, [counts.abnormal, counts.failed, counts.overdue, data?.generated_at, staleWorkers]);

  const allNotifications = notificationsError || !notificationsQuery.data ? derived : notificationsQuery.data;
  // 已读记忆：通知点掉之后不能再冒出来（刷新、轮询都算）。
  // 通知本身是按当前状态实时派生的，所以「已读」存在本地；id 里带了数量，
  // 数量变化（比如又失败了一个任务）就是一条新提醒，会重新出现。
  const [readNoticeIds, setReadNoticeIds] = useState<string[]>(() => {
    const stored = readJson<string[]>(NOTICE_READ_KEY, []);
    return Array.isArray(stored) ? stored : [];
  });
  const rememberRead = useCallback(
    (ids: string[]) => {
      setReadNoticeIds((current: string[]) => {
        const merged = Array.from(new Set([...current, ...ids])).slice(-NOTICE_READ_LIMIT);
        writeJson(NOTICE_READ_KEY, merged);
        return merged;
      });
    },
    [],
  );
  // 读过的直接不再显示（角标也只算未读的那部分）
  const notifications = allNotifications.filter((item) => !item.read && !readNoticeIds.includes(item.id));
  const unreadNotifications = notifications.length;

  const refreshNotifications = useCallback(() => {
    void notificationsQuery.reload();
  }, [notificationsQuery]);

  const markRead = useCallback(
    async (id: string) => {
      // 派生通知没有后端记录，直接在本地记住已读（以前这里直接 return，所以点掉又回来）
      rememberRead([id]);
      if (id.startsWith('derived-')) return;
      try {
        await notificationApi.markRead(id);
        notificationsQuery.setData((current) =>
          (current ?? []).map((item) => (item.id === id ? { ...item, read: true } : item)),
        );
      } catch (err) {
        // 标记失败不打扰用户：下次轮询会再同步一次状态
        if (!(err instanceof ApiError)) throw err;
      }
    },
    [notificationsQuery, rememberRead],
  );

  const markAllRead = useCallback(async () => {
    // 先把当前列表整体记为已读，无论后端有没有通知接口
    rememberRead(notifications.map((item) => item.id));
    try {
      await notificationApi.markAllRead();
      notificationsQuery.setData((current) => (current ?? []).map((item) => ({ ...item, read: true })));
    } catch {
      /* 后端不可用时保持原状 */
    }
  }, [notificationsQuery]);

  return {
    dashboard: data,
    counts,
    workers,
    staleWorkers,
    generatedAt: data?.generated_at,
    loading: dashboard.loading,
    error: dashboard.error,
    reload: () => {
      void dashboard.reload();
    },
    notifications,
    unreadNotifications,
    notificationsAreDerived: Boolean(notificationsError) || apiMissing || !notificationsQuery.data,
    notificationsLoading: notificationsQuery.loading,
    refreshNotifications,
    markRead,
    markAllRead,
  };
}
