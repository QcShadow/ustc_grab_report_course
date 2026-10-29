# macOS 部署说明

本项目在 macOS 上使用 **launchd** 常驻运行，推荐通过 GUI 完成配置和安装。

## 为什么运行时在 Application Support

macOS 的 TCC 隐私保护会阻止 launchd 后台任务读取或执行 `~/Desktop` 下的文件，表现为
`last exit code = 126`。因此服务运行时放在：

```text
~/Library/Application Support/USTC-Grab/report-course
```

仓库目录只作为源码。安装 / 更新服务时会把代码同步过去；`config.yml`、`data/`、`logs/`、
`venv/` 属于运行时状态，不会被覆盖。

## 环境要求

- macOS 12 或更高（在 macOS 26 上测试）
- Python 3.9+
- 能访问 `https://yjs1.ustc.edu.cn`
- 不需要 `sudo`，也不需要安装 Homebrew

## 快速开始（GUI）

```bash
git clone https://github.com/QcShadow/ustc_grab_report_course.git
cd ustc_grab_report_course
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python gui.py
```

也可以双击项目根目录的 `start_gui.command` 启动。

浏览器会打开 `http://127.0.0.1:<随机端口>/?token=...`。按 GUI 提示：

1. 填写邮箱、SMTP 授权码、平台 Cookie
2. 调整院系优先级和筛选条件
3. 保存配置
4. 测试 SMTP 和平台连接
5. 报告预览
6. 安装 / 更新定时任务

配置与日志都在 Application Support 目录，GUI 会直接编辑那里的 `config.yml`。

## 手动安装服务

如果不想用 GUI：

```bash
cd "$(git rev-parse --show-toplevel)"
START_INTERVAL=120 bash scripts/macos/install_launchd.sh
```

`START_INTERVAL` 可省略，默认从 `config.yml` 的 `schedule_interval_seconds` 读取（120 秒）。
安装脚本会：

1. 同步代码到 Application Support
2. 创建/复用 venv 并安装依赖
3. 检查配置
4. 生成并加载 `com.ustc.grab.report` LaunchAgent
5. 立即运行一次并写入日志

保活任务默认关闭。只有显式启用时才安装：

```bash
ENABLE_KEEPALIVE=1 bash scripts/macos/install_launchd.sh
```

保活会退掉再抢回 `particular_course.BGBM`，有丢课风险；通常不需要，客户端会自动刷新 `_WEU`。

## 配置

配置文件：

```text
~/Library/Application Support/USTC-Grab/report-course/config.yml
```

权限为 `600`。GUI 保存时会自动备份为 `config.yml.bak`。

关键项：

| 配置项 | 说明 |
| --- | --- |
| `schedule_interval_seconds` | 检测间隔，默认 120 秒 |
| `max_grabs_per_cycle` | 每轮最多成功选几门，默认 1 |
| `conflict_window_minutes` | 时间冲突窗口，默认 120 分钟 |
| `enable_grade_check` | 是否查成绩 |
| `enable_keepalive` | 是否安装保活任务 |
| `cookies._WEU` | 任意页面的值即可，客户端按应用自动刷新 |
| `data_raw.querySetting` | 院系白名单和优先级 |

修改配置后不需要重装，下一轮检测会读取新值；修改检测间隔或保活开关后需要在 GUI
点“安装 / 更新定时任务”。

## 日常操作

```bash
DEST="$HOME/Library/Application Support/USTC-Grab/report-course"

# 状态
launchctl print gui/$(id -u)/com.ustc.grab.report | grep -E 'state|last exit|runs'

# 立即运行一次
launchctl kickstart -k gui/$(id -u)/com.ustc.grab.report

# 实时日志
tail -f "$DEST/logs/main.log"

# 暂停 / 恢复
launchctl bootout gui/$(id -u)/com.ustc.grab.report
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.ustc.grab.report.plist"
```

## 日志与数据

```text
~/Library/Application Support/USTC-Grab/report-course/
├── config.yml
├── config.yml.bak
├── data/
│   ├── courses.json
│   ├── exclude.json
│   ├── grades.json
│   └── weu_cache.json
├── logs/
│   ├── main.log
│   ├── keepalive.log
│   └── launchd-*.log
└── venv/
```

日志超过 5MB 会原地截断；同一任务上一轮未结束时，新一轮会跳过。

## 卸载

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/macos/uninstall_launchd.sh          # 保留配置与数据
bash scripts/macos/uninstall_launchd.sh --purge  # 连运行目录一起删除
```

## 故障排查

**安装后 `last exit code = 126`**
通常说明任务试图读取桌面目录。确认运行时在 Application Support，并从仓库重新运行安装脚本。

**`launchctl print` 显示 not running**
两次检测之间任务本来就是 not running；看 `runs` 和 `last exit code`，以及
`logs/main.log` 的时间戳。

**平台 403 / cookie 过期**
客户端会按应用刷新 `_WEU` 并重试一次。如果还失败，重新抓 `GS_DBLOGIN_TOKEN`、`GS_SESSIONID`、
`_WEU`、`route`，在 GUI 中保存。

**SMTP 535**
授权码错或用了登录密码。用 GUI 的“测试 SMTP”只登录、不发信。

**电脑睡眠**
合盖或睡眠时 launchd 暂停，唤醒后继续。要 7×24 运行建议放常开的 Linux 服务器。

## 安全

- `config.yml` 含平台登录态和邮箱授权码，权限 `600`，不要提交 Git。
- GUI 只监听 `127.0.0.1`，启动时生成随机令牌。
- 日志不记录 Cookie 和授权码。
