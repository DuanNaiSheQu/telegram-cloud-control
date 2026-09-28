/**
 * DevComponentPreview —— 组件库预览页（**仅开发环境注册路由**，生产构建不挂载）。
 *
 * 用途：
 *  1. 页面负责人在 `npm run dev` 下打开 http://127.0.0.1:5173/__components
 *     就能看到所有共享组件的真实样子（深色 / 浅色都切一遍），照着 props 契约直接用；
 *  2. 改 tokens.ts 后刷新这个页面，可以立刻确认换皮是否整体生效。
 *
 * 注意：这里的数据全是本地 mock，不打后端；不进侧栏、不进生产。
 */
import { useState } from 'react';
import { Button, Input, Select, Space, Switch } from 'antd';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExclamationCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import PageContainer, { StatGrid } from './PageContainer';
import StatCard from './StatCard';
import SectionCard from './SectionCard';
import DataTable from './DataTable';
import FilterBar from './FilterBar';
import EmptyState from './EmptyState';
import ErrorState from './ErrorState';
import StatusBadge from './StatusBadge';
import StatusDot from './StatusDot';
import { CurrentTaskTag, MessageStatusTag, TaskStatusTag, TaskTypeTag } from './TaskStatusTag';
import CopyableText from './CopyableText';
import RelativeTime from './RelativeTime';
import TrendSparkline from './TrendSparkline';
import ConfirmModal from './ConfirmModal';
import DetailDrawer from './DetailDrawer';
import { CardSkeleton, TableSkeleton, ListSkeleton, ChartSkeleton } from './LoadingSkeleton';
import { toast } from '../utils/feedback';
import type { AccountStatus, TaskStatus } from '../api/types';

const ACCOUNT_STATUSES: AccountStatus[] = [
  'healthy',
  'pending',
  'needs_code',
  'frozen',
  'invalid',
  'dead',
  'disabled',
];

const TASK_STATUSES: TaskStatus[] = [
  'pending',
  'pending_confirmation',
  'running',
  'completed',
  'failed',
  'cancelled',
];

interface MockRow {
  id: string;
  phone: string;
  status: AccountStatus;
  statusLabel: string;
  task: TaskStatus;
  group: string;
  heartbeat: string;
  age: number;
}

const MOCK_ROWS: MockRow[] = [
  { id: 'a1', phone: '861****2551', status: 'healthy', statusLabel: '正常', task: 'running', group: '值班一组', heartbeat: new Date(Date.now() - 42_000).toISOString(), age: 428 },
  { id: 'a2', phone: '861****7734', status: 'needs_code', statusLabel: '要验证码', task: 'pending_confirmation', group: '值班一组', heartbeat: new Date(Date.now() - 190_000).toISOString(), age: 96 },
  { id: 'a3', phone: '861****0129', status: 'frozen', statusLabel: '冻结', task: 'failed', group: '备用号', heartbeat: new Date(Date.now() - 3_600_000).toISOString(), age: 1204 },
  { id: 'a4', phone: '861****5566', status: 'dead', statusLabel: '永久双向', task: 'completed', group: '备用号', heartbeat: null, age: 30 } as unknown as MockRow,
];

