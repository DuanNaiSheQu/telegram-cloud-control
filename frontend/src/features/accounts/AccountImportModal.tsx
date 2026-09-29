/**
 * AccountImportModal —— 账号矩阵导入向导（四步：选方式 → 填内容 → 预览 → 结果）。
 *
 * 支持四种来源：
 *   phone（手机号清单）/ session_string（StringSession 串）/ session_file（.session 文件）/ tdata（Telegram Desktop 目录 zip）
 *
 * 设计取舍：
 * - 「先预览再导入」：解析结果先摊开给操作员确认（脱敏展示，session 明文不回传页面）；
 * - tdata 需要可选依赖 opentele2，后端报告不可用时，这个入口直接标灰并给替代路径；
 * - 可顺手绑定代理与分组，并按「养号起点从今天算」入库（新号从最严档开始限速）。
 */
import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Segmented, Select, Space, Switch, Table, Tag, Typography, Upload, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { InboxOutlined, RocketOutlined } from '@ant-design/icons';
import { accountImportApi, groupApi, proxyApi } from '../../api/endpoints';
import { useAsyncData } from '../../hooks/useAsyncData';
import { notifySuccess, toast } from '../../utils/feedback';
import type { ImportItemPreview, ImportResponse, ImportResultItem } from '../../api/types';

interface Props {
  open: boolean;
  onClose: () => void;
  /** 导入成功后回调（刷新列表） */
  onImported?: (result: ImportResponse) => void;
}

const KIND_TIP: Record<string, string> = {
  phone: '每行一个号码，号码后可用逗号加备注；导入后走验证码登录拿会话。',
  session_string: '每行一个 Telethon StringSession；也支持 `手机号,session` 或 `session,备注`。',
  session_file: '选一个或多个 .session 文件（Telethon / Pyrogram 的 SQLite 会话），自动转成 StringSession。',
  tdata: '把 Telegram Desktop 的 tdata 目录打包成 zip 上传；一个包里可以含多个账号。',
};

