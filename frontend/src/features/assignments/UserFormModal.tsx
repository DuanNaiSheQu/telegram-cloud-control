/**
 * 员工表单弹窗：新建员工（UserFormModal）与修改口令（PasswordModal）。
 * 后端 409（用户名已存在）等中文原因直接展示在表单内。
 */
import { useState } from 'react';
import { Alert, Form, Input, Modal, Select } from 'antd';
import { userApi } from '../../api/endpoints';
import { ApiError } from '../../api/client';
import { USER_ROLE_OPTIONS } from '../../constants';
import { notifySuccess } from '../../utils/feedback';
import type { UserCreate, UserOut, UserRole } from '../../api/types';

interface UserForm {
  username: string;
  password: string;
  display_name?: string;
  role: UserRole;
}

export function UserFormModal({
  open,
  onCancel,
  onSuccess,
}: {
  open: boolean;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<UserForm>();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleFinish = async (values: UserForm) => {
    setSubmitting(true);
    setFormError(null);
    const payload: UserCreate = {
      username: values.username.trim(),
      password: values.password,
      display_name: values.display_name ?? '',
      role: values.role,
    };
    try {
      await userApi.create(payload);
      notifySuccess('员工已创建');
      form.resetFields();
      onSuccess();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.friendlyMessage : '创建失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title="新建员工"
      onCancel={onCancel}
      okText="创建"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => form.submit()}
    >
      {formError ? (
        <Alert
          type="error"
          showIcon
          closable
          onClose={() => setFormError(null)}
          message="创建失败"
          description={formError}
          style={{ marginBottom: 'var(--tg-space-xl)' }}
        />
      ) : null}
      <Form form={form} layout="vertical" onFinish={handleFinish} initialValues={{ role: 'operator' }}>
        <Form.Item
          label="用户名"
          name="username"
          rules={[{ required: true, message: '请输入用户名' }, { min: 2, message: '至少 2 个字符' }]}
        >
          <Input placeholder="登录用户名" allowClear autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="口令"
          name="password"
          rules={[{ required: true, message: '请输入口令' }, { min: 6, message: '至少 6 位' }]}
          extra="只存 bcrypt 哈希，任何人（包括管理员）都看不到明文。"
        >
          <Input.Password placeholder="至少 6 位" autoComplete="new-password" />
        </Form.Item>
        <Form.Item label="显示名" name="display_name">
          <Input placeholder="例如：值班-小王" allowClear />
        </Form.Item>
        <Form.Item label="角色" name="role" rules={[{ required: true, message: '请选择角色' }]}>
          <Select options={USER_ROLE_OPTIONS} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export function PasswordModal({
  user,
  onCancel,
  onSuccess,
}: {
  user: UserOut | null;
  onCancel: () => void;
  onSuccess: () => void;
}) {
  const [form] = Form.useForm<{ password: string }>();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleFinish = async (values: { password: string }) => {
    if (!user) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await userApi.update(user.id, { password: values.password });
      notifySuccess('口令已更新');
      form.resetFields();
      onSuccess();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.friendlyMessage : '修改失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={Boolean(user)}
      title={`修改口令：${user?.username ?? ''}`}
      onCancel={onCancel}
      okText="保存"
      cancelText="取消"
      confirmLoading={submitting}
      onOk={() => form.submit()}
    >
      {formError ? (
        <Alert
          type="error"
          showIcon
          closable
          onClose={() => setFormError(null)}
          message="修改失败"
          description={formError}
          style={{ marginBottom: 'var(--tg-space-xl)' }}
        />
      ) : null}
      <Form form={form} layout="vertical" onFinish={handleFinish}>
        <Form.Item
          label="新口令"
          name="password"
          rules={[{ required: true, message: '请输入新口令' }, { min: 6, message: '至少 6 位' }]}
          extra="改完口令后，该员工现有的登录令牌不会自动失效；如怀疑泄漏请先停用账号。"
        >
          <Input.Password placeholder="至少 6 位" autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
