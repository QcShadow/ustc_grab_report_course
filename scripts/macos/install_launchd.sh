#!/bin/bash
# 在 macOS 上安装 USTC 抢报告脚本的 launchd 定时任务。
#
# 为什么装到 Application Support：macOS 的 TCC 会阻止 launchd 后台任务
# 读取/执行桌面目录里的文件（会以 exit 126 失败），所以运行时目录必须
# 放在非受保护路径下。
#
# 用法:
#   bash scripts/macos/install_launchd.sh
#   PYTHON_BIN=/opt/homebrew/bin/python3.12 bash scripts/macos/install_launchd.sh
#
# 重复运行是安全的：会同步代码、保留 config.yml / data / logs。

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${USTC_GRAB_HOME:-$HOME/Library/Application Support/USTC-Grab/report-course}"
AGENTS="$HOME/Library/LaunchAgents"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
START_INTERVAL="${START_INTERVAL:-}"
ENABLE_KEEPALIVE="${ENABLE_KEEPALIVE:-}"

say() { printf '%s\n' "$*"; }

if [ "$(uname -s)" != "Darwin" ]; then
  say "此脚本只适用于 macOS。Linux 请使用 scripts/ustc-grab.service 或 cron。"
  exit 1
fi

say "源码目录: $SRC"
say "运行目录: $DEST"

mkdir -p "$DEST" "$DEST/logs" "$AGENTS"

# 1. 同步代码。config.yml / data / logs / venv 是运行时状态，不覆盖。
SRC_REAL="$(cd "$SRC" && pwd -P)"
DEST_REAL="$(cd "$DEST" && pwd -P)"
if [ "$SRC_REAL" != "$DEST_REAL" ]; then
  say "同步代码..."
  rsync -a \
    --exclude 'venv' \
    --exclude '.git' \
    --exclude 'logs' \
    --exclude 'config.yml' \
    --exclude 'config.yml.bak' \
    --exclude 'data' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    "$SRC/" "$DEST/"
else
  say "已在运行目录，跳过代码同步"
fi

# 首次部署时带上 data 的初始状态（成绩缓存、排除列表等）
if [ ! -d "$DEST/data" ]; then
  cp -R "$SRC/data" "$DEST/data"
  say "已复制 data/ 初始数据"
fi

# 2. Python 虚拟环境
if [ ! -x "$DEST/venv/bin/python" ]; then
  say "创建虚拟环境 ($PYTHON_BIN)..."
  "$PYTHON_BIN" -m venv "$DEST/venv"
fi
say "安装/校验依赖..."
"$DEST/venv/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$DEST/venv/bin/python" -m pip install -q --disable-pip-version-check -r "$DEST/requirements.txt"

# 3. 配置文件
if [ ! -f "$DEST/config.yml" ]; then
  if [ -f "$SRC/config.yml" ]; then
    cp "$SRC/config.yml" "$DEST/config.yml"
  else
    cp "$DEST/templates/config.template.yml" "$DEST/config.yml"
  fi
  say "已生成配置文件: $DEST/config.yml"
fi
chmod 600 "$DEST/config.yml"

# 从配置读取 GUI 设置的默认值（环境变量优先）
if [ -z "$START_INTERVAL" ]; then
  START_INTERVAL=$("$DEST/venv/bin/python" -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1],encoding='utf-8')) or {}; v=d.get('schedule_interval_seconds',120); print(max(30,min(int(v),86400)) if str(v).isdigit() else 120)" "$DEST/config.yml")
fi
if [ -z "$ENABLE_KEEPALIVE" ]; then
  ENABLE_KEEPALIVE=$("$DEST/venv/bin/python" -c "import sys,yaml; d=yaml.safe_load(open(sys.argv[1],encoding='utf-8')) or {}; print('1' if d.get('enable_keepalive') else '0')" "$DEST/config.yml")
fi

case "$START_INTERVAL" in
  ''|*[!0-9]*)
    say "START_INTERVAL 必须是整数秒，例如 START_INTERVAL=120"
    exit 2
    ;;
esac
if [ "$START_INTERVAL" -lt 30 ]; then
  say "START_INTERVAL 不能小于 30 秒"
  exit 2
fi

# 4. 配置自检；未填好就不注册定时任务
if ! "$DEST/venv/bin/python" "$DEST/scripts/macos/preflight.py"; then
  cat <<EOF

配置文件还没填好，已中止安装定时任务。
请编辑（cookie 和 SMTP 授权码都要换成真实值）:
  $DEST/config.yml
填好后重新运行:
  bash "$SRC/scripts/macos/install_launchd.sh"

EOF
  exit 3
fi

# 5. 保活任务默认关闭；只有显式 ENABLE_KEEPALIVE=1 且配置了 BGBM 才安装
if [ "$ENABLE_KEEPALIVE" = "1" ]; then
  if ! "$DEST/venv/bin/python" - "$DEST/config.yml" <<'PY'
import sys
import yaml

with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
bgbm = str((data.get("particular_course") or {}).get("BGBM") or "")
sys.exit(0 if bgbm and "xxxx" not in bgbm.lower() else 1)
PY
  then
    say "particular_course.BGBM 未配置，跳过保活任务。"
    ENABLE_KEEPALIVE=0
  fi
fi

LABELS=("com.ustc.grab.report")
if [ "$ENABLE_KEEPALIVE" = "1" ]; then
  LABELS+=("com.ustc.grab.keepalive")
else
  launchctl bootout "gui/$(id -u)/com.ustc.grab.keepalive" >/dev/null 2>&1 || true
  rm -f "$AGENTS/com.ustc.grab.keepalive.plist"
fi

# 6. 生成并加载 LaunchAgent
say "安装 launchd 任务（间隔 ${START_INTERVAL}s）..."
for label in "${LABELS[@]}"; do
  template="$DEST/scripts/macos/${label}.plist.template"
  target="$AGENTS/${label}.plist"
  sed -e "s|__DEST__|$DEST|g" -e "s|__INTERVAL__|$START_INTERVAL|g" "$template" > "$target"
  plutil -lint "$target" >/dev/null
done

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$(id -u)/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/${label}.plist"
  say "已加载: $label"
done

# 7. 立即跑一次并显示结果
launchctl kickstart -k "gui/$(id -u)/com.ustc.grab.report" >/dev/null 2>&1 || true
sleep 3

JOBS_DESC="  com.ustc.grab.report     每 ${START_INTERVAL} 秒运行 main.py"
if [ "$ENABLE_KEEPALIVE" = "1" ]; then
  JOBS_DESC="$JOBS_DESC
  com.ustc.grab.keepalive  每 30 分钟运行 main_update_weu.py（会退课再抢回）"
fi

cat <<EOF

安装完成。定时任务:
$JOBS_DESC

说明: _WEU 已按应用缓存，仅在失效时自动刷新；不需要保活课程。
默认 ${START_INTERVAL} 秒检测一次。想更快可执行:
  START_INTERVAL=60 bash "$SRC/scripts/macos/install_launchd.sh"

查看运行状态:
  launchctl print gui/$(id -u)/com.ustc.grab.report | grep -E 'state|last exit'

查看日志:
  tail -f "$DEST/logs/main.log"

修改配置后重启任务:
  launchctl kickstart -k gui/$(id -u)/com.ustc.grab.report

EOF

say "最近日志:"
tail -n 15 "$DEST/logs/main.log" 2>/dev/null || say "（尚无日志，任务可能还在启动）"
