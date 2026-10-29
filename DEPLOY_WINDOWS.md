# Windows 部署说明

Windows 使用 **任务计划程序（Task Scheduler）** 定时运行检测脚本，推荐通过 GUI 完成配置和安装。
不需要管理员权限。

## 环境要求

- Windows 10 / 11
- Python **3.9+**（安装时勾选 **Add Python to PATH**）
- PowerShell 5.1+
- 能访问 `https://yjs1.ustc.edu.cn`

## 快速开始（GUI）

1. 克隆或解压本项目。
2. 双击项目根目录的 **`setup_windows.bat`**。

脚本会：

1. 检查 Python
2. 创建 `venv`
3. 安装 `requirements.txt`
4. 从模板生成 `config.yml`
5. 启动 `python gui.py`

浏览器会打开本地 GUI。按提示填写邮箱、Cookie、院系优先级和筛选条件，保存后点
“安装 / 更新定时任务”。

下次打开 GUI 双击 **`start_gui.bat`**。

## 手动安装

在 PowerShell 或 CMD 中：

```bat
cd /d 你的项目目录
py -3 -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python gui.py
```

如果 `py` 不存在，把 `py -3` 换成 `python`。

## 定时任务

### 通过 GUI

“服务与日志”页 → “安装 / 更新”，或概览页的“安装 / 更新定时任务”。

GUI 会读取已保存的 `schedule_interval_seconds` 和 `enable_keepalive`，调用
`scripts\windows\install_task.ps1`。

### 手动安装

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install_task.ps1 -IntervalMinutes 2
```

可选参数：

```powershell
# 同时安装 30 分钟一次的保活任务（会退课再抢回）
powershell -ExecutionPolicy Bypass -File scripts\windows\install_task.ps1 -IntervalMinutes 2 -EnableKeepalive
```

任务说明：

| 任务名 | 频率 | 作用 |
| --- | --- | --- |
| `USTC-Grab-Report` | 每 2 分钟 | 检测、抢课、查成绩 |
| `USTC-Grab-Keepalive` | 每 30 分钟 | 可选保活（有丢课风险） |

任务使用当前用户身份运行，**需要用户已登录**；使用 `pythonw.exe`，不会弹出控制台窗口。

### 查看状态

```powershell
Get-ScheduledTask -TaskName "USTC-Grab-Report"
Get-ScheduledTaskInfo -TaskName "USTC-Grab-Report"

# 或
schtasks /Query /TN "USTC-Grab-Report" /V /FO LIST
```

### 立即运行 / 停止

```powershell
Start-ScheduledTask -TaskName "USTC-Grab-Report"
Stop-ScheduledTask -TaskName "USTC-Grab-Report"

# 或
schtasks /Run /TN "USTC-Grab-Report"
schtasks /End /TN "USTC-Grab-Report"
```

### 卸载

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\uninstall_task.ps1
```

配置和数据不会被删除。

## 文件位置

Windows 直接从项目目录运行，所以配置和数据在项目根目录：

```text
你的项目目录\
├── config.yml
├── config.yml.bak
├── data\
│   ├── courses.json
│   ├── exclude.json
│   ├── grades.json
│   └── weu_cache.json
├── logs\
│   └── main.log
└── venv\
```

**安装任务后不要移动项目目录**，否则任务里的 Python 路径会失效；移动后重新运行一次安装脚本。

## 故障排查

**提示找不到 Python**
安装 Python 3.9+ 时勾选 “Add Python to PATH”，然后重新打开命令行。也可以直接重跑
`setup_windows.bat`。

**任务显示 Ready 但日志没有更新**
- 任务计划程序要求用户已登录（交互式任务）。
- 检查 `logs\main.log`。
- 在任务计划程序中手动 “Run” 一次，查看 “Last Run Result”。
- 确认项目目录没有被移动。

**PowerShell 禁止运行脚本**
使用 `-ExecutionPolicy Bypass`（本项目脚本和 GUI 都已这样调用）。不要修改全局策略。

**窗口一闪而过 / 没有界面**
`start_gui.bat` 会保留错误信息；也可以在项目目录手动执行：

```bat
venv\Scripts\python.exe gui.py
```

**平台 403 / cookie 过期**
客户端会按应用刷新 `_WEU` 并重试一次。仍失败时重新抓 Cookie，在 GUI 中保存。

**SMTP 535**
使用了登录密码而不是授权码；或者授权码已失效。用 GUI 的“测试 SMTP”验证。

**电脑睡眠**
Windows 睡眠时任务暂停，唤醒后按计划继续；要 7×24 运行建议放常开的机器。

## 安全

- `config.yml` 含平台 Cookie 和 SMTP 授权码，不要提交 Git。
- GUI 只监听 `127.0.0.1`，启动时生成随机访问令牌。
- 日志不记录 Cookie 和授权码。
- 如果使用公司/学校电脑，确认任务计划程序策略允许当前用户创建任务。
