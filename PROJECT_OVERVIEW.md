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
│  └─ cz.py              # Czech module (example)
├─ tools/
│  └─ generate_codes.py  # code generator
├─ logs/                 # runtime logs and failures
├─ requirements.txt      # runtime dependencies
└─ README.md
```

## Detailed technical notes / 技术细节说明

1) CSV-first design / CSV 优先设计
- All state is kept in the CSV and updated per-row; this enables easy resume, auditing and manual fixes.
- 所有状态保存在 CSV 中并逐行更新；支持断点续跑、审计与人工修复。

2) Browser automation / 浏览器自动化
- Uses Selenium ChromeDriver and attempts to prefer an explicit `--driver-path`.
- 使用 Selenium ChromeDriver，优先推荐传入 `--driver-path`。
- If `webdriver-manager` is installed the tool can auto-download a matching chromedriver at runtime.
- 若安装了 `webdriver-manager`，程序可在运行时自动下载匹配的 chromedriver。
 - Experimental Playwright backend (browser-use) available via subcommand `cz-bu` or `cz --backend playwright` (feature branch). Sequential queries only, may become default after evaluation.
 - 实验性 Playwright 后端（browser-use）可通过 `cz-bu` 子命令或 `cz --backend playwright` 使用（特性分支）。当前为顺序查询，评估后可能成为默认。

3) Overlay handling / 覆盖层处理
- Strategy: targeted click on refuse/close buttons → JS-dispatched MouseEvent → hide/remove overlays → retry.
- 策略：优先点击拒绝/关闭按钮 → 发送 JS MouseEvent → 隐藏/移除覆盖层 → 重试。

4) Result extraction / 结果提取
- Multi-selector polling, Selenium `.text` read and JS innerText/textContent fallbacks.
- 多选择器轮询、Selenium `.text` 读取与 JS innerText/textContent 回退。
- If needed, a page-level JS scan extracts candidate status fragments when elements are present but not visible.
- 如有必要，页面级 JS 扫描会在元素存在但不可见时提取状态片段。

5) Resilience & retries / 弹性与重试
- Per-row retry count with exponential backoff and jitter.
- 每条支持可配置的重试次数，并采用带抖动的指数退避。
- Driver/session recreation on recoverable errors to continue long runs.
- 在可恢复错误上进行驱动/会话重建以支持长时间运行。

6) Logging & diagnostics / 日志与诊断
- Logs written under `logs/` and failing rows appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- 日志写入 `logs/`，失败条目追加到 `logs/fails/YYYY-MM-DD_fails.csv`。
- Page HTML snapshots saved only for Unknown/Query Failed rows to reduce noise.
- 页面 HTML 快照仅在 Unknown/Query Failed 时保存，以减少噪声文件。

## How to extend (add a country) / 如何扩展（添加国家模块）
1. Create `query_modules/xy.py` (xy = ISO-2 code).
2. Implement `def query_status(code: str, driver=None, **opts) -> str:` and return a normalized status.
3. Register the module in `visa_status.py` mapping.

## Concurrency / 并发 (workers)

- Purpose: support higher throughput by running multiple query workers in parallel while reusing browser instances via a driver pool. / 目的：通过并行运行多个 worker 并重用浏览器实例（驱动池）来提高吞吐量。

- CLI: `--workers N` (default 1). When N>1 the Czech module uses a ThreadPoolExecutor and a simple driver pool pre-creating up to N webdriver instances. / 命令行：`--workers N`（默认 1）。当 N>1 时，捷克模块使用 ThreadPoolExecutor 及一个简单的驱动池，预创建最多 N 个 webdriver 实例。

- Behavior: each completed task is flushed immediately to the input CSV and failing rows are appended to `logs/fails/YYYY-MM-DD_fails.csv`. This preserves resume/replication semantics even during concurrent runs. / 行为：每个完成的查询会立刻写回输入 CSV，失败条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv`，即便并发运行也能保持可恢复/可审计语义。

