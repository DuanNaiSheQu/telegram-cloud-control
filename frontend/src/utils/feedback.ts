/** 全局消息提示桥：把 App.useApp() 的实例交给非组件代码（fetch 封装）使用。 */
import type { MessageInstance } from 'antd/es/message/interface';

let messageApi: MessageInstance | null = null;

export function bindMessageApi(instance: MessageInstance | null): void {
  messageApi = instance;
}

export function notifyError(content: string): void {
  if (messageApi) messageApi.error(content);
  else console.error('[notifyError]', content);
}

export function notifySuccess(content: string): void {
  if (messageApi) messageApi.success(content);
}

export function notifyInfo(content: string): void {
  if (messageApi) messageApi.info(content);
}

export function notifyWarning(content: string): void {
  if (messageApi) messageApi.warning(content);
}
