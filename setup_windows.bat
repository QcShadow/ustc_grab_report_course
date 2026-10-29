@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% --version >nul 2>nul
if errorlevel 1 (
  echo 没有找到 Python 3。请先安装 Python 3.9 或更高版本，并勾选 "Add Python to PATH"。
  pause
  exit /b 1
)

if not exist venv (
  echo 正在创建虚拟环境...
  %PY% -m venv venv
  if errorlevel 1 goto :error
)

call venv\Scripts\activate.bat

echo 正在安装依赖...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

if not exist config.yml (
  copy templates\config.template.yml config.yml >nul
)

echo 启动图形界面...
python gui.py
goto :eof

:error
echo.
echo 安装失败，请检查上面的错误信息。
pause
exit /b 1
