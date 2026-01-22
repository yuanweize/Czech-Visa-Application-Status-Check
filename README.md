
# Czech Visa Application Status Check / 捷克签证状态批量查询

> Modern, reliable, and user-friendly tool for bulk checking Czech visa application status, with smart notifications and user management.  
> 现代化、可靠、易用的捷克签证批量查询与智能通知工具，支持用户自助管理。

---

- [Czech Visa Application Status Check / 捷克签证状态批量查询](#czech-visa-application-status-check--捷克签证状态批量查询)
	- [Features / 主要功能](#features--主要功能)
	- [Quick Start / 快速上手](#quick-start--快速上手)
	- [Configuration / 配置说明](#configuration--配置说明)
	- [Usage / 常用用法](#usage--常用用法)
	- [Monitoring \& Notification / 监控与通知](#monitoring--notification--监控与通知)
	- [User Management / 用户管理](#user-management--用户管理)
	- [Technical Highlights / 技术亮点](#technical-highlights--技术亮点)
	- [Logging \& Service / 日志与服务部署](#logging--service--日志与服务部署)
	- [FAQ / 常见问题](#faq--常见问题)
	- [Contributing / 贡献指南](#contributing--贡献指南)
	- [Links / 相关链接](#links--相关链接)
	- [License / 许可证](#license--许可证)

---

## Features / 主要功能

- Bulk Status Query / 批量状态查询：捷克移民局签证状态批量查询
- Smart Code Generation / 智能码生成：灵活日期区间+工作日/排除
- Automated Monitoring / 自动监控：后台定时监控，频率可配
- Email Notification / 邮件通知：HTML 提醒+频控；验证码邮件即时优先
- User Management / 用户管理：Web 界面、邮件验证、验证码保护
- Hot Reload / 热更新：.env 配置实时热加载，无需重启
- Security / 安全：频控、文件访问控制、会话管理

## Quick Start / 快速上手

1) Clone & Install / 克隆与安装

```bash
# Clone the repo / 克隆仓库
git clone https://github.com/yuanweize/Czech-Visa-Application-Status-Check.git
cd Czech-Visa-Application-Status-Check

# (Recommended 推荐) Use uv for fast env management
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate        # Linux/macOS
# source .venv/Scripts/activate   # Windows Git Bash
uv pip install -r requirements.txt
playwright install chromium

# (Alternative 备选) Use pip
python -m pip install -r requirements.txt
playwright install chromium
```

2) Minimal run / 最小运行

```bash
# Generate codes 生成查询码
python visa_status.py gen -o query_codes.csv -s 2025-06-01 -e 2025-06-07 -n 5

# Check status 批量查询
python visa_status.py cz -i query_codes.csv -w 4 -H true

# Generate report 生成报告
python visa_status.py report --charts
```

## Configuration / 配置说明

- Base / 基础
	- HEADLESS=true|false: Playwright 无头模式（默认 true）
	- SITE_DIR=site: 输出 status.json 与静态站点根目录
	- MONITOR_LOG_DIR=logs/monitor: 监控日志目录（默认 logs/monitor）
	- SERVE=true|false: 是否启动内置 HTTP（根目录为 SITE_DIR，端口 SITE_PORT）
	- SITE_PORT=8000: 站点端口（默认 8000）
	- DEFAULT_FREQ_MINUTES=60: 全局默认监控频率（分钟）
	- WORKERS=1: 查询并发页面数

- SMTP
	- SMTP_HOST, SMTP_PORT(465/587), SMTP_USER, SMTP_PASS, SMTP_FROM
	- EMAIL_MAX_PER_MINUTE=10: 每分钟最大发信数（队列限流）
	- EMAIL_FIRST_CHECK_DELAY=30: 首次记录延迟发送秒数（避免首次风暴）

- Codes / 监控代码配置（二选一，可混用）
	- CODES_JSON='[ {"code":"PEKI2025...","channel":"email","target":"you@mail.com","freq_minutes":30,"note":"..."} ]'
		- channel 可为空字符串或省略表示关闭通知
		- freq_minutes 为空/省略将使用 DEFAULT_FREQ_MINUTES
	- 编号格式 Numbered:
		- CODE_1=PEKI2025...  CHANNEL_1=email  TARGET_1=you@mail.com  FREQ_MINUTES_1=30  NOTE_1=xxx
		- CODE_2=...

Example .env / 配置示例：

```env
HEADLESS=true
SITE_DIR=site
SERVE=false
SITE_PORT=8000
DEFAULT_FREQ_MINUTES=60
WORKERS=1

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=user@example.com
SMTP_PASS=your-app-password
SMTP_FROM=user@example.com
EMAIL_MAX_PER_MINUTE=10
EMAIL_FIRST_CHECK_DELAY=30

CODES_JSON='[{"code":"PEKI202509040004","channel":"email","target":"you@mail.com","freq_minutes":30}]'
# 或者 / or
# CODE_1=PEKI202509080001
# CHANNEL_1=email
# TARGET_1=you@mail.com
# FREQ_MINUTES_1=45
```

Notes / 说明：
- 所有 .env 变更在守护模式下会被自动热加载（安装 watchdog 时）。
- 重复的查询码会导致启动失败，请确保唯一。

## Usage / 常用用法

- Generate codes / 生成代码
	- python visa_status.py generate-codes -o query_codes.csv -s 2025-06-01 -e 2025-06-30 -n 5
	- 别名 Aliases: gen, gc
	- 选项 Options: --include-weekends, --exclude 35, --prefix ABC

- Clean CSV / 清理与导出 JSON（用于监控 CODES_JSON）
	- 仅代码 JSON 行：python visa_status.py cl -fm
	- 带字段 JSON 行：python visa_status.py cl -fm t:your@mail.com,f:60
	- 紧凑数组 JSON：python visa_status.py cl -fma t:your@mail.com,f:60
	- 输入/输出：-i input.csv，-o output.(csv|json)

- Check status / 批量查询
	- python visa_status.py cz -i query_codes.csv -w 4 -H true|false
	- 别名 Alias: c

- Monitor / 定时监控与通知
	- 单次：python visa_status.py monitor --once -e .env
	- 守护：python visa_status.py monitor -e .env
	- systemd（Debian/Ubuntu）
		- 安装：sudo python visa_status.py monitor --install -e /path/to/.env
		- 启动/状态：sudo python visa_status.py monitor --start / python visa_status.py monitor --status
		- 停止/重载/卸载：--stop / --reload / --uninstall；重启：--restart
		- 可用 --python-exe 指定解释器

- Report / 报告（Markdown + 可选图表）
	- python visa_status.py report -i query_codes.csv --charts -o reports/summary.md
	- 默认输出目录：reports/YYYY-MM-DD/HH-MM-SS/summary.md，并归档输入 CSV

CSV format example / CSV 示例：

```csv
日期/Date,查询码/Code,签证状态/Status
2025-06-02,PEKI202506020001,Rejected/Closed / 被拒绝/已关闭
2025-06-03,PEKI202506030002,Granted / 已通过
```

行为说明 / Behavior:
- 已为最终非失败状态的行将被跳过；`Query Failed / 查询失败` 视为待重试。
- 所有结果被标准化为有限集合：Granted、Rejected/Closed、Proceedings、Not Found、Unknown、Query Failed。

## Monitoring & Notification / 监控与通知

- What triggers email / 何时发信：
	- 首次记录或状态变化时发送；主题示例 `[Granted] PEKI2025... - CZ Visa Status`
- Queue & rate limiting / 队列与限流：
	- 普通通知走队列，按 EMAIL_MAX_PER_MINUTE 限流，防止 SMTP 过载
	- 首次大量 codes 时，结合 EMAIL_FIRST_CHECK_DELAY 做平滑延迟
- Verification priority / 验证码优先级：
	- 用户管理的验证码邮件走“即时通道”，绕过队列，保证秒级送达
- SMTP pool / 连接池：
	- 复用连接并带 NOOP 健康检查与 AUTH 节流，减少“过多 AUTH”导致的封禁

状态文件 / Status file：
- 监控周期结束会写入 `SITE_DIR/status.json`（仅字符串状态）；当 SERVE=true 时可在 `SITE_PORT` 提供静态站点。

## User Management / 用户管理

- Web 界面：在主站点（SERVE=true）工具栏中进入，添加/查看/删除自己的查询码
- 邮箱验证：10 分钟限时链接 + 6 位验证码，防止滥用
- 简单 CAPTCHA：基础运算题，拦截机器人
- 无数量限制：用户可按需管理任意数量代码
- 安全：100 req/min 频控、文件白名单、统一错误页

快速开始：

```bash
# 开启 Web 界面（.env 中设置 SERVE=true）
python visa_status.py monitor -e .env
# 访问 http://localhost:8000
```

## Technical Highlights / 技术亮点

- CSV-first：所有状态保存在 CSV，断点续查、易审计
- Playwright：单浏览器多页面并发，默认无头
- 智能邮件：队列+每分钟限流；验证码即时优先；SMTP 连接池
- 热更新：.env 改动自动生效（watchdog）
- 安全：频控、文件白名单、统一错误跳转、详细日志
- 自动日志轮换：长期运行更稳健

## Logging & Service / 日志与服务部署

- 日志轮换：保持文件 < 2MB，轮换保留最近 1000 行；目录 `logs/monitor`（可配 MONITOR_LOG_DIR）
- 周期日志：记录每轮处理、邮件通知、热更新事件与统计
- systemd：支持一键安装、启动、停止、状态、重载、卸载与重启
- 热更新：CLI 与 systemd 模式均支持；变更在下个周期生效

示例日志 / Sample:
```
[2025-09-17T10:30:00] Processing 34 codes (3 added, 1 removed, 2 modified)
[2025-09-17T10:30:03] notify Email code=PEKI202508140001 to=user@example.com ok=True
[2025-09-17T10:30:45] .env changed detected, reloading configuration
```

## FAQ / 常见问题

- 收不到邮件？
	- 检查 SMTP 配置、垃圾箱、频控（EMAIL_MAX_PER_MINUTE）
- Playwright 报错？
	- 确保安装 playwright 与 chromium：python -m playwright install chromium
- 如何设置监控频率？
	- 修改 .env 的 DEFAULT_FREQ_MINUTES 或单个 code 的 freq_minutes
- 如何部署为服务？
	- 见上文 systemd 小节

## Contributing / 贡献指南

- 欢迎 PR（建议先开 issue 讨论）；遵循现有代码风格，附必要测试
- 文档/翻译/功能/安全改进均欢迎；新增国家模块请放在 `query_modules/`

## Links / 相关链接

- GitHub Repo: https://github.com/yuanweize/Czech-Visa-Application-Status-Check
- Issues: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues
- Discussions: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/discussions

## License / 许可证

[MIT](LICENSE)


