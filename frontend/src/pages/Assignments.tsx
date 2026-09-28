/**
 * 员工分配页（admin 专属）：
 * - 员工列表：用户名/角色/启用状态/已分配账号数/最后登录；
 * - 新建 / 改口令 / 停用 / 启用 / 删除；
 * - 选员工 → 账号选择器（搜索/分组筛选/多选/「未分配」视图，行内显示归属人）批量分配/取消；
 * - 分配矩阵：每个员工名下的账号一览；
 * - operator 访问：不请求任何接口，直接给中文 403 提示。
 */
import { useMemo, useState } from 'react';
import { Button, Space, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  DeleteOutlined,
  KeyOutlined,
  PlusOutlined,
  ReloadOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import {
  ConfirmModal,
  DataTable,
  ErrorState,
  PageContainer,
  RelativeTime,
  SectionCard,
  SoftTag,
  StatCard,
  StatGrid,
} from '../components';
import { accountApi, assignmentApi, userApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatNumber, shortId } from '../utils/format';
import { notifySuccess } from '../utils/feedback';
import { useAuth } from '../auth/AuthContext';
import { USER_ROLE_LABELS } from '../constants';
import type { UserOut, UserRole } from '../api/types';
import { AccountAssignModal } from '../features/assignments/AccountAssignModal';
import { PasswordModal, UserFormModal } from '../features/assignments/UserFormModal';

export default function Assignments() {
  const { isAdmin, user: currentUser } = useAuth();
  const users = useAsyncData(() => userApi.list(), [], { immediate: isAdmin });
  const assignments = useAsyncData(() => assignmentApi.list(), [], { immediate: isAdmin });
  const accounts = useAsyncData(() => accountApi.list({ page: 1, page_size: 200 }), [], {
    immediate: isAdmin,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [pwdUser, setPwdUser] = useState<UserOut | null>(null);
  const [assignUser, setAssignUser] = useState<UserOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const userList = useMemo(() => users.data ?? [], [users.data]);
  const assignmentList = useMemo(() => assignments.data ?? [], [assignments.data]);
  const accountList = useMemo(() => accounts.data?.items ?? [], [accounts.data]);

  const assignedAccountCount = useMemo(() => {
    const set = new Set<string>();
    for (const item of assignmentList) for (const id of item.account_ids) set.add(id);
    return set.size;
  }, [assignmentList]);
  const unassignedCount = Math.max(0, accountList.length - assignedAccountCount);
  const operatorCount = userList.filter((item) => item.role === 'operator').length;

  // 分配矩阵：每个员工名下的账号标签（管理员行说明「看全部」）
  const accountLabelOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of accountList) map.set(item.id, item.phone_masked);
    return map;
  }, [accountList]);

  const matrixRows = useMemo(
    () =>
      assignmentList.map((item) => ({
        ...item,
        labels: item.account_ids.map((id) => accountLabelOf.get(id) ?? shortId(id)),
      })),
    [assignmentList, accountLabelOf],
  );

  // operator 访问：管理端专属页，直接给中文 403 提示（接口同样拒绝，这里不再发起请求）
  if (!isAdmin) {
    return (
      <PageContainer title="员工分配" description="员工账号、口令与账号分配关系的管理入口。">
        <SectionCard>
          <ErrorState
            title="403 需要管理员权限"
            description="员工分配是管理员专属页面：员工账号、口令与分配关系都属于管理动作。当前登录账号是操作员，后端接口同样会拒绝（403）。如有需要，请联系管理员。"
            error="需要管理员权限"
            compact
          />
        </SectionCard>
      </PageContainer>
    );
  }

  const handleToggleActive = async (record: UserOut) => {
    setBusyId(record.id);
    try {
      await userApi.update(record.id, { is_active: !record.is_active });
      notifySuccess(record.is_active ? '员工已停用' : '员工已启用');
      void users.reload();
    } catch {
      /* 最后一个管理员的保护等后端 400/409 中文原因已由 client 统一提示 */
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await userApi.remove(deleteTarget.id);
      notifySuccess(res.message || '员工已删除');
      setDeleteTarget(null);
      void users.reload();
      void assignments.reload();
    } catch {
      /* client 已统一中文提示 */
    } finally {
      setDeleting(false);
    }
  };

  const columns: ColumnsType<UserOut> = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 170,
      render: (value: string, record) => (
        <div className="tg-stack">
          <span>{value}</span>
          {record.display_name && record.display_name !== value ? (
            <Typography.Text type="secondary">{record.display_name}</Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 100,
      render: (value: UserRole) => (
        <SoftTag tone={value === 'admin' ? 'primary' : 'neutral'}>
          {USER_ROLE_LABELS[value] ?? value}
        </SoftTag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 90,
      render: (value: boolean) => (
        <SoftTag tone={value ? 'success' : 'neutral'}>{value ? '启用' : '停用'}</SoftTag>
      ),
    },
    {
      title: '已分配账号数',
      dataIndex: 'account_count',
      width: 130,
      align: 'right',
      render: (value: number, record) => (
        <Space size={6}>
          <span className="tg-num">{formatNumber(value)}</span>
          {record.role === 'admin' ? (
            <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
              管理员看全部
            </Typography.Text>
          ) : null}
        </Space>
      ),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login_at',
      width: 150,
      render: (value: string | null) => <RelativeTime value={value} />,
    },
    {
      title: '操作',
      key: 'actions',
      width: 340,
      fixed: 'right',
      render: (_: unknown, record) => {
        const isSelf = record.id === currentUser?.id;
        return (
          <Space size="small" wrap>
            <Tooltip title={record.role === 'admin' ? '管理员可见全部账号，无需分配' : undefined}>
              <Button
                size="small"
                icon={<TeamOutlined />}
                disabled={record.role === 'admin'}
                onClick={() => setAssignUser(record)}
              >
                分配账号
              </Button>
            </Tooltip>
            <Button size="small" icon={<KeyOutlined />} onClick={() => setPwdUser(record)}>
              改口令
            </Button>
            <Button
              size="small"
              loading={busyId === record.id}
              disabled={isSelf}
              onClick={() => void handleToggleActive(record)}
            >
              {record.is_active ? '停用' : '启用'}
            </Button>
            <Tooltip title={isSelf ? '不能删除自己' : undefined}>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                disabled={isSelf}
                onClick={() => setDeleteTarget(record)}
              >
                删除
              </Button>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  const matrixColumns: ColumnsType<(typeof matrixRows)[number]> = [
    {
      title: '员工',
      dataIndex: 'username',
      width: 200,
      render: (value: string, record) => (
        <div className="tg-stack">
          <span>{value}</span>
          {record.display_name && record.display_name !== value ? (
            <Typography.Text type="secondary">{record.display_name}</Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '账号数',
      dataIndex: 'account_count',
      width: 90,
      align: 'right',
      render: (value: number) => <span className="tg-num">{formatNumber(value)}</span>,
    },
    {
      title: '名下账号',
      key: 'labels',
      render: (_: unknown, record) =>
        record.labels.length ? (
          <Space size={6} wrap>
            {record.labels.map((label: string) => (
              <SoftTag key={label} tone="info">
                {label}
              </SoftTag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">还没有分配账号</Typography.Text>
        ),
    },
  ];

  return (
    <PageContainer
      title="员工分配"
      description="分组是标签，分配才是权限：操作员只能看到并操作自己被分配到的账号；管理员可见全部。"
      actions={
        <Space>
          <Button
            icon={<ReloadOutlined />}
            loading={users.loading}
            onClick={() => {
              void users.reload();
              void assignments.reload();
              void accounts.reload();
            }}
          >
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建员工
          </Button>
        </Space>
      }
    >
      <StatGrid>
        <StatCard title="员工总数" value={userList.length} tone="neutral" />
        <StatCard title="操作员" value={operatorCount} tone="primary" />
        <StatCard title="已分配账号" value={assignedAccountCount} tone="success" />
        <StatCard title="未分配账号" value={unassignedCount} tone="warning" />
      </StatGrid>

      <DataTable<UserOut>
        rowKey="id"
        columns={columns}
        dataSource={userList}
        loading={users.loading}
        error={users.error}
        onRetry={() => void users.reload()}
        columnSettingsKey="assignments-users"
        scrollX={1100}
        empty={{
          art: 'accounts',
          title: '还没有员工账号',
          description: '新建员工并分配账号后，对方就可以用自己的账号登录控制台值班了。',
          action: (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建员工
            </Button>
          ),
        }}
      />

      <SectionCard
        title="分配矩阵"
        subtitle="每个员工名下的账号一览；在员工行点「分配账号」可批量调整，账号选择器里也能按归属人反查。"
        bodyPadding="none"
      >
        <DataTable<(typeof matrixRows)[number]>
          rowKey="user_id"
          columns={matrixColumns}
          dataSource={matrixRows}
          loading={assignments.loading}
          error={assignments.error}
          onRetry={() => void assignments.reload()}
          showDensity={false}
          scrollX={760}
          empty={{
            art: 'list',
            title: '还没有分配记录',
            description: '在员工列表里点「分配账号」，把账号批量交给操作员。',
          }}
        />
      </SectionCard>

      <UserFormModal
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onSuccess={() => {
          setCreateOpen(false);
          void users.reload();
        }}
      />

      <PasswordModal user={pwdUser} onCancel={() => setPwdUser(null)} onSuccess={() => setPwdUser(null)} />

      <AccountAssignModal
        open={Boolean(assignUser)}
        user={assignUser}
        assignments={assignmentList}
        accounts={accountList}
        onCancel={() => setAssignUser(null)}
        onSaved={() => {
          setAssignUser(null);
          void users.reload();
          void assignments.reload();
        }}
      />

      <ConfirmModal
        open={Boolean(deleteTarget)}
        danger
        loading={deleting}
        title={`删除员工「${deleteTarget?.username ?? ''}」？`}
        content="删除后该员工无法再登录控制台；他名下的账号会变成未分配，不影响账号本身。"
        okText="删除"
        onOk={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </PageContainer>
  );
}
