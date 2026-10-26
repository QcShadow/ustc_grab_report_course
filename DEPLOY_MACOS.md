# macOS 部署说明

本目录提供一套在 macOS 上常驻运行的部署脚本，替代仓库自带的 Linux `systemd` 方案。

## 为什么不能直接放在桌面运行

macOS 的 TCC 隐私保护会阻止 `launchd` 后台任务读取或执行 `~/Desktop` 下的文件（表现为
`last exit code = 126`）。因此部署时会把**运行时副本**同步到：

```
~/Library/Application Support/USTC-Grab/report-course
```

工作区里的仓库只作为源码：改代码后重新跑一次安装脚本即可同步过去。
`config.yml`、`data/`、`logs/`、`venv/` 属于运行时状态，安装脚本不会覆盖。

## 请求频率与 `_WEU` 缓存

平台的 `_WEU` 是**按应用隔离**的：从首页复制的 `_WEU` 去请求选课接口会 403，成绩接口又需要
自己的 `_WEU`。客户端会自动打开对应应用首页获取该应用的 `_WEU`，并缓存到
`data/weu_cache.json`（权限 `600`，已加入 `.gitignore`）。

正常运行时**不会**重复访问首页，只有缓存缺失、失效或接口返回 403 时才刷新并重试一次。
因此一轮检测固定为 3 个接口请求：已选报告、可选报告、成绩。

默认间隔 **120 秒**，约为原项目（60 秒）的一半。需要更快可以重装：

```bash
START_INTERVAL=60 bash scripts/macos/install_launchd.sh
```

## 筛选条件与院系优先级

服务端查询条件 `data_raw.querySetting` 里的 YXDM 白名单（顺序即优先级）：

1. 人工智能与数据科学学院 `229`
2. 计算机科学与技术学院 `011`
3. 信息科学技术学院 `210`
4. 自动化系 `010`
5. 电子工程与信息科学系 `006`
6. 软件学院 `225`
7. 软件学院合肥 `A13`
8. 网络空间安全学院 `221`
9. 微电子学院 `219`

客户端还会再过滤一遍：报告时间 `BGSJ` 晚于当前、报名截止 `JZSJ` 晚于当前、`KXRS > YXRS`、不在
`data/exclude.json`。候选按“院系优先级 → 报名截止升序 → 报告时间升序”排序。

时间冲突由 `conflict_window_minutes`（默认 120 分钟）判定：两场报告开始时间相差小于 2 小时视为冲突。
每轮最多成功 1 门，因此会优先提交优先级最高的那门；如果把 `max_grabs_per_cycle` 调大，脚本会跳过
与已选报告时间冲突的低优先级候选。

`pageSize` 已设为 999，一次取回全部候选（当前约 770 条），避免只看最新 100 条而漏掉还能选的报告。

## 抢课数量

`max_grabs_per_cycle` 默认 `1`：每轮最多**成功**选 1 门，失败时最多再尝试 2 门，然后结束本轮。
下一轮会重新搜索，已经选上的课程不会再出现。这样不会因为平台一次放出很多报告就给你全选上。

如果某门课一直失败（时间冲突、名额问题），把它的 `BGBM` 加进 `data/exclude.json`，脚本会跳过它；
如果它已经被选上，脚本也会自动退掉。

## 一键安装

