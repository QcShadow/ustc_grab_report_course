# USTC 报告选课助手

基于 [1540975647/ustc_grab_report_course](https://github.com/1540975647/ustc_grab_report_course) 的
macOS / Windows 图形化版本。

界面只保留三件事：

- **自动抢课配置**：邮箱、平台 Cookie、院系优先级、检测间隔
- **已选报告预览**：打开页面自动读取，也可以手动刷新
- **启用 / 停止**：右上角一个按钮控制定时任务

## 快速开始

要求 Python 3.9+，能访问 `https://yjs1.ustc.edu.cn`。

### macOS

```bash
git clone https://github.com/QcShadow/ustc_grab_report_course.git
cd ustc_grab_report_course
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python gui.py
```

也可以直接双击项目根目录的 `start_gui.command`。

配置与数据保存在：

```text
~/Library/Application Support/USTC-Grab/report-course
```

### Windows

1. 安装 Python 3.9+，勾选 **Add Python to PATH**
2. 下载或克隆本项目
3. 双击 `setup_windows.bat`

脚本会自动创建 `venv`、安装依赖并打开 GUI。以后双击 `start_gui.bat`。

## 使用

1. 填发件邮箱、收件邮箱、SMTP 服务器、端口、授权码。
   - 163：`smtp.163.com:465`
   - QQ：`smtp.qq.com:465`
   - 授权码不是邮箱登录密码。
2. 填平台 Cookie：Chrome 登录 → F12 → Network → 任意 `gsapp` 请求 → Request Headers → `Cookie`。
3. 调整院系顺序。越靠前优先级越高；时间冲突时优先选靠前的院系。
4. 设置检测间隔和是否查询成绩。
5. 点 **保存配置**。
6. 打开右上角“自动抢课”开关。
7. 下方“已选报告”会自动刷新，也可以手动刷新。

配置分成“账号与通知 / 院系优先级 / 基本设置”三段，切换不会丢失未保存内容。

关闭右上角开关即停止抢课；配置和数据会保留。

## 配置

配置文件（macOS）：

```text
~/Library/Application Support/USTC-Grab/report-course/config.yml
```

Windows 在项目根目录的 `config.yml`。

必填：

| 项 | 说明 |
| --- | --- |
| `email.sender` / `email.receiver` | 发件、收件邮箱 |
| `email.smtp.server` / `port` / `auth_code` | SMTP 服务器、端口、授权码 |
| `cookies.GS_DBLOGIN_TOKEN` | 平台登录 Cookie |
| `cookies.GS_SESSIONID` | 平台会话 Cookie |
| `cookies._WEU` | 应用令牌，客户端会自动刷新 |
| `cookies.route` | 平台路由 Cookie |

可选 / 高级参数（GUI 不展示，直接改 `config.yml`）：

| 项 | 默认 | 说明 |
| --- | --- | --- |
| `schedule_interval_seconds` | `120` | 检测间隔 |
| `enable_grade_check` | `false` | 是否查成绩 |
| `max_grabs_per_cycle` | `1` | 每轮最多成功选几门 |
| `conflict_window_minutes` | `120` | 时间冲突窗口 |
| `data_raw.pageSize` | `999` | 一次取回的候选数 |
| `enable_keepalive` | `false` | 保活任务（通常不需要） |

`config.yml` 含平台登录态和邮箱授权码，权限为 `600`，不要提交到 Git。

## 定时任务

- macOS：launchd，任务标识 `com.ustc.grab.report`
- Windows：任务计划程序，任务名 `USTC-Grab-Report`

日志：

```text
# macOS
~/Library/Application Support/USTC-Grab/report-course/logs/main.log

# Windows
项目目录\logs\main.log
```

## 注意

- 电脑睡眠或合盖时任务暂停，唤醒后继续。
- Cookie 过期时会发一次提醒邮件；重新抓 Cookie 填入 GUI 即可。
- 默认每轮最多成功选 1 门，避免一次选太多报告。
- 已选报告不会被自动替换；新课与已选课冲突时平台会拒绝。
- GUI 只监听 `127.0.0.1`，启动时生成随机访问令牌。

## 许可

[MIT](LICENSE)

原项目：[1540975647/ustc_grab_report_course](https://github.com/1540975647/ustc_grab_report_course)
