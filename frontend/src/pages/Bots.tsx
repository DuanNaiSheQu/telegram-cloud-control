/**
 * Bot 管理页：Bot 列表（名称/@username/Token 掩码/Webhook 状态与注册时间/自动回复开关/转发目标）
 * + 新建/编辑/删除 + 重新校验（getMe）+ 注册/删除 Webhook + persona 资料编辑（字数与示例模板）。
 * - 新建/换 Token 失败（假 Token → 后端 400 中文原因）在表单内展示，页面不崩；
 * - getMe 校验失败的无效 Token 行显式标黄（useBotHealth 页内体检）；
 * - Token 安全提示（加密保存、只在服务端解密）。
 */
import { useState } from 'react';
import { Button, Space, Switch, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  UserOutlined,
} from '@ant-design/icons';
import {
  ConfirmModal,
  CopyableText,
  DataTable,
  PageContainer,
  RelativeTime,
  SoftTag,
} from '../components';
import { botApi } from '../api/endpoints';
import { useAsyncData } from '../hooks/useAsyncData';
import { formatNumber } from '../utils/format';
import { notifySuccess, toast } from '../utils/feedback';
import { useAuth } from '../auth/AuthContext';
import type { BotOut } from '../api/types';
import { BotFormModal } from '../features/bots/BotFormModal';
import { PersonaModal } from '../features/bots/PersonaModal';
import { setBotHealthCache, useBotHealth } from '../features/bots/useBotHealth';

