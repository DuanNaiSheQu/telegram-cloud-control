/**
 * 组件库统一出口。
 *
 * 页面推荐这样 import：
 *   import { PageContainer, StatCard, SectionCard, DataTable, FilterBar,
 *            EmptyState, ErrorState, StatusBadge, StatusDot, TaskStatusTag,
 *            ConfirmModal, DetailDrawer, CopyableText, RelativeTime,
 *            TrendSparkline, CardSkeleton, TableSkeleton } from '../components';
 *
 * 每个组件的 props 契约写在各自文件头注释里；速查表见 components/README.md。
 */
export { default as StatCard, type StatCardProps, type StatDelta } from './StatCard';
export { default as SectionCard, type SectionCardProps } from './SectionCard';
export {
  default as StatusBadge,
  StatusBadge as StatusBadgeNamed,
  type StatusBadgeProps,
} from './StatusBadge';
export { default as StatusDot, type StatusDotProps } from './StatusDot';
export {
  default as TaskStatusTag,
  TaskStatusTag as TaskStatusTagNamed,
  TaskTypeTag,
  CurrentTaskTag,
  MessageStatusTag,
  SoftTag,
} from './TaskStatusTag';
export { default as EmptyState, type EmptyStateProps, type EmptyArt } from './EmptyState';
export { default as ErrorState, type ErrorStateProps } from './ErrorState';
export { default as ErrorBoundary, type ErrorBoundaryProps } from './ErrorBoundary';
export {
  default as PageSkeleton,
  CardSkeleton,
  TableSkeleton,
  ListSkeleton,
  StatSkeleton,
  ChartSkeleton,
  type SkeletonProps,
} from './LoadingSkeleton';
export { default as DataTable, type DataTableProps, type TableDensity } from './DataTable';
export { default as FilterBar, type FilterBarProps } from './FilterBar';
export { default as DetailDrawer, type DetailDrawerProps, type DetailSection, type DetailItem } from './DetailDrawer';
export { default as ConfirmModal, type ConfirmModalProps } from './ConfirmModal';
export { default as CopyableText, type CopyableTextProps } from './CopyableText';
export { default as RelativeTime, type RelativeTimeProps } from './RelativeTime';
export { default as TrendSparkline, type TrendSparklineProps, type SparkPoint } from './TrendSparkline';
export { default as PageContainer, PageHeader, StatGrid, type PageContainerProps, type PageHeaderProps, type Crumb } from './PageContainer';
export { default as NotFound, type NotFoundProps } from './NotFound';
