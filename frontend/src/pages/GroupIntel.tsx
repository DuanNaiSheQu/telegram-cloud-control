/**
 * 群情报（无感采集）：左边的群档案列表 + 右侧选中群的成员名单与入退群事件流。
 *
 * 采集是只读的：只调 GetFullChannel / GetParticipants，不发消息、不回应、不加群。
 * 入群/退群流水本身由 Worker 事件监听被动记录，这里只负责「看」和「手动补采」。
 */
import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Modal,
  Segmented,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CloudDownloadOutlined, FileZipOutlined, LinkOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Progress } from 'antd';
import { PageContainer, StatCard, StatGrid, RelativeTime, SoftTag } from '../components';
import { notifyError, toast } from '../utils/feedback';
import { downloadBlob, filenameFromDisposition } from '../utils/download';
import BulkResultModal from '../features/accounts/BulkResultModal';
import { groupIntelApi } from '../api/endpoints';
import { useAsyncData, useInterval } from '../hooks/useAsyncData';
import { notifySuccess } from '../utils/feedback';
import type {
  BulkResultOut,
  CollectJob,
  GroupEventOut,
  GroupMemberOut,
  GroupProfileOut,
} from '../api/types';

const KIND_LABEL: Record<string, string> = {
  group: '普通群',
  megagroup: '超级群',
  channel: '频道',
  chat: '群聊',
};