export default function Bots() {
  const { isAdmin } = useAuth();
  const bots = useAsyncData(() => botApi.list(), []);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<BotOut | null>(null);
  const [personaBot, setPersonaBot] = useState<BotOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<BotOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [healthVersion, setHealthVersion] = useState(0);

  const health = useBotHealth(bots.data ?? [], isAdmin, healthVersion);

  const handleWebhook = async (bot: BotOut, enable: boolean) => {
    setBusyId(bot.id);
    try {
      const res = await botApi.webhook(bot.id, enable);
      notifySuccess(res.message || (enable ? 'Webhook 已注册' : 'Webhook 已删除'));
      void bots.reload();
    } catch {
      /* client 已统一中文提示（后端 detail 带 Telegram 原始原因） */
    } finally {
      setBusyId(null);
    }
  };

  const handleCheck = async (bot: BotOut) => {
    setBusyId(bot.id);
    try {
      const res = await botApi.check(bot.id);
      setBotHealthCache(bot.id, 'ok');
      setHealthVersion((v) => v + 1);
      notifySuccess(`校验通过：${res.bot_username ? `@${res.bot_username}` : res.name}`);
      void bots.reload();
    } catch {
      setBotHealthCache(bot.id, 'invalid');
      setHealthVersion((v) => v + 1);
      toast.warning('校验失败：该 Token 可能已失效，详见行内标黄提示');
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await botApi.remove(deleteTarget.id);
      notifySuccess(res.message || 'Bot 已删除');
      setDeleteTarget(null);
      void bots.reload();
    } catch {
      /* client 已统一中文提示 */
    } finally {
      setDeleting(false);
    }
  };

  const columns: ColumnsType<BotOut> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 190,
      render: (value: string, record) => {
        const invalid = health[record.id] === 'invalid';
        return (
          <div className="tg-stack">
            <Space size={6} wrap>
              <span>{value}</span>
              {invalid ? (
                <Tooltip title="getMe 校验失败：Token 无效或已被撤销，请重新保存 Token 或到 BotFather 重新签发">
                  <SoftTag tone="warning">Token 失效</SoftTag>
                </Tooltip>
              ) : health[record.id] === 'checking' ? (
                <SoftTag tone="neutral">校验中…</SoftTag>
              ) : null}
            </Space>
            {record.bot_tg_id ? (
              <Typography.Text type="secondary" className="ellipsis">
                ID {record.bot_tg_id}
              </Typography.Text>
            ) : null}
          </div>
        );
      },
    },
    {
      title: '@username',
      dataIndex: 'bot_username',
      width: 150,
      render: (value: string | null) =>
        value ? (
          <Typography.Text code>@{value}</Typography.Text>
        ) : (
          <Tooltip title="Token 校验成功后由 getMe 回填">
            <SoftTag tone="neutral">未校验</SoftTag>
          </Tooltip>
        ),
    },
    {
      title: 'Token 掩码',
      dataIndex: 'token_masked',
      width: 180,
      render: (value: string) =>
        value ? (
          <CopyableText value={value} mono tooltip="加密保存，接口只回掩码；明文只在服务端解密" />
        ) : (
          '—'
        ),
    },
    {
      title: 'Webhook',
      key: 'webhook',
      width: 230,
      render: (_: unknown, record) => (
        <div className="tg-stack">
          <SoftTag tone={record.webhook_enabled ? 'success' : 'neutral'}>
            {record.webhook_enabled ? '已注册' : '未注册'}
          </SoftTag>
          {record.webhook_url ? (
            <Tooltip title={record.webhook_url}>
              <Typography.Text type="secondary" className="ellipsis" style={{ maxWidth: 200 }}>
                {record.webhook_url}
              </Typography.Text>
            </Tooltip>
          ) : null}
          {record.webhook_set_at ? (
            <Typography.Text type="secondary">
              注册于 <RelativeTime value={record.webhook_set_at} />
            </Typography.Text>
          ) : null}
        </div>
      ),
    },
    {
      title: '自动回复',
      dataIndex: 'auto_reply_enabled',
      width: 100,
      render: (value: boolean, record) => (
        <Tooltip title={isAdmin ? undefined : '仅管理员可操作'}>
          <Switch
            size="small"
            checked={value}
            disabled={!isAdmin}
            onChange={async (checked) => {
              try {
                await botApi.update(record.id, { auto_reply_enabled: checked });
                notifySuccess(checked ? '自动回复已开启' : '自动回复已关闭');
                void bots.reload();
              } catch {
                /* client 已统一中文提示 */
              }
            }}
          />
        </Tooltip>
      ),
    },
    {
      title: '转发目标',
      key: 'relay',
      width: 170,
      render: (_: unknown, record) =>
        record.relay_enabled ? (
          <div className="tg-stack">
            <SoftTag tone="primary">
              转发到 {record.relay_target_kind === 'private' ? '私聊' : '群聊'}
            </SoftTag>
            {record.relay_target_chat_id ? (
              <CopyableText value={record.relay_target_chat_id} mono />
            ) : (
              <Typography.Text type="secondary">未设置目标会话</Typography.Text>
            )}
          </div>
        ) : (
          <SoftTag tone="neutral">未开启</SoftTag>
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
      width: 330,
      fixed: 'right',
      render: (_: unknown, record) => (
        <Space size="small" wrap>
          <Tooltip title={isAdmin ? '重新 getMe 校验 Token' : '仅管理员可操作'}>
            <Button
              size="small"
              icon={<SyncOutlined />}
              disabled={!isAdmin}
              loading={busyId === record.id}
              onClick={() => void handleCheck(record)}
            >
              重新校验
            </Button>
          </Tooltip>
          <Tooltip title={isAdmin ? undefined : '仅管理员可操作'}>
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              disabled={!isAdmin}
              loading={busyId === record.id}
              onClick={() => void handleWebhook(record, !record.webhook_enabled)}
            >
              {record.webhook_enabled ? '删除 Webhook' : '注册 Webhook'}
            </Button>
          </Tooltip>
          <Button size="small" icon={<UserOutlined />} onClick={() => setPersonaBot(record)}>
            资料
          </Button>
          <Tooltip title={isAdmin ? undefined : '仅管理员可操作'}>
            <Button size="small" icon={<EditOutlined />} disabled={!isAdmin} onClick={() => setEditing(record)}>
              编辑
            </Button>
          </Tooltip>
          <Tooltip title={isAdmin ? undefined : '仅管理员可操作'}>
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

  const invalidCount = (bots.data ?? []).filter((item) => health[item.id] === 'invalid').length;

  return (
    <PageContainer
      title="Bot 管理"
      description="Bot Token 加密保存（只回掩码）；Webhook 注册与自动回复资料在这里维护，转发规则在「Bot 转发」页。"
      actions={
        <Space>
          <Button icon={<ReloadOutlined />} loading={bots.loading} onClick={() => void bots.reload()}>
            刷新
          </Button>
          <Tooltip title={isAdmin ? undefined : '仅管理员可新建 Bot'}>
            <Button type="primary" icon={<PlusOutlined />} disabled={!isAdmin} onClick={() => setCreateOpen(true)}>
              新建 Bot
            </Button>
          </Tooltip>
        </Space>
      }
    >
      <DataTable<BotOut>
        rowKey="id"
        columns={columns}
        dataSource={bots.data ?? []}
        loading={bots.loading}
        error={bots.error}
        onRetry={() => void bots.reload()}
        columnSettingsKey="bots"
        scrollX={1560}
        onRow={(record) => ({
          style:
            health[record.id] === 'invalid'
              ? { background: 'var(--tg-color-warning-bg)' }
              : undefined,
        })}
        title={
          invalidCount > 0 ? (
            <span style={{ color: 'var(--tg-color-warning)' }}>
              有 {formatNumber(invalidCount)} 个 Bot 的 Token 校验失败（已标黄），请重新保存 Token
            </span>
          ) : undefined
        }
        empty={{
          art: 'list',
          title: '还没有 Bot',
          description: '用 BotFather 给的 Token 新建一个 Bot，就可以做转发与自动回复了。',
          action: isAdmin ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              新建 Bot
            </Button>
          ) : undefined,
        }}
      />

      <BotFormModal
        open={createOpen || Boolean(editing)}
        bot={editing}
        onCancel={() => {
          setCreateOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          setCreateOpen(false);
          setEditing(null);
          void bots.reload();
        }}
      />

      <PersonaModal
        bot={personaBot}
        onCancel={() => setPersonaBot(null)}
        onSuccess={() => {
          setPersonaBot(null);
          void bots.reload();
        }}
      />

      <ConfirmModal
        open={Boolean(deleteTarget)}
        danger
        loading={deleting}
        title={`删除 Bot「${deleteTarget?.name ?? ''}」？`}
        content="删除后它的 Webhook 会一并注销，关联的转发规则和自动回复都会失效。"
        okText="删除"
        onOk={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </PageContainer>
  );
}
