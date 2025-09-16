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
requirements.txt              # playwright (+ optional matplotlib + watchdog for hot reloading)
README.md
PROJECT_OVERVIEW.md
```

## Monitor (scheduler + Email) / 监控（调度器 + 邮件）
- Email-only via SMTP (Telegram removed). 可为每个查询码配置 1 个或多个收件邮箱。
- Writes `SITE_DIR/status.json`（仅字符串状态）与静态站点目录；当 `SERVE=true` 时内置 HTTP 将以 `SITE_DIR` 为根在 `SITE_PORT` 端口提供访问。
- Sequential for stability; per-cycle browser lifecycle: create Chromium only during a cycle and close it afterward to minimize idle CPU. 复用 cz 查询逻辑，失败时软恢复并必要时重建页面/上下文。
- Email subject: `[<Status>] <Code> - CZ Visa Status`; HTML body shows old→new when changed.
**Hot reloading / .env 热更新**

The monitor supports automatic hot reloading of the `.env` configuration file. When enabled, any changes to `.env` are detected and the configuration is reloaded without restarting the service.

- **Enabled automatically in daemon mode** (not `--once`) **when the `watchdog` package is installed**.
- If you see `Warning: watchdog not available, .env hot reloading disabled`, install watchdog:
  ```bash
  python -m pip install watchdog
  # or
  uv pip install watchdog
  ```
- Hot reloading works for both CLI and systemd service modes.
- Configuration changes take effect in the next monitoring cycle.

监控器支持 `.env` 文件的自动热更新。只要安装了 `watchdog` 包，修改 `.env` 文件会自动检测并重新加载配置，无需重启服务。

如出现 `Warning: watchdog not available, .env hot reloading disabled`，请安装 watchdog：
```bash
python -m pip install watchdog
# 或
uv pip install watchdog
```

热更新适用于 CLI 和 systemd 服务模式。配置更改会在下一个监控周期生效。

---

## Monitor service
- HTTP server: `SERVE=true` + `SITE_PORT` → serves `SITE_DIR` as doc root.
- Systemd (Debian):
  - Installs a unit to /etc/systemd/system/cz-visa-monitor.service
  - ExecStart: python visa_status.py monitor -e /path/to/.env
  - Restart=always; requires sudo for install/start/stop.
  - Prefers uv virtualenv (`.venv/bin/python`) if present; override with `--python-exe` at install time.
- CLI helpers: `--install/--uninstall/--start/--stop/--reload/--restart/--status`（`--status` 使用 `--no-pager`）。

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
