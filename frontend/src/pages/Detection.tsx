import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleTwoTone,
  CloseCircleTwoTone,
  ReloadOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { accountApi, groupApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatTime } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import StatusBadge from '../components/StatusBadge';
import type { AccountOut, CheckRequest, CheckResultOut } from '../api/types';

interface CheckRow extends CheckResultOut {
  checked_at: string;
}

export default function Detection() {
  const [keyword, setKeyword] = useState('');
  const [groupId, setGroupId] = useState<string | undefined>(undefined);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [rows, setRows] = useState<CheckRow[]>([]);
  const [checking, setChecking] = useState(false);
  const [lastScope, setLastScope] = useState<CheckRequest | null>(null);

  const accounts = useAsyncData(
    () =>
      accountApi.list({
        page: 1,
        page_size: 200,
        keyword: keyword || undefined,
        group_id: groupId || undefined,
      }),
    [keyword, groupId],
  );
  const groups = useAsyncData(() => groupApi.list(), []);

  const runCheck = async (payload: CheckRequest, label: string) => {
    setChecking(true);
    try {
      const res = await accountApi.checkBatch(payload);
      const raw = res as unknown as CheckResultOut[] | { items: CheckResultOut[] };
      const list = Array.isArray(raw) ? raw : (raw?.items ?? []);
      const checkedAt = new Date().toISOString();
      setRows(list.map((item) => ({ ...item, checked_at: checkedAt })));
      setLastScope(payload);
      notifySuccess(`${label}：已写 ${list.length} 条检测任务，Worker 读到后会写回状态`);
      void accounts.reload();
    } catch {
      /* client 已统一提示 */
    } finally {
      setChecking(false);
    }
  };

  const accountColumns: ColumnsType<AccountOut> = [
    { title: '手机号', dataIndex: 'phone_masked', width: 140 },
    {
      title: '用户名',
      dataIndex: 'username',
      width: 140,
      render: (value: string | null) => value || '—',
    },
    {
      title: '分组',
      dataIndex: 'group_name',
      width: 120,
      render: (value: string | null) => (value ? <Tag color="blue">{value}</Tag> : <Tag>未分组</Tag>),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 110,
      render: (_: unknown, record) => (
        <StatusBadge status={record.status} label={record.status_label} reason={record.status_reason} />
      ),
    },
    {
      title: '最后检测',
      dataIndex: 'last_checked_at',
      width: 170,
      render: (value: string | null) => formatTime(value),
    },
    {
      title: '最后心跳',
      dataIndex: 'last_heartbeat',
      width: 170,
      render: (value: string | null) => formatTime(value),
    },
  ];

  const resultColumns: ColumnsType<CheckRow> = [
    { title: '脱敏手机号', dataIndex: 'phone_masked', width: 140 },
    {
      title: '连得上',
      dataIndex: 'reachable',
      width: 110,
      render: (value: boolean) =>
        value ? (
          <Space size={4}>
            <CheckCircleTwoTone twoToneColor="#52c41a" /> 连得上
          </Space>
        ) : (
          <Space size={4}>
            <CloseCircleTwoTone twoToneColor="#ff4d4f" /> 连不上
          </Space>
        ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 120,
      render: (_: unknown, record) => <StatusBadge status={record.status} label={record.status_label} />,
    },
    {
      title: '说明',
      dataIndex: 'message',
      render: (value: string) => value || '—',
    },
    {
      title: '关联任务',
      dataIndex: 'task_id',
      width: 180,
      render: (value: string | null, record) =>
        value ? (
          <Tooltip title={value}>
            <Link to={`/tasks?account_id=${record.account_id}`}>{value.slice(0, 8)}…</Link>
          </Tooltip>
        ) : (
          '—'
        ),
    },
    {
      title: '检测时间',
      dataIndex: 'checked_at',
      width: 170,
      render: (value: string) => formatTime(value),
    },
  ];

  return (
    <div>
      <Card className="section-card" title="账号检测">
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="检测会写一条 account_check 任务并立刻续一次租约，Worker 读到后读一次状态写回该行；结果为「连得上 / 要验证码 / 会话失效」。"
        />
        <div className="page-toolbar">
          <Select
            allowClear
            placeholder="按分组筛选"
            style={{ width: 180 }}
            value={groupId}
            onChange={(value) => {
              setGroupId(value);
              setSelectedIds([]);
            }}
            options={(groups.data ?? []).map((g) => ({ value: g.id, label: `${g.name}（${g.account_count}）` }))}
          />
          <Input.Search
            allowClear
            placeholder="手机号 / 用户名关键词"
            style={{ width: 220 }}
            onSearch={(value) => setKeyword(value.trim())}
          />
          <Space className="page-toolbar-right">
            <Button icon={<ReloadOutlined />} onClick={() => void accounts.reload()} loading={accounts.loading}>
              刷新列表
            </Button>
            <Button
              icon={<SafetyCertificateOutlined />}
              disabled={!selectedIds.length}
              loading={checking}
              onClick={() =>
                void runCheck({ account_ids: selectedIds, scope: 'selected' }, `检测选中 ${selectedIds.length} 个`)
              }
            >
              检测选中（{selectedIds.length}）
            </Button>
            {groupId ? (
              <Button
                loading={checking}
                onClick={() => void runCheck({ account_ids: null, scope: `group:${groupId}` }, '检测当前分组')}
              >
                检测当前分组
              </Button>
            ) : null}
            <Button
              type="primary"
              loading={checking}
              onClick={() => void runCheck({ account_ids: null, scope: 'all' }, '检测全部')}
            >
              全部检测
            </Button>
          </Space>
        </div>

        <Table<AccountOut>
          size="small"
          rowKey="id"
          loading={accounts.loading}
          dataSource={accounts.data?.items ?? []}
          columns={accountColumns}
          pagination={{ pageSize: 10, showSizeChanger: false, size: 'small' }}
          locale={{ emptyText: <Empty description="没有符合条件的账号" /> }}
          rowSelection={{
            preserveSelectedRowKeys: true,
            selectedRowKeys: selectedIds,
            onChange: (keys) => setSelectedIds(keys.map((key) => String(key))),
          }}
        />
      </Card>

      <Card
        title="检测结果"
        extra={
          <Space>
            <Typography.Text type="secondary">
              {rows.length ? `最近一次检测返回 ${rows.length} 条` : '还没有发起检测'}
            </Typography.Text>
            <Button
              icon={<ReloadOutlined />}
              disabled={!lastScope}
              loading={checking}
              onClick={() => lastScope && void runCheck(lastScope, '重新检测')}
            >
              刷新结果
            </Button>
          </Space>
        }
      >
        <Table<CheckRow>
          size="small"
          rowKey={(record) => `${record.account_id}-${record.task_id ?? ''}-${record.checked_at}`}
          dataSource={rows}
          columns={resultColumns}
          pagination={{ pageSize: 10, showSizeChanger: false, size: 'small' }}
          locale={{
            emptyText: <Empty description="点上面的「检测选中」或「全部检测」查看结果" />,
          }}
        />
      </Card>
    </div>
  );
}