export default function AccountImportModal({ open, onClose, onImported }: Props) {
  const [kind, setKind] = useState('');
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [proxyId, setProxyId] = useState<string | undefined>();
  const [groupId, setGroupId] = useState<string | undefined>();
  const [remark, setRemark] = useState('');
  const [startWarmup, setStartWarmup] = useState(true);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportItemPreview[] | null>(null);
  const [previewMeta, setPreviewMeta] = useState<{ total: number; ready: number; failed: number } | null>(null);
  const [result, setResult] = useState<ImportResponse | null>(null);

  const formats = useAsyncData(() => accountImportApi.formats(), [open], { immediate: false });
  const proxies = useAsyncData(() => proxyApi.list(), [open], { immediate: false });
  const groups = useAsyncData(() => groupApi.list(), [open], { immediate: false });

  // 格式列表由后端给：第一项作为默认选中；万一当前选中的被后端移除（比如手机号清单下线）就回退到首项
  useEffect(() => {
    const list = formats.data?.formats ?? [];
    if (!list.length) return;
    if (!list.some((item) => item.kind === kind)) setKind(list[0].kind);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formats.data]);

  const activeFormat = useMemo(
    () => (formats.data?.formats ?? []).find((item) => item.kind === kind),
    [formats.data, kind],
  );
  const tdataBlocked = kind === 'tdata' && formats.data?.tdata_available === false;

  const buildForm = () => {
    const form = new FormData();
    form.append('kind', kind);
    if (text.trim()) form.append('text', text);
    files.forEach((file) => form.append('files', file));
    form.append('remark', remark);
    form.append('start_warmup', String(startWarmup));
    if (proxyId) form.append('proxy_id', proxyId);
    if (groupId) form.append('group_id', groupId);
    return form;
  };

  const reset = () => {
    setText('');
    setFiles([]);
    setPreview(null);
    setPreviewMeta(null);
    setResult(null);
  };

  const handleParse = async () => {
    if (!text.trim() && files.length === 0) {
      toast.warning('先粘贴清单或选择文件');
      return;
    }
    setBusy(true);
    try {
      const res = await accountImportApi.parse(buildForm());
      setPreview(res.items);
      setPreviewMeta({ total: res.total, ready: res.ready, failed: res.failed });
      if (res.failed) toast.warning(`有 ${res.failed} 条解析失败，下面标红的原因可以先改掉`);
    } catch {
      /* client 已统一提示 */
    } finally {
      setBusy(false);
    }
  };

  const handleImport = async () => {
    setBusy(true);
    try {
      const res = await accountImportApi.run(buildForm());
      setResult(res);
      notifySuccess(res.message);
      onImported?.(res);
    } catch {
      /* client 已统一提示 */
    } finally {
      setBusy(false);
    }
  };

  const previewColumns: ColumnsType<ImportItemPreview> = [
    { title: '来源', dataIndex: 'source', width: 110, render: (value: string) => <Tag>{value}</Tag> },
    { title: '标识', dataIndex: 'label', width: 200, ellipsis: true },
    {
      title: '会话',
      dataIndex: 'has_session',
      width: 80,
      render: (value: boolean) => (value ? <Tag color="green">已带</Tag> : <Tag>待登录</Tag>),
    },
    { title: 'DC', dataIndex: 'dc_id', width: 60, render: (value: number | null) => value ?? '—' },
    {
      title: '解析结果',
      dataIndex: 'error',
      width: 320,
      ellipsis: { showTitle: false },
      render: (value: string | null) => {
        const text = value || '可以导入';
        return (
          <Tooltip title={text} placement="topLeft">
            <span className={value ? 'tg-clamp-cell tg-text-danger' : 'tg-clamp-cell'}>{text}</span>
          </Tooltip>
        );
      },
    },
  ];

  const resultColumns: ColumnsType<ImportResultItem> = [
    { title: '标识', dataIndex: 'label', width: 200, ellipsis: true },
    {
      title: '结果',
      dataIndex: 'ok',
      width: 90,
      render: (value: boolean) => (value ? <Tag color="green">成功</Tag> : <Tag color="red">跳过</Tag>),
    },
    { title: '说明', dataIndex: 'message', ellipsis: true },
  ];

  return (
    <Modal
      open={open}
      title="批量导入账号"
      width={860}
      onCancel={() => {
        reset();
        onClose();
      }}
      footer={
        <Space>
          <Button onClick={handleParse} loading={busy} disabled={tdataBlocked}>
            预览解析结果
          </Button>
          <Button
            type="primary"
            icon={<RocketOutlined />}
            loading={busy}
            disabled={tdataBlocked}
            onClick={() => void handleImport()}
          >
            开始导入
          </Button>
        </Space>
      }
      afterOpenChange={(visible) => {
        if (!visible) return;
        void formats.reload();
        void proxies.reload();
        void groups.reload();
      }}
    >
      <div className="tg-stack" style={{ gap: 'var(--tg-space-lg)' }}>
        <Segmented
          value={kind}
          onChange={(value) => {
            setKind(String(value));
            setPreview(null);
            setResult(null);
          }}
          options={(formats.data?.formats ?? []).map((item) => ({ label: item.label, value: item.kind }))}
          block
        />

        <Alert
          type={tdataBlocked ? 'warning' : 'info'}
          showIcon
          message={activeFormat?.label ?? '导入方式'}
          description={
            <>
              {activeFormat?.description ?? KIND_TIP[kind]}
              {tdataBlocked ? (
                <>
                  <br />
                  {activeFormat?.hint ?? '当前环境没有安装 opentele2，tdata 转换不可用；可先用 .session 文件或验证码登录导入。'}
                </>
              ) : null}
            </>
          }
        />

        {kind === 'phone' || kind === 'session_string' ? (
          <Input.TextArea
            rows={8}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={
              kind === 'phone'
                ? '+12025550143\n+447700900123,备注'
                : '1BVtsOK...（一行一个）\n+12025550143,1BVtsOK...'
            }
            style={{ fontFamily: 'var(--tg-font-family-mono, monospace)' }}
          />
        ) : (
          <Upload.Dragger
            multiple
            accept={activeFormat?.accept}
            fileList={files.map((file, index) => ({ uid: String(index), name: file.name }))}
            beforeUpload={(file) => {
              setFiles((prev) => [...prev.filter((item) => item.name !== file.name), file as File]);
              return false; // 交给「开始导入」统一提交
            }}
            onRemove={(file) => setFiles((prev) => prev.filter((item) => item.name !== file.name))}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到这里（{activeFormat?.accept ?? '.session / .zip'}）</p>
            <p className="ant-upload-hint">可一次选多个文件；点「预览解析结果」先看内容再导入</p>
          </Upload.Dragger>
        )}

        <Form layout="vertical" size="small">
          <Space wrap align="start">
            <Form.Item label="绑定代理（可选）" style={{ marginBottom: 0 }}>
              <Select
                allowClear
                style={{ width: 200 }}
                placeholder="不绑定"
                value={proxyId}
                loading={proxies.loading}
                onChange={setProxyId}
                options={(proxies.data ?? []).map((item) => ({ value: item.id, label: `${item.name}（${item.endpoint}）` }))}
              />
            </Form.Item>
            <Form.Item label="归入分组（可选）" style={{ marginBottom: 0 }}>
              <Select
                allowClear
                style={{ width: 180 }}
                placeholder="不分组"
                value={groupId}
                loading={groups.loading}
                onChange={setGroupId}
                options={(groups.data ?? []).map((item) => ({ value: item.id, label: item.name }))}
              />
            </Form.Item>
            <Form.Item label="备注" style={{ marginBottom: 0 }}>
              <Input style={{ width: 200 }} value={remark} onChange={(event) => setRemark(event.target.value)} placeholder="例如：八月推广批" />
            </Form.Item>
            <Form.Item label="养号起点" style={{ marginBottom: 0 }}>
              <Switch checked={startWarmup} onChange={setStartWarmup} />
              <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 'var(--tg-font-size-xs)' }}>
                从今天起按最严额度限速
              </Typography.Text>
            </Form.Item>
          </Space>
        </Form>

        {previewMeta ? (
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 'var(--tg-font-size-sm)' }}>
              解析出 {previewMeta.total} 条：可导入 {previewMeta.ready} 条
              {previewMeta.failed ? `，${previewMeta.failed} 条有问题` : ''}
            </Typography.Text>
            <Table<ImportItemPreview>
              size="small"
              rowKey={(record, index) => `${record.label}-${index}`}
              columns={previewColumns}
              dataSource={preview ?? []}
              pagination={{ pageSize: 6, size: 'small' }}
              style={{ marginTop: 'var(--tg-space-md)' }}
            />
          </div>
        ) : null}

        {result ? (
          <Alert
            type={result.failed ? 'warning' : 'success'}
            showIcon
            message={result.message}
            description={
              <Table<ImportResultItem>
                size="small"
                rowKey={(record) => `${record.index}-${record.label}`}
                columns={resultColumns}
                dataSource={result.results}
                pagination={{ pageSize: 6, size: 'small' }}
              />
            }
          />
        ) : null}
      </div>
    </Modal>
  );
}
