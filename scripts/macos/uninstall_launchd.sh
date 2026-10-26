#!/bin/bash
# 卸载 macOS launchd 定时任务。
# 用法: bash scripts/macos/uninstall_launchd.sh [--purge]
#   --purge 连同运行目录和日志一起删除（默认保留数据与配置）

set -uo pipefail

DEST="${USTC_GRAB_HOME:-$HOME/Library/Application Support/USTC-Grab/report-course}"
AGENTS="$HOME/Library/LaunchAgents"
LABELS=("com.ustc.grab.report" "com.ustc.grab.keepalive")

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  rm -f "$AGENTS/${label}.plist"
  echo "已卸载: $label"
done

if [ "${1:-}" = "--purge" ]; then
  case "$DEST" in
    "$HOME/Library/Application Support/USTC-Grab/report-course") rm -rf "$DEST" ;;
    *) echo "拒绝删除非预期路径: $DEST" >&2; exit 1 ;;
  esac
  echo "已删除运行目录: $DEST"
else
  echo "运行目录与数据已保留: $DEST"
  echo "如需彻底删除: bash scripts/macos/uninstall_launchd.sh --purge"
fi