export function DevComponentPreview() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(true);

  return (
    <PageContainer
      title="共享组件库预览（仅开发环境）"
      description="页面负责人按需取用；改动 theme/tokens.ts 后刷新本页即可确认换皮是否整体生效。生产构建不会注册这个路由。"
      actions={
        <Space>
          <Button onClick={() => toast.success('操作成功')}>成功提示</Button>
          <Button onClick={() => toast.warning('该账号需要验证码')}>警告提示</Button>
          <Button danger onClick={() => toast.error('无法连接后端服务，请确认 API 已启动')}>
            失败提示
          </Button>
          <Button onClick={() => setConfirmOpen(true)}>二次确认</Button>
          <Button type="primary" onClick={() => setDrawerOpen(true)}>
            详情抽屉
          </Button>
        </Space>
      }
    >
      <StatGrid>
        <StatCard title="在线账号" value={12} unit="个" tone="success" icon={<CheckCircleOutlined />} trend={[4, 6, 5, 8, 9, 11, 12]} hint="租约有效且心跳正常" />
        <StatCard title="异常账号" value={3} tone="danger" icon={<ExclamationCircleOutlined />} delta={{ value: 12.5, suffix: '%', goodWhen: 'down' }} trend={[1, 2, 2, 3, 5, 4, 3]} />
        <StatCard title="失败任务" value={1} tone="warning" icon={<ReloadOutlined />} delta={{ value: -50, suffix: '%', goodWhen: 'down' }} />
        <StatCard title="检测耗时 P95" value={860} unit="ms" tone="info" icon={<ClockCircleOutlined />} trend={[920, 880, 900, 870, 860]} />
        <StatCard title="加载中" value={0} loading />
      </StatGrid>

      <SectionCard
        title="筛选栏 + 数据表格"
        subtitle="DataTable 支持分页/排序/密度/列设置/导出按钮位；筛选栏可折叠并显示已选条件"
        extra={<Button onClick={() => setCollapsed((v) => !v)}>切换折叠</Button>}
        bodyPadding="none"
      >
        <div style={{ padding: 'var(--tg-space-lg) var(--tg-layout-card-padding)' }}>
          <FilterBar
            collapsible
            defaultCollapsed={collapsed}
            onReset={() => toast.info('已重置筛选')}
            onSearch={() => toast.info('查询')}
            activeFilters={[
              { key: 'status', label: '状态', value: '要验证码', onRemove: () => undefined },
              { key: 'group', label: '分组', value: '值班一组', onRemove: () => undefined },
            ]}
          >
            <Input placeholder="手机号 / 用户名" style={{ width: 200 }} allowClear />
            <Select placeholder="状态" style={{ width: 140 }} options={[{ value: 'healthy', label: '正常' }]} />
            <Select placeholder="分组" style={{ width: 140 }} options={[{ value: 'g1', label: '值班一组' }]} />
          </FilterBar>
        </div>
        <DataTable<MockRow>
          rowKey="id"
          dataSource={MOCK_ROWS}
          columnSettingsKey="dev_preview"
          title="账号表"
          total={MOCK_ROWS.length}
          page={1}
          pageSize={20}
          scrollX={1000}
          onExport={() => toast.success('已触发导出（此处仅演示按钮位）')}
          columns={[
            { title: '手机号', dataIndex: 'phone', key: 'phone', render: (v: string) => <CopyableText value={v} /> },
            {
              title: '状态',
              dataIndex: 'status',
              key: 'status',
              render: (_: unknown, row) => <StatusBadge status={row.status} label={row.statusLabel} reason="示例原因" />,
            },
            { title: '当前任务', dataIndex: 'task', key: 'task', render: (v: TaskStatus) => <TaskStatusTag status={v} /> },
            { title: '分组', dataIndex: 'group', key: 'group' },
            { title: '号龄', dataIndex: 'age', key: 'age', render: (v: number) => `${v} 天` },
            {
              title: '最后心跳',
              dataIndex: 'heartbeat',
              key: 'heartbeat',
              render: (v: string | null) => <RelativeTime value={v} />,
            },
            {
              title: '操作',
              key: 'actions',
              fixed: 'right',
              width: 120,
              render: () => <Button type="link" size="small">检测</Button>,
            },
          ]}
        />
      </SectionCard>

      <SectionCard title="状态与标签" subtitle="账号 7 态 / 任务状态 / 消息状态 / 所有语义色">
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            {ACCOUNT_STATUSES.map((status) => (
              <StatusBadge key={status} status={status} />
            ))}
          </div>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            {ACCOUNT_STATUSES.map((status) => (
              <StatusDot key={status} status={status} label={status} />
            ))}
          </div>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            {TASK_STATUSES.map((status) => (
              <TaskStatusTag key={status} status={status} />
            ))}
          </div>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            <TaskTypeTag type="sync_dialogs" />
            <TaskTypeTag type="send_message" />
            <CurrentTaskTag task="idle" />
            <CurrentTaskTag task="syncing" />
            <CurrentTaskTag task="awaiting_confirm" />
            <MessageStatusTag status="sent" />
            <MessageStatusTag status="failed" />
          </div>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            <StatusDot tone="primary" label="primary" pulse />
            <StatusDot tone="success" label="success" />
            <StatusDot tone="warning" label="warning" pulse />
            <StatusDot tone="danger" label="danger" />
            <StatusDot tone="info" label="info" />
            <StatusDot tone="neutral" label="neutral" />
          </div>
          <div className="tg-flex" style={{ flexWrap: 'wrap' }}>
            <CopyableText value="8613800002551" mono />
            <CopyableText value="0f3d2c1b-9a8e-4f7c-b6d5-1e2f3a4b5c6d" mono maxLength={20} />
            <RelativeTime value={new Date(Date.now() - 90_000).toISOString()} />
            <span className="tg-muted">|</span>
            <RelativeTime value={new Date(Date.now() - 90_000).toISOString()} showAbsolute />
          </div>
        </div>
      </SectionCard>

      <div style={{ display: 'grid', gap: 'var(--tg-layout-page-gap)', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
        <SectionCard title="空态" subtitle="EmptyState（插画 + 引导按钮）">
          <EmptyState
            art="accounts"
            title="还没有账号"
            description="先建一个号，再用这个号自己的验证码登录。"
            action={<Button type="primary">新建账号</Button>}
            secondaryAction={<Button type="text">查看接入说明</Button>}
          />
        </SectionCard>

        <SectionCard title="失败态" subtitle="ErrorState（带重试，绝不白屏）">
          <ErrorState error="无法连接后端服务，请确认 API 已启动" onRetry={() => toast.info('重试')} />
        </SectionCard>

        <SectionCard title="趋势迷你图" subtitle="TrendSparkline（纯 SVG，无图表库）">
          <div className="tg-stack">
            <TrendSparkline data={[3, 5, 4, 8, 6, 9, 12]} color="var(--tg-color-chart-2)" height={56} />
            <TrendSparkline data={[9, 8, 8, 6, 5, 4, 3]} color="var(--tg-color-chart-5)" height={56} />
            <TrendSparkline data={[]} height={56} />
          </div>
        </SectionCard>

        <SectionCard title="骨架屏" subtitle="卡片 / 表格 / 列表 / 图表">
          <div className="tg-stack" style={{ gap: 'var(--tg-space-xxl)' }}>
            <CardSkeleton rows={2} />
            <TableSkeleton rows={3} columns={4} />
            <ListSkeleton rows={2} />
            <ChartSkeleton height={120} />
          </div>
        </SectionCard>

        <SectionCard title="加载 / 失败 / 空 三态容器" subtitle="SectionCard 自带 loading / error / empty 切换">
          <Space direction="vertical" style={{ width: '100%' }}>
            <Switch checkedChildren="空态" unCheckedChildren="空态" defaultChecked />
          </Space>
          <div style={{ marginTop: 'var(--tg-space-lg)' }}>
            <SectionCard loading skeletonRows={3} title={undefined} />
          </div>
        </SectionCard>

        <SectionCard title="Toast 统一封装" subtitle="utils/feedback 的 toast（自动去重 2 秒）">
          <Space wrap>
            <Button icon={<ThunderboltOutlined />} onClick={() => toast.success('已同步 3 个会话')}>
              成功
            </Button>
            <Button onClick={() => toast.warning('登录已过期，请重新登录')}>警告</Button>
            <Button danger onClick={() => toast.error('没有权限执行该操作')}>
              失败
            </Button>
            <Button onClick={() => toast.info('已复制')}>信息</Button>
            <Button onClick={() => toast.notify('error', '任务失败', { description: '单条发送：账号不在正常状态' })}>
              横幅通知
            </Button>
          </Space>
        </SectionCard>
      </div>

      <ConfirmModal
        open={confirmOpen}
        danger
        title="停用这 3 个账号？"
        content={<div>861****2551、861****7734、861****0129</div>}
        description="停用后不再认领任务，租约立即释放；可随时重新启用。"
        confirmPhrase="确认停用"
        okText="停用"
        onOk={() => {
          setConfirmOpen(false);
          toast.success('已停用 3 个账号');
        }}
        onCancel={() => setConfirmOpen(false)}
      />

      <DetailDrawer
        open={drawerOpen}
        title="861****2551"
        subtitle={<StatusBadge status="healthy" label="正常" />}
        onClose={() => setDrawerOpen(false)}
        sections={[
          {
            title: '基本信息',
            items: [
              { label: '用户名', value: '@example_user' },
              { label: '用户 ID', value: '8613800002551', copyable: true, mono: true },
              { label: '号龄', value: '428 天' },
              { label: '分组', value: '值班一组' },
              { label: '代理', value: 'hk-socks5（socks5://10.0.0.2:1080）' },
              { label: '最后心跳', value: <RelativeTime value={new Date(Date.now() - 42_000).toISOString()} /> },
              { label: '备注', value: '长文本溢出示例：这是一段很长的备注……', span: 'full' },
            ],
          },
          {
            title: '会话统计',
            items: [
              { label: '群聊', value: 18 },
              { label: '私信', value: 6 },
              { label: '未读', value: 2 },
            ],
          },
        ]}
        footer={
          <Space>
            <Button danger>停用</Button>
            <Button>清除租约</Button>
            <Button type="primary">单号检测</Button>
          </Space>
        }
      />
    </PageContainer>
  );
}

export default DevComponentPreview;
