# Project Overview / 项目概览

Czech Visa Application Status Check is a compact CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
本项目是一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

Refactor 2025: Playwright-only, async workers, simplified CLI. Legacy Selenium/agent/backends removed.
2025 重构：仅 Playwright、异步并发、精简 CLI；已移除 Selenium/Agent/多后端。

## Design goals / 设计目标
- Reliable long-running batches with per-row CSV flush and retries/backoff.
- 支持长期批量运行，通过逐行写回 CSV 与重试/退避实现鲁棒性。
- Simple module-based extensibility to add more countries.
- 基于模块的可扩展性，便于添加更多国家支持。

## Module API / 模块 API
- Country module exposes `update_csv_with_status(csv_path: str, headless=True, workers=1, retries=3, log_dir='logs', **_) -> None`.
- 国家模块导出 `update_csv_with_status(csv_path: str, headless=True, workers=1, retries=3, log_dir='logs', **_) -> None`。
- Behavior：read CSV → query via Playwright → write normalized result per row → append failures to `logs/fails/YYYY-MM-DD_fails.csv`.
- 行为：读取 CSV → 使用 Playwright 查询 → 逐行写回标准化结果 → 失败行追加到 `logs/fails/YYYY-MM-DD_fails.csv`。
- Register in `visa_status.py` under `QUERY_MODULES`.
- 在 `visa_status.py` 的 `QUERY_MODULES` 中注册。

## Project layout / 项目结构
```
visa_status.py                # CLI entrypoint/dispatcher (aliases & short flags supported)
query_modules/
  └─ cz.py                    # Czech module (Playwright-only, async workers)
tools/
  └─ generate_codes.py        # code generator
logs/                         # runtime logs; fails under logs/fails/DATE_fails.csv
requirements.txt              # playwright (+ optional matplotlib)
README.md
PROJECT_OVERVIEW.md
```

## Monitor (scheduler + Email) / 监控（调度器 + 邮件）
- Email-only notifications via SMTP (Telegram removed). One or more emails per code are supported.
- 通过 SMTP 发送邮件（已移除 Telegram），每个查询码可配置 1 个或多个收件邮箱。
- Writes `SITE_DIR/status.json` and a static site directory for viewing status snapshots.
- 会写出 `SITE_DIR/status.json` 与静态站点目录，便于查看状态快照。
- Sequential design for stability: monitor uses a single page sequentially and reuses the cz querying routine; it auto-recovers the page/context on failures and retries cautiously.
- 为稳定性采用串行：监控以单页串行方式运行，复用 cz 查询逻辑；在失败时自动恢复页面/上下文，并做谨慎重试。
- Email subject: `[<Status>] <Code> - CZ Visa Status`; HTML body includes old→new when changed.
- 邮件主题：`[<状态>] <查询码> - CZ Visa Status`；HTML 正文在状态变更时包含旧→新。

## Monitor service
- Design: sequential, single page; reuse cz logic; soft-recover then rebuild page on failures.
- HTTP server: enable with SERVE=true, SITE_PORT, serves SITE_DIR as doc root.
- Systemd service (Debian):
  - Installs a unit to /etc/systemd/system/cz-visa-monitor.service
  - ExecStart: python visa_status.py monitor -e /path/to/.env
  - Restart=always; requires sudo for install/start/stop.
- CLI helpers: `--install/--uninstall/--start/--stop/--reload/--status`.

## Technical notes / 技术说明
1) CSV-first design / CSV 优先
- State is kept in CSV and updated per-row; supports resume/auditing/manual fixes.
- 状态保存在 CSV 并逐行更新；支持断点续跑、审计与人工修复。

2) Playwright workers / Playwright 并发
- One browser; N pages; headless by default; `--headless False` shows UI.
- 单浏览器；N 个页面；默认无头；`--headless False` 显示界面。

3) Overlay & result extraction / 覆盖层与结果提取
- Click/hide/remove overlays; multi-selector polling; JS fallbacks.
- 点击/隐藏/移除覆盖层；多选择器轮询；JS 回退。

4) Logging & summary / 日志与总结
- Logs under `logs/`; failures archived with `连续失败次数/Consecutive_Fail_Count`.
- 日志位于 `logs/`；失败行归档并带有 `连续失败次数/Consecutive_Fail_Count`。

## CLI notes / CLI 说明
- Aliases: `generate-codes` = `gen`/`gc`, `report` = `rep`/`r`, `cz` = `c`.
- 别名：`generate-codes` = `gen`/`gc`，`report` = `rep`/`r`，`cz` = `c`。
- Global flags: `-r/--retries`, `-l/--log-dir`.
- 全局参数：`-r/--retries`、`-l/--log-dir`。

## Reporting / 报告
- `python visa_status.py report [-i CSV] [--charts] [-o PATH]` → Markdown with optional charts.
- 通过 `python visa_status.py report [-i CSV] [--charts] [-o PATH]` 生成 Markdown（可选图表）。

## Quick start (uv) / 快速开始（uv）
See README Quick start (uv) for step-by-step setup.
详细步骤见 README 的“Quick start (uv)”。

## Version control hygiene / 版本控制规范
Ignored by default (.gitignore) / 默认忽略：
- Runtime artifacts: `logs/`, `reports/`, `monitor_site/`, `.output/`。
- Credentials and secrets: `.env`, `.env.*`, `*.secrets`, `credentials.json`。

CSV files are tracked as data. 如需忽略本地测试 CSV，可添加更窄规则（如 `*.local.csv`）。
