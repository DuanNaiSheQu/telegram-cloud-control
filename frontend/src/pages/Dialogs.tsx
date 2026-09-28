/**
 * 会话（专业 IM 收件箱）：
 *  左栏 —— 会话列表（渠道色条 / 未读角标 / 预览 / 搜索 / 筛选 / 排序 / 滚动加载）；
 *  右栏 —— 消息流（正序气泡 / 日期分隔 / 未读分隔线 / 失败重发 / 无限上翻 / 会话内搜索 / 跳到底部）
 *          + 输入区（AI 草稿 / 二分支发送提示 / Ctrl/⌘+Enter）+ 顶部操作（同步历史 / 标记已读 / 会话信息）。
 *  双栏宽度可拖动；WebSocket 只订阅当前打开的会话，多会话不串消息。
 *  按规划「不做批量群发 / 批量私信」——本页不提供任何批量发送入口。
 */
import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react';
import { PageHeader } from '../components';
import { accountApi, botApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { useLocalStorage } from '../hooks/useLocalStorage';
import { useBreakpoint } from '../hooks/useMediaQuery';
import { useDialogList } from '../features/dialogs/useDialogList';
import { useChatRoom } from '../features/dialogs/useChatRoom';
import { DialogListPane } from '../features/dialogs/DialogListPane';
import { ChatPane } from '../features/dialogs/ChatPane';
import {
  IM_LIST_DEFAULT,
  IM_LIST_MAX,
  IM_LIST_MIN,
  IM_LIST_WIDTH_KEY,
} from '../features/dialogs/types';
import '../features/dialogs/dialogs.css';
import type { DialogOut } from '../api/types';

export default function Dialogs() {
  const list = useDialogList();
  const { isNarrow } = useBreakpoint();

  const [activeDialog, setActiveDialog] = useState<DialogOut | null>(null);
  const [listWidth, setListWidth] = useLocalStorage<number>(IM_LIST_WIDTH_KEY, IM_LIST_DEFAULT);
  const [dragging, setDragging] = useState(false);
  const activeIdRef = useRef<string | null>(null);

  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }, { silent: true }), []);
  const bots = useAsyncData(async () => {
    try {
      return await botApi.list();
    } catch {
      return [];
    }
  }, []);

  const room = useChatRoom(activeDialog, (patch) => {
    if (activeIdRef.current) list.patchItem(activeIdRef.current, patch);
  });

  useEffect(() => {
    activeIdRef.current = activeDialog?.id ?? null;
  }, [activeDialog]);

  const openDialog = (dialog: DialogOut) => {
    setActiveDialog({ ...dialog });
  };

  // ---------- 双栏拖宽 ----------

  const handleGripDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (isNarrow) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = listWidth;
    setDragging(true);
    const onMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      setListWidth(Math.min(IM_LIST_MAX, Math.max(IM_LIST_MIN, startWidth + delta)));
    };
    const onUp = () => {
      setDragging(false);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  };

  return (
    <div className="tg-page">
      <PageHeader
        title="会话"
        description="群聊与私信的统一收件箱：左侧选会话，右侧回消息；新消息实时推送，发送走用户号任务队列或 Bot 直发。"
      />

      <div
        className="im-workspace"
        style={{ ['--im-list-width' as string]: `${listWidth}px` }}
      >
        <DialogListPane
          items={list.items}
          total={list.total}
          loading={list.loading}
          loadingMore={list.loadingMore}
          error={list.error}
          filters={list.filters}
          onFiltersChange={list.setFilters}
          onResetFilters={list.resetFilters}
          activeCount={list.activeCount}
          sortOrder={list.sortOrder}
          onToggleSort={list.toggleSort}
          onReload={list.reload}
          onLoadMore={list.loadMore}
          activeId={activeDialog?.id ?? null}
          onOpen={openDialog}
          accountOptions={(accounts.data?.items ?? []).map((item) => ({
            value: item.id,
            label: `${item.phone_masked}${item.remark ? `（${item.remark}）` : ''}`,
          }))}
          botOptions={(bots.data ?? []).map((bot) => ({
            value: bot.id,
            label: bot.bot_username ? `@${bot.bot_username}` : bot.name,
          }))}
          wsStatus={room.wsStatus}
        />

        <div
          className={['im-grip', dragging ? 'is-dragging' : ''].filter(Boolean).join(' ')}
          onMouseDown={handleGripDown}
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整列表宽度"
        />

        <ChatPane room={room} />
      </div>
    </div>
  );
}
