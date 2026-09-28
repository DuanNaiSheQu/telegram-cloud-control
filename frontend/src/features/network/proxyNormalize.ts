/**
 * 代理出口填写规范化：粘贴「socks5://user:pass@1.2.3.4:1080」这类完整出口，
 * 一键解析成 scheme / host / port / username / password；主机名清洗掉协议头与路径。
 */
import type { ProxyScheme } from '../../api/types';

export interface ParsedEndpoint {
  scheme?: ProxyScheme;
  host?: string;
  port?: number;
  username?: string;
  password?: string;
}

const SCHEME_ALIASES: Record<string, ProxyScheme> = {
  socks5: 'socks5',
  socks5h: 'socks5',
  socks4: 'socks4',
  socks4a: 'socks4',
  http: 'http',
  https: 'https',
  mtproxy: 'mtproxy',
  mtproto: 'mtproxy',
};

/** 把用户粘贴的出口字符串解析成字段；解析不了时原样放回 host 供用户手工改 */
export function parseEndpoint(raw: string): ParsedEndpoint {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const result: ParsedEndpoint = {};

  let rest = trimmed;
  // 1) 协议头（可选）
  const schemeMatch = /^([a-z0-9]+):\/\//i.exec(rest);
  if (schemeMatch) {
    const alias = SCHEME_ALIASES[schemeMatch[1].toLowerCase()];
    if (alias) result.scheme = alias;
    rest = rest.slice(schemeMatch[0].length);
  }
  // 2) 账号口令（可选 user[:pass]@）
  const atIndex = rest.lastIndexOf('@');
  if (atIndex >= 0) {
    const auth = rest.slice(0, atIndex);
    rest = rest.slice(atIndex + 1);
    const colon = auth.indexOf(':');
    if (colon >= 0) {
      result.username = decodeURIComponent(auth.slice(0, colon));
      result.password = decodeURIComponent(auth.slice(colon + 1));
    } else {
      result.username = decodeURIComponent(auth);
    }
  }
  // 3) host[:port]，去掉路径与查询
  rest = rest.split(/[/?#]/, 1)[0];
  const ipv6 = /^\[([^\]]+)\](?::(\d+))?$/.exec(rest);
  if (ipv6) {
    result.host = ipv6[1];
    if (ipv6[2]) result.port = Number(ipv6[2]);
  } else {
    const hostPort = /^([^:]+)(?::(\d+))?$/.exec(rest);
    if (hostPort) {
      result.host = hostPort[1];
      if (hostPort[2]) result.port = Number(hostPort[2]);
    } else {
      result.host = rest;
    }
  }
  if (result.port !== undefined && (Number.isNaN(result.port) || result.port < 1 || result.port > 65535)) {
    delete result.port;
  }
  return result;
}

/** 主机名清洗：去协议头、去路径、去空格；保留不了的内容返回清洗后的值 */
export function normalizeHost(raw: string): string {
  let value = raw.trim();
  value = value.replace(/^[a-z0-9]+:\/\//i, '');
  value = value.split(/[/?#]/, 1)[0];
  return value;
}

/** 主机合法性：不含空格、协议头、路径 */
export function hostError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return '请输入主机';
  if (/\s/.test(value)) return '主机里不能有空格';
  if (/^[a-z0-9]+:\/\//i.test(value)) return '不要带协议头（scheme://），协议请用下拉选择';
  if (/[/?#]/.test(value)) return '不要带路径或查询参数';
  return null;
}
