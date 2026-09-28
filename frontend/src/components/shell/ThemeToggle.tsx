/**
 * ThemeToggle —— 顶栏主题开关（浅色 / 深色 / 跟随系统），localStorage 记忆。
 *
 * props 契约：{ size?: 'sm'|'md' }（可选）
 * 行为：点击弹出菜单；当前项打勾；「跟随系统」时图标随系统明暗变化。
 */
import { Dropdown, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import { BgColorsOutlined, CheckOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons';
import { useTheme } from '../../theme';
import type { ThemePreference } from '../../theme';

export interface ThemeToggleProps {
  size?: 'sm' | 'md';
}

const LABELS: Record<ThemePreference, string> = {
  light: '浅色',
  dark: '深色',
  system: '跟随系统',
};

export function ThemeToggle({ size = 'md' }: ThemeToggleProps) {
  const { preference, mode, setPreference } = useTheme();

  const items: MenuProps['items'] = (['light', 'dark', 'system'] as ThemePreference[]).map((value) => ({
    key: value,
    icon: value === 'light' ? <SunOutlined /> : value === 'dark' ? <MoonOutlined /> : <BgColorsOutlined />,
    label: LABELS[value],
    onClick: () => setPreference(value),
    extra: preference === value ? <CheckOutlined style={{ color: 'var(--tg-color-primary)' }} /> : null,
  }));

  return (
    <Dropdown menu={{ items, selectedKeys: [preference] }} trigger={['click']} placement="bottomRight">
      <Tooltip title={`主题：${LABELS[preference]}`}>
        <button
          type="button"
          className="app-icon-button"
          aria-label={`主题：${LABELS[preference]}`}
          style={size === 'sm' ? { width: 28, height: 28 } : undefined}
        >
          {mode === 'dark' ? <MoonOutlined /> : <SunOutlined />}
        </button>
      </Tooltip>
    </Dropdown>
  );
}

export default ThemeToggle;
