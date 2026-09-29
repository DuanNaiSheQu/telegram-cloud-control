#!/usr/bin/env bash
# 内置浏览器环境安装（服务器无桌面也能跑）
#
# 为什么需要它：
#   佩奇的 Cap 验证会检测浏览器环境，纯无头模式直接被拦（captcha_token 拿不到）。
#   所以必须跑「真实窗口」——而服务器没有桌面，就用 Xvfb 造一块**虚拟屏幕**：
#   Chrome 以为自己在正常显示器上（指纹完整），实际没有任何物理输出。
#
# 装什么：
#   1. Google Chrome（真 Chrome，指纹比打包 Chromium 干净）
#   2. Xvfb（虚拟显示器）
#   3. X11 相关运行库（Chrome 在最小化系统上缺的那些）
#   4. Playwright 的 Node 依赖
#
# 用法：bash scripts/install_browser.sh
set -euo pipefail

log() { printf '\033[36m[install]\033[0m %s\n' "$1"; }
warn() { printf '\033[33m[install]\033[0m %s\n' "$1"; }
die() { printf '\033[31m[install]\033[0m %s\n' "$1" >&2; exit 1; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null 2>&1 && SUDO="sudo" || warn "非 root 且没有 sudo，可能装不上系统包"
fi

install_debian() {
  log "Debian/Ubuntu 系：安装 Xvfb、字体、X11 库与 Chrome"
  $SUDO apt-get update -qq
  $SUDO apt-get install -y -qq \
    xvfb xauth \
    fonts-liberation fonts-noto-cjk \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libxshmfence1 wget gnupg ca-certificates || \
    warn "部分依赖安装失败，继续尝试"

  if ! command -v google-chrome >/dev/null 2>&1 && ! command -v google-chrome-stable >/dev/null 2>&1; then
    log "下载并安装 Google Chrome"
    tmp_deb="$(mktemp --suffix=.deb)"
    if wget -q -O "$tmp_deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb; then
      $SUDO apt-get install -y -qq "$tmp_deb" || $SUDO dpkg -i "$tmp_deb" || warn "Chrome 安装失败"
      rm -f "$tmp_deb"
    else
      warn "Chrome 下载失败（网络不通？）——稍后可由 Playwright 自带的 Chromium 兜底"
    fi
  else
    log "已存在 Google Chrome，跳过"
  fi
}

install_rhel() {
  log "RHEL/CentOS 系：安装 Xvfb 与 Chrome"
  $SUDO yum install -y epel-release || true
  $SUDO yum install -y xorg-x11-server-Xvfb libX11 libXcomposite libXdamage \
    libXrandr libgbm cups-libs atk at-spi2-atk nss alsa-lib pango cairo \
    liberation-fonts google-noto-sans-cjk-fonts wget || warn "部分依赖安装失败"
  if ! command -v google-chrome >/dev/null 2>&1; then
    $SUDO yum install -y https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm || \
      warn "Chrome 安装失败"
  fi
}

install_macos() {
  log "macOS：系统本身有显示，无需 Xvfb；确认 Chrome 存在即可"
  if [ ! -d "/Applications/Google Chrome.app" ]; then
    warn "未找到 Google Chrome。可执行：brew install --cask google-chrome"
  else
    log "已存在 Google Chrome"
  fi
}

OS="$(uname -s)"
case "$OS" in
  Linux)
    if command -v apt-get >/dev/null 2>&1; then install_debian
    elif command -v yum >/dev/null 2>&1; then install_rhel
    else die "未识别的包管理器，请手动安装 xvfb 与 google-chrome"
    fi
    ;;
  Darwin) install_macos ;;
  *) warn "未识别的系统：$OS（Windows 请自己装 Chrome）" ;;
esac

# ---------- Playwright 依赖与自带浏览器（作为 Chrome 的兜底） ----------
FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../frontend" && pwd)"
if [ -f "$FRONTEND_DIR/package.json" ]; then
  log "安装 Playwright 的 Chromium 兜底内核"
  ( cd "$FRONTEND_DIR" && npx --yes playwright install chromium >/dev/null 2>&1 ) || \
    warn "Playwright Chromium 安装失败（不影响系统 Chrome 路线）"
fi

log "完成。自检："
printf '  Chrome : %s\n' "$(command -v google-chrome || command -v google-chrome-stable || echo '未装（将用 Playwright Chromium）')"
printf '  Xvfb   : %s\n' "$(command -v Xvfb || echo '未装（macOS 不需要）')"
log "跑验证时会自动检测：macOS 直接开最小化窗口；Linux 无 DISPLAY 时自动起 Xvfb。"
