/**
 * 兼容层：旧代码里的 `import Layout, { RequireAuth } from './components/Layout'`。
 * 新代码请直接用外壳：`import { AppShell } from './components/shell/AppShell'`。
 */
import { AppShell } from './shell/AppShell';

export { AppShell as Layout, RequireAuth } from './shell/AppShell';
export { NAV_GROUPS, NAV_ITEMS, matchNav } from './shell/nav';

export default AppShell;
