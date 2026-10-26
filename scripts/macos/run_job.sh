#!/bin/bash
# launchd 调用的单次执行入口：加锁、写日志、按大小截断。
# 用法: run_job.sh main|keepalive

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
JOB="${1:-main}"

case "$JOB" in
  main)
    SCRIPT="main.py"
    ;;
  keepalive)
    SCRIPT="main_update_weu.py"
    ;;
  *)
    echo "用法: $0 main|keepalive" >&2
    exit 64
    ;;
esac

LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/$JOB.log"
LOCK="$LOG_DIR/$JOB.lock"
MAX_LOG_BYTES=$((5 * 1024 * 1024))

mkdir -p "$LOG_DIR"
cd "$ROOT" || exit 70

# 系统 Python 3.9 自带 LibreSSL，urllib3 每次启动都会打一条无害告警，这里静音
export PYTHONWARNINGS="ignore"

# 单文件超过 5MB 时原地截断，避免日志无限增长
if [ -f "$LOG" ]; then
  size="$(stat -f%z "$LOG" 2>/dev/null || echo 0)"
  if [ "$size" -gt "$MAX_LOG_BYTES" ]; then
    : > "$LOG"
    echo "[$(date '+%F %T')] 日志超过 5MB，已截断" >> "$LOG"
  fi
fi

# 上一轮还没结束时跳过，避免任务堆叠
if ! /usr/bin/shlock -p $$ -f "$LOCK" >/dev/null 2>&1; then
  echo "[$(date '+%F %T')] 跳过：上一轮 $JOB 仍在运行" >> "$LOG"
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT

echo "[$(date '+%F %T')] ===== 开始 $SCRIPT (pid $$) =====" >> "$LOG"
"$ROOT/venv/bin/python" "$SCRIPT" >> "$LOG" 2>&1
rc=$?
echo "[$(date '+%F %T')] ===== 结束 $SCRIPT (exit $rc) =====" >> "$LOG"
exit "$rc"