在终端中执行（不要用 `sudo`）：

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/macos/install_launchd.sh
```

首次运行会创建运行目录、虚拟环境，并生成 `config.yml` 模板。因为配置还是占位符，
脚本会停下来并提示路径。这是预期行为。

## 填写配置

```bash
open -e "$HOME/Library/Application Support/USTC-Grab/report-course/config.yml"
```

需要替换的项：

| 配置项 | 说明 |
| --- | --- |
| `email.sender` / `email.receiver` | 发件邮箱与收件邮箱 |
| `email.smtp.server` / `port` | 默认 `smtp.qq.com:465`，按你的邮箱服务商改 |
| `email.smtp.auth_code` | SMTP **授权码**，不是邮箱登录密码 |
| `cookies.GS_DBLOGIN_TOKEN` | 登录研究生平台后 F12 → 网络 → 任意请求的 Cookie |
| `cookies.GS_SESSIONID` | 同上 |
| `cookies.route` | 同上 |
| `cookies._WEU` | 任意页面的值即可，客户端会按应用自动刷新并缓存 |
| `particular_course.BGBM` | **可选**。只有启用保活任务时才需要 |

Cookie 获取方法见仓库 README 3.2 节。`config.yml` 权限会被设为 `600`（仅本人可读），
请勿提交到 Git（`.gitignore` 已忽略）。

## 自检

纯本地检查（不联网）：

```bash
cd "$HOME/Library/Application Support/USTC-Grab/report-course"
./venv/bin/python scripts/macos/preflight.py
```

再验证 cookie 与 SMTP：

```bash
./venv/bin/python scripts/macos/preflight.py --network --smtp
```

`--network` 只发一次只读查询；`--smtp` 只登录、不发邮件。

## 成绩查询首次预热

如果开启了 `enable_grade_check`，且 `data/grades.json` 为空，第一次正式运行会把所有历史成绩
都当成新成绩，每门课发一封邮件。注册定时任务前先执行一次：

```bash
cd "$HOME/Library/Application Support/USTC-Grab/report-course"
./venv/bin/python scripts/macos/prime_grades.py
```

该脚本只读查询成绩并写入 `data/grades.json`，不会发送邮件。

## 注册定时任务

自检通过后重新执行安装脚本：

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/macos/install_launchd.sh
```

默认只注册一个 LaunchAgent：

| Label | 频率 | 作用 |
| --- | --- | --- |
| `com.ustc.grab.report` | 每 120 秒 | 退排除课 → 搜索 → 抢课 → （可选）查成绩 |

## 可选：保活任务

原项目的保活每 30 分钟退掉一门课再抢回来，借请求刷新 `_WEU`，存在**抢不回来就丢课**的风险。
现在 `_WEU` 已由客户端自动维护，默认**不安装**保活任务。

确需启用时（必须先在 `config.yml` 配好真实的 `particular_course.BGBM`）：

```bash
ENABLE_KEEPALIVE=1 bash scripts/macos/install_launchd.sh
```

## 日常操作

```bash
UID_NUM=$(id -u)
DEST="$HOME/Library/Application Support/USTC-Grab/report-course"

# 查看任务状态
launchctl print gui/$UID_NUM/com.ustc.grab.report | grep -E 'state|last exit'

# 立即手动触发一次
launchctl kickstart -k gui/$UID_NUM/com.ustc.grab.report

# 实时日志
tail -f "$DEST/logs/main.log"

# 暂停 / 恢复
launchctl bootout gui/$UID_NUM/com.ustc.grab.report
launchctl bootstrap gui/$UID_NUM "$HOME/Library/LaunchAgents/com.ustc.grab.report.plist"
```

日志超过 5MB 会自动原地截断；同一任务上一轮未结束时，新一轮会跳过，避免堆叠请求。
`data/weu_cache.json` 可以随时删除，下一次运行会自动重新获取。

## 卸载

```bash
cd "$(git rev-parse --show-toplevel)"
bash scripts/macos/uninstall_launchd.sh          # 保留配置与数据
bash scripts/macos/uninstall_launchd.sh --purge  # 连运行目录一起删除
```

## 注意事项

- **电脑必须醒着**。合盖或睡眠时 launchd 不会执行，唤醒后会继续；要 7×24 运行建议放
  在常开的 Linux 服务器上（用仓库自带 `scripts/ustc-grab.service`）。
- **Cookie 过期会按当前间隔发提醒邮件**（默认每 2 分钟一封），这是上游逻辑。收到后重新抓
  Cookie 填入 `config.yml`，再 `launchctl kickstart -k` 即可。
- `enable_grade_check` 默认关闭；开启后每一轮会额外查询一次成绩。如果只想抢报告，关掉它
  可以把请求量再降三分之一。
- 修改 `config.yml` 后不需要重装，下一轮调度就会读取新值。
