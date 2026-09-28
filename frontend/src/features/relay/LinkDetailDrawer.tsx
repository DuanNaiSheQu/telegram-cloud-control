/**
 * LinkDetailDrawer —— 一条已转发记录的详情抽屉。
 * 展示原消息（正文/发送人/会话/归属号/时间）与员工群里那条（chat_id / 消息 ID），
 * 底部「跳转原会话」深链 /dialogs?dialog_id=…
 */
import { Button, Typography } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { CopyableText, DetailDrawer, RelativeTime } from '../../components';
import type { RelayLinkItem } from './types';

export function LinkDetailDrawer({
  link,
  onClose,
}: {
  link: RelayLinkItem | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const open = Boolean(link);

  const body = link?.origin_body;
  const dialogTitle = link?.origin_dialog_title;

  return (
    <DetailDrawer
      open={open}
      title="转发记录详情"
      subtitle={
        link ? (
          <RelativeTime value={link.origin_created_at ?? link.created_at} showAbsolute />
        ) : null
      }
      onClose={onClose}
      width={560}
      sections={[
        {
          title: '原消息',
          items: [
            {
              label: '发送人',
              value: link?.origin_sender_name || '—',
            },
            {
              label: '会话',
              value: dialogTitle || '—',
            },
            {
              label: '归属账号',
              value: link?.account_label || '—',
            },
            {
              label: '原消息 ID',
              value: <CopyableText value={link?.message_id} mono maxLength={32} />,
            },
            {
              label: '原消息时间',
              value: link?.origin_created_at ? (
                <RelativeTime value={link.origin_created_at} showAbsolute />
              ) : (
                '—'
              ),
              span: 'full',
            },
          ],
        },
        {
          title: '员工群里那条',
          items: [
            {
              label: 'chat_id',
              value: <CopyableText value={link?.staff_chat_id} mono />,
            },
            {
              label: '消息 ID',
              value: <CopyableText value={link?.staff_message_id} mono />,
            },
            {
              label: '转发时间',
              value: link?.created_at ? <RelativeTime value={link.created_at} showAbsolute /> : '—',
              span: 'full',
            },
          ],
        },
        {
          title: '关联',
          items: [
            {
              label: '转发规则',
              value: <CopyableText value={link?.route_id} mono maxLength={32} />,
            },
            {
              label: 'Bot',
              value: <CopyableText value={link?.bot_id} mono maxLength={32} />,
            },
          ],
        },
      ]}
      footer={
        link?.origin_dialog_id ? (
          <Button
            type="primary"
            icon={<ArrowRightOutlined />}
            onClick={() => {
              onClose();
              navigate(`/dialogs?dialog_id=${link.origin_dialog_id}`);
            }}
          >
            跳转原会话
          </Button>
        ) : null
      }
    >
      {body ? (
        <div style={{ marginBottom: 'var(--tg-space-xl)' }}>
          <Typography.Text type="secondary">原消息正文</Typography.Text>
          <div
            style={{
              marginTop: 'var(--tg-space-md)',
              padding: 'var(--tg-space-lg)',
              background: 'var(--tg-color-bg-sunken)',
              borderRadius: 'var(--tg-radius-md)',
              color: 'var(--tg-color-text-primary)',
              fontSize: 'var(--tg-font-size)',
              lineHeight: 'var(--tg-font-line-normal)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {body}
          </div>
        </div>
      ) : null}
    </DetailDrawer>
  );
}
