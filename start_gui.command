#!/bin/bash
# macOS 双击启动 GUI。首次运行前请确保已创建 venv 并安装依赖：
#   python3 -m venv venv
#   ./venv/bin/pip install -r requirements.txt
cd "$(dirname "$0")" || exit 1

if [ ! -x "venv/bin/python" ]; then
  echo "未找到 venv。请先在终端执行："
  echo "  cd \"$(pwd)\""
  echo "  python3 -m venv venv"
  echo "  ./venv/bin/pip install -r requirements.txt"
  echo
  read -n 1 -s -r -p "按任意键退出..."
  exit 1
fi

exec ./venv/bin/python gui.py
