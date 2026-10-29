@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
  echo 还没有安装虚拟环境，请先运行 setup_windows.bat
  pause
  exit /b 1
)
venv\Scripts\python.exe gui.py
if errorlevel 1 pause