export default function GroupIntel() {
  const [keyword, setKeyword] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<GroupProfileOut | null>(null);
  const [memberScope, setMemberScope] = useState<'all' | 'human' | 'bot'>('all');
  const [collectOpen, setCollectOpen] = useState(false);
  const [collectBusy, setCollectBusy] = useState(false);
  const [collectForm] = Form.useForm();
  const [collectResult, setCollectResult] = useState<BulkResultOut | null>(null);
  // 按链接采集：粘贴群链接 → 自动解析 + 采群员
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkForm] = Form.useForm();

  const stats = useAsyncData(() => groupIntelApi.stats(), []);
  // 采集进度：进行中时每 5 秒刷新一次，避免黑盒等待
  const jobs = useAsyncData(() => groupIntelApi.jobs({ limit: 30 }), []);
  const [exporting, setExporting] = useState(false);
  useInterval(() => {
    if ((jobs.data?.summary.active ?? 0) > 0) void jobs.reload();
  }, 5000);
  const profiles = useAsyncData(
    () => groupIntelApi.profiles({ q: keyword || undefined, page, page_size: 20 }),
    [keyword, page],
  );
  const members = useAsyncData(
    () =>
      selected
        ? groupIntelApi.members(selected.id, {
            page: 1,
            page_size: 50,
            only_bots: memberScope === 'bot' || undefined,
            exclude_bots: memberScope === 'human' || undefined,
          })
        : Promise.resolve(null),
    [selected?.id, memberScope],
    { immediate: false },
  );
  const events = useAsyncData(
    () => groupIntelApi.events({ tg_chat_id: selected?.tg_chat_id, hours: 24 * 7, page_size: 50 }),
    [selected?.tg_chat_id],
  );

  useEffect(() => {
    if (selected) void members.reload();
  }, [selected?.id, memberScope]); // eslint-disable-line react-hooks/exhaustive-deps

  const runCollect = async () => {
    const values = collectForm.getFieldsValue() as {
      scope?: 'all' | 'group';
      limit_groups?: number;
      sample_members?: number;
      with_members?: boolean;
      member_limit?: number;
    };
    setCollectBusy(true);
    try {
      const res = await groupIntelApi.collect({
        scope: 'all',
        limit_groups: values.limit_groups ?? 30,
        sample_members: values.sample_members ?? 0,
        with_members: Boolean(values.with_members),
        member_limit: values.member_limit ?? 200,
      });
      setCollectOpen(false);
      setCollectResult(res);
      notifySuccess(res.message);
      void stats.reload();
      void profiles.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setCollectBusy(false);
    }
  };

  const runCollectByLink = async () => {
    const values = linkForm.getFieldsValue() as {
      links?: string;
      join_if_missing?: boolean;
      leave_after?: boolean;
      member_limit?: number;
    };
    const links = String(values.links ?? '')
      .split(/[\n\s]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!links.length) {
      toast.warning('先粘贴至少一个群链接');
      return;
    }
    setLinkBusy(true);
    try {
      const res = await groupIntelApi.collectByLink({
        scope: 'all',
        links,
        join_if_missing: Boolean(values.join_if_missing),
        leave_after: Boolean(values.leave_after),
        member_limit: values.member_limit ?? 200,
      });
      setLinkOpen(false);
      setCollectResult(res);
      notifySuccess(res.message);
      void stats.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setLinkBusy(false);
    }
  };

  const runExport = async (query?: { batch_id?: string; profile_ids?: string }) => {
    setExporting(true);
    try {
      const res = await groupIntelApi.exportZip({ ...query, include_events: true });
      const filename = filenameFromDisposition(null, 'group-intel.zip');
      downloadBlob(res.blob, filename);
      notifySuccess(`已打包 ${res.total ?? ''} 行数据，浏览器正在下载`);
    } catch {
      notifyError('打包导出失败，稍后重试');
    } finally {
      setExporting(false);
    }
  };

  const STAGE_LABEL: Record<string, string> = {
    queued: '排队中',
    resolving: '解析链接',
    resolved: '已定位群',
    joined: '已加入群',
    fetching: '采集中',
    done: '已完成',
    failed: '失败',
    cancelled: '已取消',
    running: '执行中',
  };

  const jobColumns: ColumnsType<CollectJob> = [
    {
      title: '目标',
      dataIndex: 'link',
      render: (value: string | null, record) => (
        <span className="tg-stack" style={{ gap: 2 }}>
          <span className="tg-ellipsis" style={{ maxWidth: 320, display: 'inline-block' }}>{value || record.title || '—'}</span>
          {record.title ? (
            <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>{record.title}</span>
          ) : null}
        </span>
      ),
    },
    { title: '执行号', dataIndex: 'account_label', width: 120 },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 110,
      render: (value: string) => (
        <SoftTag
          tone={value === 'done' ? 'success' : value === 'failed' ? 'danger' : value === 'fetching' ? 'info' : 'warning'}
          size="sm"
        >
          {STAGE_LABEL[value] ?? value}
        </SoftTag>
      ),
    },
    {
      title: '进度',
      dataIndex: 'fetched',
      width: 120,
      render: (value: number | null, record) => (
        <span className="tg-num">
          {value ?? 0}
          {record.target_count ? ` / ${record.target_count}` : ''}
        </span>
      ),
    },
    {
      title: '说明',
      dataIndex: 'detail',
      ellipsis: true,
      render: (value: string, record) =>
        record.error ? <span style={{ color: 'var(--tg-color-danger)' }}>{record.error}</span> : value || '—',
    },
    {
      title: '更新',
      dataIndex: 'updated_at',
      width: 120,
      render: (value: string | null, record) => <RelativeTime value={value ?? record.completed_at ?? record.created_at} />,
    },
  ];

  const profileColumns: ColumnsType<GroupProfileOut> = [
    {
      title: '群',
      dataIndex: 'title',
      render: (value: string, record) => (
        <span className="tg-stack" style={{ gap: 2 }}>
          <span style={{ fontWeight: 'var(--tg-font-weight-medium)' }}>{value || '未命名群'}</span>
          <span className="tg-muted" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
            {record.username ? `@${record.username}` : record.tg_chat_id}
          </span>
        </span>
      ),
    },
    { title: '类型', dataIndex: 'kind', width: 90, render: (value: string) => <Tag>{KIND_LABEL[value] ?? value}</Tag> },
    {
      title: '成员数',
      dataIndex: 'member_count',
      width: 90,
      render: (value: number | null) => <span className="tg-num">{value ?? '—'}</span>,
    },
    {
      title: '已采成员',
      dataIndex: 'member_sampled',
      width: 100,
      render: (value: number, record) => (
        <span>
          <span className="tg-num">{value}</span>
          {record.member_synced_at ? null : <Tag style={{ marginLeft: 6 }}>未同步</Tag>}
        </span>
      ),
    },
    {
      title: '采集时间',
      dataIndex: 'collected_at',
      width: 130,
      render: (value: string | null) => <RelativeTime value={value} />,
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (value: string) => (
        <SoftTag tone="neutral" size="sm">{value === 'join_event' ? '入群事件' : value === 'profile_sync' ? '资料同步' : value}</SoftTag>
      ),
    },
  ];

  const memberColumns: ColumnsType<GroupMemberOut> = [
    {
      title: '成员',
      dataIndex: 'display_name',
      render: (value: string, record) => (
        <span className="tg-stack" style={{ gap: 2 }}>
          <span>
            {value || '—'}
            {record.is_admin ? <Tag color="gold" style={{ marginLeft: 6 }}>管理员</Tag> : null}
            {record.is_bot ? <Tag style={{ marginLeft: 6 }}>机器人</Tag> : null}
            {record.is_premium ? <Tag color="purple" style={{ marginLeft: 6 }}>会员</Tag> : null}
          </span>
          <span className="tg-muted tg-mono" style={{ fontSize: 'var(--tg-font-size-xs)' }}>
            {record.username ? `@${record.username}` : record.tg_user_id}
          </span>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value: string) =>
        value === 'member' ? <SoftTag tone="success" size="sm">在群</SoftTag> : <SoftTag tone="danger" size="sm">{value === 'kicked' ? '被移除' : '已退群'}</SoftTag>,
    },
    { title: '来源', dataIndex: 'source', width: 110, render: (value: string) => (value === 'join_event' ? '入群事件' : value === 'message' ? '群内发言' : '名单同步') },
    { title: '入群时间', dataIndex: 'joined_at', width: 130, render: (value: string | null) => <RelativeTime value={value} /> },
    { title: '最近出现', dataIndex: 'last_seen_at', width: 130, render: (value: string | null) => <RelativeTime value={value} /> },
  ];

  const eventColumns: ColumnsType<GroupEventOut> = [
    {
      title: '类型',
      dataIndex: 'event_type_label',
      width: 100,
      render: (value: string, record) => (
        <SoftTag tone={record.event_type === 'join' || record.event_type === 'invite' ? 'success' : 'danger'} size="sm">
          {value}
        </SoftTag>
      ),
    },
    { title: '成员', dataIndex: 'user_display', render: (value: string, record) => value || record.username || record.tg_user_id || '—' },
    {
      title: '群',
      dataIndex: 'group_title',
      width: 180,
      ellipsis: true,
      render: (value: string | null) => value || <span className="tg-muted">—</span>,
    },
    {
      title: '被谁拉进来',
      dataIndex: 'actor_tg_id',
      width: 120,
      render: (value: number | null) => (value ? <span className="tg-mono">{value}</span> : <span className="tg-muted">自己进/退</span>),
    },
    { title: '时间', dataIndex: 'occurred_at', width: 130, render: (value: string | null) => <RelativeTime value={value} /> },
  ];

  return (
    <PageContainer
      title="群情报"
      description="入群即采：Worker 在事件回调里静默记录入群/退群，不发言、不回应；群资料与成员名单按需只读拉取。"
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { void stats.reload(); void profiles.reload(); void events.reload(); }}>
            刷新
          </Button>
          <Button icon={<LinkOutlined />} onClick={() => setLinkOpen(true)}>
            按链接采集
          </Button>
          <Button type="primary" icon={<CloudDownloadOutlined />} onClick={() => setCollectOpen(true)}>
            采集群情报
          </Button>
        </Space>
      }
    >
      <StatGrid>
        <StatCard title="已采群数" value={stats.data?.groups ?? 0} tone="primary" hint="有档案的群" />
        <StatCard title="已采成员" value={stats.data?.members ?? 0} tone="success" hint={`其中机器人 ${stats.data?.bots ?? 0} 个`} />
        <StatCard title="今日入群" value={stats.data?.joins_today ?? 0} tone="success" hint="含被邀请入群" />
        <StatCard title="今日退群" value={stats.data?.leaves_today ?? 0} tone={stats.data?.leaves_today ? 'warning' : 'neutral'} hint="含被移除" />
      </StatGrid>

      <Card
        size="small"
        title="采集进度"
        extra={
          <Space>
            <SoftTag tone="info" size="sm">进行中 {jobs.data?.summary.active ?? 0}</SoftTag>
            <SoftTag tone="success" size="sm">完成 {jobs.data?.summary.completed ?? 0}</SoftTag>
            {(jobs.data?.summary.failed ?? 0) > 0 ? (
              <SoftTag tone="danger" size="sm">失败 {jobs.data?.summary.failed ?? 0}</SoftTag>
            ) : null}
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void jobs.reload()}>
              刷新
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<FileZipOutlined />}
              loading={exporting}
              onClick={() => void runExport()}
            >
              打包导出
            </Button>
          </Space>
        }
      >
        <Progress
          percent={
            jobs.data && jobs.data.summary.total > 0
              ? Math.round((jobs.data.summary.completed / jobs.data.summary.total) * 100)
              : 0
          }
          size="small"
          status={(jobs.data?.summary.failed ?? 0) > 0 ? 'exception' : 'active'}
          format={(percent) =>
            `${percent}%（已采 ${jobs.data?.summary.members_collected ?? 0} 人，共 ${jobs.data?.summary.total ?? 0} 条任务）`
          }
        />
        <Table<CollectJob>
          size="small"
          rowKey="task_id"
          style={{ marginTop: 'var(--tg-space-md)' }}
          columns={jobColumns}
          dataSource={jobs.data?.jobs ?? []}
          loading={jobs.loading}
          pagination={{ pageSize: 6, size: 'small' }}
          locale={{ emptyText: '还没有采集任务：用「按链接采集」粘贴链接，或点「采集群情报」' }}
        />
      </Card>

      {stats.data && !stats.data.watching ? (
        <Alert
          type="warning"
          showIcon
          message="入群事件监听已关闭（GROUP_INTEL_WATCH_ENABLED=false）"
          description="关闭后只能手动采集，事件流不会自动积累。"
        />
      ) : null}

      <Card
        size="small"
        title="群档案"
        extra={
          <Space>
            <Segmented
              size="small"
              value={memberScope}
              onChange={(value) => setMemberScope(value as 'all' | 'human' | 'bot')}
              options={[
                { label: '全部成员', value: 'all' },
                { label: '只看真人', value: 'human' },
                { label: '只看机器人', value: 'bot' },
              ]}
            />
          </Space>
        }
      >
        <Space style={{ marginBottom: 'var(--tg-space-lg)' }} wrap>
          <input
            className="ant-input"
            style={{ width: 240, height: 'var(--tg-layout-control-height)' }}
            placeholder="按群名 / 用户名搜索"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setPage(1);
                void profiles.reload();
              }
            }}
          />
          <Button icon={<SearchOutlined />} onClick={() => { setPage(1); void profiles.reload(); }}>
            搜索
          </Button>
          <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
            共 {profiles.data?.total ?? 0} 个群；点一行看成员与事件
          </Typography.Text>
        </Space>

        <Table<GroupProfileOut>
          size="small"
          rowKey="id"
          columns={profileColumns}
          dataSource={profiles.data?.items ?? []}
          loading={profiles.loading}
          pagination={{
            current: page,
            pageSize: 20,
            total: profiles.data?.total ?? 0,
            showSizeChanger: false,
            onChange: setPage,
            size: 'small',
          }}
          onRow={(record) => ({ onClick: () => setSelected(record), style: { cursor: 'pointer' } })}
          rowClassName={(record) => (record.id === selected?.id ? 'ant-table-row-selected' : '')}
          locale={{ emptyText: '还没有群档案：点右上角「采集群情报」，或等入群事件自动积累' }}
        />
      </Card>

      {selected ? (
        <Card
          size="small"
          title={`${selected.title || '未命名群'} · 情报详情`}
          extra={
            <Space>
              <Button size="small" onClick={() => void runExport({ profile_ids: selected.id })} loading={exporting}>
                打包这个群
              </Button>
              <Button size="small" href={groupIntelApi.membersCsvUrl(selected.id)} target="_blank">
                导出成员 CSV
              </Button>
              <Button size="small" onClick={() => setSelected(null)}>
                关闭
              </Button>
            </Space>
          }
        >
          <Tabs
            size="small"
            items={[
              {
                key: 'members',
                label: `成员（${members.data?.total ?? selected.member_sampled}）`,
                children: (
                  <Table<GroupMemberOut>
                    size="small"
                    rowKey="id"
                    columns={memberColumns}
                    dataSource={members.data?.items ?? []}
                    loading={members.loading}
                    pagination={{ pageSize: 10, size: 'small' }}
                    locale={{ emptyText: '还没有成员数据：用「采集群情报」勾上「同时采成员名单」' }}
                  />
                ),
              },
              {
                key: 'events',
                label: `入退群（${events.data?.total ?? 0}）`,
                children: (
                  <Table<GroupEventOut>
                    size="small"
                    rowKey="id"
                    columns={eventColumns}
                    dataSource={events.data?.items ?? []}
                    loading={events.loading}
                    pagination={{ pageSize: 10, size: 'small' }}
                    locale={{ emptyText: '最近 7 天没有入退群事件' }}
                  />
                ),
              },
              {
                key: 'profile',
                label: '群资料',
                children: (
                  <div className="tg-stack" style={{ gap: 'var(--tg-space-md)' }}>
                    <div>群 ID：<span className="tg-mono">{selected.tg_chat_id}</span></div>
                    <div>类型：{KIND_LABEL[selected.kind] ?? selected.kind}{selected.is_public ? '（公开）' : '（私有）'}</div>
                    <div>成员数：{selected.member_count ?? '未知'}</div>
                    <div>邀请链接：{selected.invite_link ? <span className="tg-mono">{selected.invite_link}</span> : <span className="tg-muted">未采集到（需要管理员权限）</span>}</div>
                    <div>简介：{selected.about || <span className="tg-muted">—</span>}</div>
                    <div>采集时间：<RelativeTime value={selected.collected_at} /></div>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      ) : null}

      <Modal
        open={collectOpen}
        title="采集群情报"
        okText="开始采集"
        cancelText="取消"
        confirmLoading={collectBusy}
        onCancel={() => setCollectOpen(false)}
        onOk={() => void runCollect()}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Alert
            type="info"
            showIcon
            message="只读采集，不会在群里留下任何痕迹"
            description="对账号选择范围内全部可见账号执行：读取它们已加入群的资料；开启成员名单后会按页拉取（页间有间隔、单群有上限）。"
          />
          <Form form={collectForm} layout="vertical" initialValues={{ limit_groups: 30, sample_members: 0, with_members: false, member_limit: 200 }}>
            <Form.Item label="每个号最多采多少个群" name="limit_groups">
              <InputNumber min={1} max={300} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item label="每群顺带抽样多少个成员（0 = 只采群档案）" name="sample_members">
              <InputNumber min={0} max={500} style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="with_members" valuePropName="checked">
              <Checkbox>同时为每个群排队「采集群成员」任务（拉更大名单，速度慢一些）</Checkbox>
            </Form.Item>
            <Form.Item label="成员任务每群上限" name="member_limit">
              <InputNumber min={1} max={500} style={{ width: 200 }} />
            </Form.Item>
          </Form>
        </div>
      </Modal>

      <Modal
        open={linkOpen}
        title="按群链接采集群员"
        okText="开始采集"
        cancelText="取消"
        confirmLoading={linkBusy}
        onCancel={() => setLinkOpen(false)}
        onOk={() => void runCollectByLink()}
      >
        <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
          <Alert
            type="info"
            showIcon
            message="粘贴群链接，系统自动解析群并采集群员"
            description="支持 t.me/xxx、t.me/+hash、@username、数字 ID，一行一个（最多 50 个）。只有号**已经在群里**才能读到成员名单；不在群里时可勾选自动加入。多个链接会轮流分给不同账号，避免一个号连续进群。"
          />
          <Form form={linkForm} layout="vertical" initialValues={{ join_if_missing: false, leave_after: false, member_limit: 200 }}>
            <Form.Item
              label="群链接（每行一个）"
              name="links"
              rules={[{ required: true, message: '至少一个链接' }]}
            >
              <Input.TextArea
                rows={6}
                placeholder={'https://t.me/somegroup\nt.me/+AbCdEfGh123\n@public_group'}
                style={{ fontFamily: 'var(--tg-font-family-mono, monospace)' }}
              />
            </Form.Item>
            <Form.Item name="join_if_missing" valuePropName="checked">
              <Checkbox>不在群里时自动加入（会在群里留下一条入群系统消息，并按高风险动作计费）</Checkbox>
            </Form.Item>
            <Form.Item name="leave_after" valuePropName="checked">
              <Checkbox>采完自动退出该群（留人不留痕，仅对本次加入的号生效）</Checkbox>
            </Form.Item>
            <Form.Item label="每群采集多少成员" name="member_limit">
              <InputNumber min={0} max={500} style={{ width: 200 }} />
            </Form.Item>
          </Form>
        </div>
      </Modal>

      <BulkResultModal open={Boolean(collectResult)} result={collectResult} onClose={() => setCollectResult(null)} />
    </PageContainer>
  );
}
