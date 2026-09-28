/**
 * Bot 转发页：转发规则列表 + 新建/编辑（带测试消息）+ 删除/停用 +
 * 已转发记录表（原消息正文/发送人/会话/员工群那条 ID，来自 /api/relays/links 新字段）+
 * 记录详情抽屉（跳原会话）。
 * 全部颜色/间距走 var(--tg-*)，表格/筛选/空态用共享组件。
 */
import { useMemo, useState } from 'react';
import { Button, Select, Space, Switch, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  ConfirmModal,
  CopyableText,
  DataTable,
  FilterBar,
  PageContainer,
  RelativeTime,
  SoftTag,
  StatCard,
  StatGrid,
} from '../components';
import { accountApi, botApi, dialogApi, relayApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { buildActiveFilters, useTableQuery } from '../hooks/useTableQuery';
import { formatNumber, shortId } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import { useAuth } from '../auth/AuthContext';
import type { RelayRouteOut, RelayTargetKind } from '../api/types';
import { LinkDetailDrawer } from '../features/relay/LinkDetailDrawer';
import { RelayRouteFormModal } from '../features/relay/RelayRouteFormModal';
import { TestMessageModal } from '../features/relay/TestMessageModal';
import { botLabel, type RelayLinkItem } from '../features/relay/types';

export default function Relay() {
  const { isAdmin } = useAuth();
  const routes = useAsyncData(() => relayApi.list(), []);
  const bots = useAsyncData(() => botApi.list(), []);
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), []);
  const dialogs = useAsyncData(() => dialogApi.list({ page: 1, page_size: 200 }), []);

  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<RelayRouteOut | null>(null);
  const [testRoute, setTestRoute] = useState<RelayRouteOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RelayRouteOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [toggleBusyId, setToggleBusyId] = useState<string | null>(null);
  const [detailLink, setDetailLink] = useState<RelayLinkItem | null>(null);

  const linksQuery = useTableQuery({ filters: { route_id: '' as string }, pageSize: 20 });
  const links = useAsyncData(
    () =>
      relayApi.links({
        route_id: linksQuery.filters.route_id || null,
        page: linksQuery.page,
        page_size: linksQuery.pageSize,
      }),
    [linksQuery.paramsKey],
  );

  const routeList = useMemo(() => routes.data ?? [], [routes.data]);
  const botList = useMemo(() => bots.data ?? [], [bots.data]);

  const totalRelayed = useMemo(
    () => routeList.reduce((sum, item) => sum + (item.relayed_count || 0), 0),
    [routeList],
  );
  const enabledCount = useMemo(() => routeList.filter((item) => item.enabled).length, [routeList]);

  const handleToggle = async (record: RelayRouteOut, checked: boolean) => {
    setToggleBusyId(record.id);
    try {
      await relayApi.update(record.id, { enabled: checked });
      notifySuccess(checked ? '规则已启用' : '规则已停用');
      void routes.reload();
    } catch {
      /* client 已统一中文提示 */
    } finally {
      setToggleBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await relayApi.remove(deleteTarget.id);
      notifySuccess(res.message || '规则已删除');
      setDeleteTarget(null);
      void routes.reload();
    } catch {
      /* client 已统一中文提示 */
    } finally {
      setDeleting(false);
    }
  };

  const routeColumns: ColumnsType<RelayRouteOut> = [
    {
      title: '规则',
      dataIndex: 'name',
      width: 170,
      render: (value: string, record) => (
        <div className="tg-stack">
          <span className="tg-nowrap">{value || `规则 ${shortId(record.id, 6)}`}</span>
          {record.remark ? (
            <Typography.Text type="secondary" className="ellipsis" title={record.remark}>
              {record.remark}
            </Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: 'Bot',
      dataIndex: 'bot_name',
      width: 170,
      render: (value: string | null, record) => (
        <div className="tg-stack">
          <span>{value || '—'}</span>
          {record.bot_username ? (
            <Typography.Text code>@{record.bot_username}</Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '员工群 chat_id',
      dataIndex: 'staff_chat_id',
      width: 200,
      render: (value: number, record) => (
        <div className="tg-stack">
          <CopyableText value={value} mono />
          {record.staff_chat_title ? (
            <Typography.Text type="secondary" className="ellipsis" title={record.staff_chat_title}>
              {record.staff_chat_title}
            </Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '目标类型',
      dataIndex: 'target_kind',
      width: 90,
      render: (value: RelayTargetKind) => (
        <SoftTag tone="info">{value === 'private' ? '私聊' : '群聊'}</SoftTag>
      ),
    },
    {
      title: '来源过滤',
      key: 'source',
      width: 210,
      render: (_: unknown, record) => (
        <div className="tg-stack">
          <span>
            <SoftTag tone={record.account_id ? 'primary' : 'neutral'}>
              {record.account_label ? `账号 ${record.account_label}` : '全部账号'}
            </SoftTag>
          </span>
          <span>
            <SoftTag tone={record.dialog_id ? 'primary' : 'neutral'}>
              {record.dialog_title ? `会话 ${record.dialog_title}` : '全部会话'}
            </SoftTag>
          </span>
        </div>
      ),
    },
    {
      title: '已转发',
      dataIndex: 'relayed_count',
      width: 90,
      align: 'right',
      render: (value: number) => <span className="tg-num">{formatNumber(value)}</span>,
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 80,
      render: (value: boolean, record) => (
        <Tooltip title={isAdmin ? undefined : '仅管理员可启用/停用规则'}>
          <Switch
            size="small"
            checked={value}
            disabled={!isAdmin}
            loading={toggleBusyId === record.id}
            onChange={(checked) => void handleToggle(record, checked)}
          />
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 140,
      render: (value: string | null) => <RelativeTime value={value} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      fixed: 'right',
      render: (_: unknown, record) => (
        <Space size="small" wrap>
          <Tooltip title="查看这条规则已转发的记录">
            <Button size="small" icon={<LinkOutlined />} onClick={() => linksQuery.setFilter('route_id', record.id)}>
              记录
            </Button>
          </Tooltip>
          <Tooltip title={isAdmin ? '用这条规则的 Bot 发一条测试消息' : '仅管理员可发送测试消息'}>
            <Button
              size="small"
              icon={<ExperimentOutlined />}
              disabled={!isAdmin}
              onClick={() => setTestRoute(record)}
            >
              测试
            </Button>
          </Tooltip>
          <Tooltip title={isAdmin ? undefined : '仅管理员可编辑规则'}>
            <Button size="small" icon={<EditOutlined />} disabled={!isAdmin} onClick={() => setEditing(record)}>
              编辑
            </Button>
          </Tooltip>
          <Tooltip title={isAdmin ? undefined : '仅管理员可删除规则'}>
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={!isAdmin}
              onClick={() => setDeleteTarget(record)}
            >
              删除
            </Button>
          </Tooltip>
        </Space>
      ),
    },
  ];

  const linkColumns: ColumnsType<RelayLinkItem> = [
    {
      title: '时间',
      key: 'origin_created_at',
      width: 140,
      render: (_: unknown, record) => (
        <RelativeTime value={record.origin_created_at ?? record.created_at} />
      ),
    },
    {
      title: '原消息正文',
      key: 'origin_body',
      width: 240,
      render: (_: unknown, record) =>
        record.origin_body ? (
          <Tooltip title={record.origin_body}>
            <span className="tg-clamp-2" style={{ color: 'var(--tg-color-text-primary)' }}>
              {record.origin_body}
            </span>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: '发送人',
      key: 'origin_sender_name',
      width: 130,
      render: (_: unknown, record) => record.origin_sender_name || '—',
    },
    {
      title: '会话',
      key: 'origin_dialog_title',
      width: 180,
      render: (_: unknown, record) => (
        <div className="tg-stack">
          <span className="ellipsis" title={record.origin_dialog_title ?? undefined}>
            {record.origin_dialog_title || '—'}
          </span>
          {record.account_label ? (
            <Typography.Text type="secondary">{record.account_label}</Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '员工群那条 ID',
      dataIndex: 'staff_message_id',
      width: 150,
      render: (value: number) => <CopyableText value={value} mono />,
    },
    {
      title: '员工群 chat_id',
      dataIndex: 'staff_chat_id',
      width: 150,
      render: (value: number) => <CopyableText value={value} mono />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      fixed: 'right',
      render: (_: unknown, record) => (
        <Button size="small" onClick={() => setDetailLink(record)}>
          详情
        </Button>
      ),
    },
  ];

  const routeOptions = routeList.map((item) => ({
    value: item.id,
    label: item.name || `规则 ${shortId(item.id, 6)}`,
  }));

  return (
    <PageContainer
      title="Bot 转发"
      description="把账号收到的消息按规则用 Bot 转发到员工群，并保留「原消息 ↔ 员工群那条」的对应关系。"
      actions={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            loading={routes.loading}
            onClick={() => {
              void routes.reload();
              void bots.reload();
              void links.reload();
            }}
          >
            刷新
          </Button>
          <Tooltip title={isAdmin ? undefined : '仅管理员可新建规则'}>
            <Button type="primary" icon={<PlusOutlined />} disabled={!isAdmin} onClick={() => setCreateOpen(true)}>
              新建规则
            </Button>
          </Tooltip>
        </Space>
      }
    >
      <StatGrid>
        <StatCard title="规则总数" value={routeList.length} tone="neutral" />
        <StatCard title="启用中" value={enabledCount} tone="primary" />
        <StatCard title="累计转发" value={totalRelayed} tone="success" />
      </StatGrid>

      <DataTable<RelayRouteOut>
        rowKey="id"
        columns={routeColumns}
        dataSource={routeList}
        loading={routes.loading}
        error={routes.error}
        onRetry={() => void routes.reload()}
        columnSettingsKey="relay-routes"
        scrollX={1500}
        empty={{
          art: 'list',
          title: '还没有转发规则',
          description: '建一条规则，把账号收到的消息用 Bot 自动转发到员工群。',
          action: isAdmin ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建规则
            </Button>
          ) : undefined,
          secondaryAction: botList.length ? undefined : (
            <Link to="/bots">
              <Button>先去 Bot 管理创建 Bot</Button>
            </Link>
          ),
        }}
      />

      <DataTable<RelayLinkItem>
        title="已转发记录"
        rowKey="id"
        columns={linkColumns}
        dataSource={links.data?.items ?? []}
        total={links.data?.total ?? 0}
        page={linksQuery.page}
        pageSize={linksQuery.pageSize}
        onPageChange={linksQuery.setPage}
        loading={links.loading}
        error={links.error}
        onRetry={() => void links.reload()}
        columnSettingsKey="relay-links"
        scrollX={1200}
        toolbar={
          <FilterBar
            onReset={linksQuery.reset}
            onSearch={() => void links.reload()}
            loading={links.loading}
            activeFilters={buildActiveFilters([
              {
                key: 'route_id',
                label: '规则',
                display: routeOptions.find((item) => item.value === linksQuery.filters.route_id)?.label,
                clear: () => linksQuery.setFilter('route_id', ''),
              },
            ])}
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="全部规则"
              style={{ width: 240 }}
              value={linksQuery.filters.route_id || undefined}
              onChange={(value) => linksQuery.setFilter('route_id', value ?? '')}
              options={routeOptions}
            />
          </FilterBar>
        }
        empty={{
          art: 'inbox',
          title: '还没有转发记录',
          description: '规则命中并成功转发后，原消息与员工群里那条的对应关系会记录在这里。',
        }}
      />

      <RelayRouteFormModal
        open={createOpen || Boolean(editing)}
        route={editing}
        bots={botList.map((bot) => ({
          value: bot.id,
          label: botLabel(bot.name, bot.bot_username),
          name: bot.name,
          username: bot.bot_username ?? undefined,
        }))}
        accounts={(accounts.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.phone_masked}${item.username ? ` / ${item.username}` : ''}`,
          name: item.phone_masked,
        }))}
        dialogs={(dialogs.data?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.title || item.peer_display || item.tg_chat_id}（${
            item.channel === 'bot' ? 'Bot' : '用户号'
          }）`,
          name: item.title,
        }))}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void routes.reload();
        }}
      />

      <TestMessageModal
        open={Boolean(testRoute)}
        botId={testRoute?.bot_id ?? null}
        chatId={testRoute?.staff_chat_id ?? null}
        botLabel={testRoute ? botLabel(testRoute.bot_name, testRoute.bot_username) : undefined}
        onClose={() => setTestRoute(null)}
      />

      <ConfirmModal
        open={Boolean(deleteTarget)}
        danger
        loading={deleting}
        title={`删除转发规则「${deleteTarget?.name || shortId(deleteTarget?.id ?? '', 6)}」？`}
        content="已转发的记录会保留，但这条规则不会再转发新消息。"
        okText="删除"
        onOk={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      <LinkDetailDrawer link={detailLink} onClose={() => setDetailLink(null)} />
    </PageContainer>
  );
}
