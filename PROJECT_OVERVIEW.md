# Project Overview / 项目概览

Czech Visa Application Status Check is a compact CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
Czech Visa Application Status Check 是一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

## Design goals / 设计目标
- Reliable long-running batches with per-row CSV flush and retries/backoff.
- 支持长期批量运行，通过逐行写回 CSV 与重试/退避实现鲁棒性。
- Simple module-based extensibility to add more countries.
- 基于模块的可扩展性，便于添加更多国家支持。

## Module API (summary) / 模块 API（摘要）
- Each country module should expose a function `query_status(code: str, **opts) -> str` which returns a normalized status string.
- 每个国家模块应导出函数 `query_status(code: str, **opts) -> str`，返回标准化状态字符串。
- Modules may accept driver configuration and should handle driver recreation if necessary.
- 模块可以接受驱动配置并在必要时处理驱动重建。
- Place modules under `query_modules/<iso>.py` and register the module in `visa_status.py`.
- 将模块放在 `query_modules/<iso>.py` 下，并在 `visa_status.py` 中注册。

## Project layout / 项目结构
```
query_codes_project/
├─ visa_status.py        # CLI entrypoint and dispatcher
├─ query_modules/
# Project Overview / 项目概览

Czech Visa Application Status Check is a compact CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
Czech Visa Application Status Check 是一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

Refactor 2025: Playwright-only, minimal CLI, async concurrency. Selenium/agent/backends removed.
2025 重构：仅 Playwright、精简 CLI、异步并发；已移除 Selenium、Agent 与多后端。

## Design goals / 设计目标
- Reliable long-running batches with per-row CSV flush and retries/backoff.
- 支持长期批量运行，通过逐行写回 CSV 与重试/退避实现鲁棒性。
- Simple module-based extensibility to add more countries.
- 基于模块的可扩展性，便于添加更多国家支持。

## Module API / 模块 API
- Each country module exposes `update_csv_with_status(csv_path: str, headless=True, workers=1, retries=3, log_dir='logs', **_) -> None`.
- 每个国家模块导出 `update_csv_with_status(csv_path: str, headless=True, workers=1, retries=3, log_dir='logs', **_) -> None`。
- Behavior 行为：读取 CSV → 使用 Playwright 查询 → 逐行回写标准化结果 → 失败行追加至 `logs/fails/YYYY-MM-DD_fails.csv`。
- Place modules under `query_modules/<iso>.py` and register in `visa_status.py`'s `QUERY_MODULES`.
- 模块放于 `query_modules/<iso>.py` 下，并在 `visa_status.py` 的 `QUERY_MODULES` 中注册。

## Project layout / 项目结构
```
visa_status.py                # CLI entrypoint and dispatcher (supports short flags & aliases)
query_modules/
  └─ cz.py                    # Czech module (Playwright-only, async workers)
tools/
  └─ generate_codes.py        # code generator
logs/                         # runtime logs and fails (logs/fails/DATE_fails.csv)
requirements.txt              # playwright (+ optional matplotlib)
README.md
PROJECT_OVERVIEW.md
```

## Technical notes / 技术说明

1) CSV-first design / CSV 优先设计
- State is kept in the CSV and updated per-row; supports resume, auditing, and manual edits.
- 所有状态保存在 CSV 中并逐行更新；支持断点续跑、审计与人工修复。

2) Browser automation (Playwright) / 浏览器自动化（Playwright）
- Chromium via Playwright async API; headless by default; pass `--headless False` to show UI.
- 基于 Playwright 的 Chromium 异步 API；默认无头；传 `--headless False` 显示界面。
- Single browser per run; N pages as workers for concurrency (`--workers N`).
- 每次运行仅一个浏览器；使用 N 个页面作为并发 worker（`--workers N`）。

CLI notes / CLI 说明：
- Subcommand aliases: `generate-codes` = `gen`/`gc`, `report` = `rep`/`r`, `cz` = `c`.
- Short flags: global `-r/--retries`, `-l/--log-dir`; `gen` supports `-s/-e/-n/-w/-x/-p/-o`; `report` supports `-i/-o/-c`; `cz` supports `-i/-H/-w` (retries via global `-r`).

3) Overlay handling / 覆盖层处理
- Targeted refuse/close clicks → JS-dispatched events → hide/remove overlays → proceed.
- 策略：优先点击拒绝/关闭按钮 → 发送 JS 事件 → 隐藏/移除覆盖层 → 继续。

4) Result extraction / 结果提取
- Multi-selector polling with Playwright; JS innerText/textContent fallbacks and page-scan.
- 基于 Playwright 的多选择器轮询；必要时使用 JS innerText/textContent 回退与页面级扫描。

5) Resilience & retries / 弹性与重试
- Per-row retry with small backoff; best-effort overlay dismissal before interaction.
- 每条带小退避的重试；在交互前尽力清理覆盖层。

6) Logging & diagnostics / 日志与诊断
- Logs under `logs/`; failing rows appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- 日志写入 `logs/`；失败条目追加到 `logs/fails/YYYY-MM-DD_fails.csv`。

## Concurrency / 并发
- Use `--workers N` to run N parallel workers (pages). Each worker reuses the same browser instance.
- 使用 `--workers N` 运行 N 个并发 worker（页面）。所有 worker 共享同一浏览器实例。
- Ctrl+C attempts graceful shutdown: pending tasks cancelled, progress flushed, browser closed.
- Ctrl+C 尝试优雅退出：取消未完成任务、刷新进度并关闭浏览器。
- Resource note: Each worker uses memory; on low-memory machines limit workers.
- 资源提示：每个 worker 会占用内存；低内存环境请降低 worker 数。

## How to extend / 如何扩展
1. Create `query_modules/xy.py` (xy = ISO-2 code).
2. Implement `update_csv_with_status(csv_path: str, headless=True, workers=1, retries=3, log_dir='logs', **_)` using Playwright.
3. Register in `visa_status.py`'s `QUERY_MODULES`.

## Reporting / 报告
- `python visa_status.py report [-i CSV] [--charts] [-o PATH]` produces a Markdown report and archives the input CSV into the report folder.
- 通过 `python visa_status.py report [-i CSV] [--charts] [-o PATH]` 生成 Markdown 报告，并将输入 CSV 归档到报告文件夹。

## Troubleshooting / 故障排查
- Ensure Playwright & Chromium are installed:
  - `pip install playwright`
  - `python -m playwright install chromium`
- 若启动报错，请先安装 Playwright 与 Chromium：
  - `pip install playwright`
  - `python -m playwright install chromium`

*** End of overview / 概览结束 ***
- Submission volume / 提交量: 仅统计“有效”行（非空且非 Not Found），并对日历跨度零填充方便趋势对比。