- Ctrl+C handling: concurrent runs catch `KeyboardInterrupt`, cancel pending tasks, flush in-memory progress to CSV, close all browser instances and then exit. / Ctrl+C 处理：并发运行会捕获 `KeyboardInterrupt`，取消挂起任务、将内存中的进度写回 CSV、关闭所有浏览器实例并退出。

- Resource note: each Chrome instance consumes memory (>= ~150-300MB depending on flags and page complexity). Limit `--workers` on low-memory machines. Consider N <= available_memory / 300MB as a rough starting point. / 资源提示：每个 Chrome 实例会消耗内存（取决于参数和页面，通常 >=150-300MB）。在低内存机器上请限制 `--workers`。一个粗略估算：N 不应超过 可用内存 ÷ 300MB。

- Alternatives: for stronger isolation or to avoid GIL/driver thread contention, consider a multi-process model (ProcessPool) or using a remote Selenium Grid. / 备选方案：如需更强隔离或避免线程/驱动争用，可考虑多进程模型（ProcessPool）或外部 Selenium Grid。

## Reporting module / 报告模块（详细分析）

- Location / 位置: `tools/report.py` （通过 `python visa_status.py report` 调用）。
- Purpose / 目的: 生成面向申请者与维护者的可读性强的 Markdown 报告，帮助评估：
	- 当前通过率 (Granted 占比)
	- 拒签/关闭与查询失败情况
	- 审理中(Proceedings) 积压量与比例 (Backlog ratio)
	- 日/周/月的趋势与波动 (含周成功率环比 Δ)
	- 工作日活跃度（用于优化查询码生成：聚焦周一/周二等高处理日）
	- SLA 超期（Proceedings 超过 60 天）
- Ignore strategy / 忽略策略: 全局忽略 `Not Found` 行（无开启开关）。
- Command / 命令:
```bash
python visa_status.py report -i query_codes.csv [--charts]
```
- Output / 输出: `reports/<YYYY-MM-DD>/<HH-MM-SS>/summary.md` 分层目录（日期/时间）精确到秒；图表 PNG 与报告同目录。
- Key metrics / 关键指标:
	- success_rate = Granted / counted
	- processing_rate = (Granted + Rejected)/counted
	- rejection_rate = Rejected/Closed / counted
	- backlog_ratio (每日与累计 Proceedings 占比)
	- weekly Δsuccess%
	- SLA overdue ratio (Proceedings 超过60天占当前 Proceedings 比例)
	- weekday peak (峰值工作日)
	- ISO Week (报告标题中显示当前 UTC ISO 周)
- Submission volume / 提交量: 仅统计“有效”行（非空且非 Not Found），并对日历跨度零填充方便趋势对比。
- Charts (optional with --charts & matplotlib): daily success vs backlog line, weekly success bar, distribution pie。
- Auto-install / 自动安装: 在未禁用自动安装且指定 `--charts` 时尝试安装缺失的 `matplotlib`。
- Extensibility / 可扩展: 未来若保留多次抓取快照，可进一步分析平均处理时长 / Proceedings→Granted 转化周期。

## Links / 链接
- README (user guide): [README.md](README.md)
- README（用户指南）：[README.md](README.md)

## Code generator extensions / 代码生成器扩展
- New options:
	- `--exclude-weekdays` (aliases: `--exclude`, `--排除`, `--日期排除`) accept digits 1..7 for Mon..Sun, forms: `35`, `3 5`, `3,5`.
	- `--prefix` (alias: `--前缀`) sets code prefix (default `PEKI`).
- Order of filtering:
	1. Start with weekdays (Mon-Fri) unless `--include-weekends`.
	2. Remove any weekday codes present in exclude set.
	3. Generate `<PREFIX>YYYYMMDD####` sequences.
- Prefix normalization: trimmed; fallback to PEKI if empty after trim.

*** End of overview / 概览结束 ***
