 # Czech Visa Application Status Check / 捷克签证状态批量查询

A small CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)  
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Tech stack / 技术栈
Python 3.8+。

Selenium WebDriver (Chrome) for browser automation.
使用 Selenium WebDriver（Chrome）进行浏览器自动化。

webdriver-manager (optional) to auto-download chromedriver when available.
webdriver-manager（可选）在可用时用于自动下载 chromedriver。

CSV-based I/O using Python's stdlib (`csv`) — no Excel / openpyxl dependency.
使用 Python 标准库的 CSV（`csv`）进行输入输出 — 无 Excel / openpyxl 依赖。

Basic logging to files under `logs/`.
基本日志写入 `logs/` 目录。

## What it does / 功能简介
Generate visa application query codes and write them to a CSV for later querying.
生成签证申请查询码并写入 CSV 以供后续查询。

Read a CSV of codes and query the Czech Immigration Office website per-row, then write normalized results back to the CSV immediately.
读取包含查询码的 CSV，逐行查询捷克移民局网站，并将标准化结果立即写回 CSV。

Save failing rows after retries to daily failure files in `logs/fails/` for offline retry.
在重试后仍失败的条目保存到 `logs/fails/` 的按日文件，便于离线重试。

## Project structure (for contributors) / 项目结构（面向贡献者）
- `visa_status.py` — CLI entrypoint and dispatcher that registers country modules and exposes commands.
- `query_modules/` — directory containing one module per country (e.g. `cz.py`). Each module implements a simple querying interface.
- `tools/generate_codes.py` — code generator utility.
- `logs/` — run and fail logs; failing rows are appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- `requirements.txt` — Python dependencies (e.g. selenium, webdriver-manager).

设计说明：查询器为模块化设计——要添加新的国家支持，请在 `query_modules/<iso>.py` 下添加文件，按照 `PROJECT_OVERVIEW.md` 中描述的模块 API 实现并在 `visa_status.py` 中注册。

## Quick start / 快速开始
1) Install dependencies / 安装依赖
Python package requirements are listed in `requirements.txt`.
Python 依赖项列在 `requirements.txt` 中。

```bash
python -m pip install -r requirements.txt
```

2) Generate codes / 生成查询码
Generate a CSV of visa application query codes.
生成签证申请查询码的 CSV。

Simple example:
简单示例：
```bash
python visa_status.py generate-codes
```

Advanced examples / 高级用法示例：
1) 从2025年6月1日到2025年6月30日之间，以每天5个查询码的量生成查询码 / Generate 5 per day for June:
```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-06-30 --per-day 5
```
2) 排除周三与周五(3,5) / Exclude Wed & Fri while keeping only weekdays (default already excludes weekends):
```bash
python visa_status.py generate-codes --start 2025-06-01 --end 2025-06-14 --exclude-weekdays 35 -o no_wed_fri.csv
```
	可等价使用 `--exclude 3,5` 或 `--排除 35`。
3) 包含周末但排除周日，且使用自定义前缀 SHAN / Include weekends, exclude Sunday, custom prefix:
```bash
python visa_status.py generate-codes --start 2025-06-01 --end 2025-06-07 --include-weekends --exclude 7 --prefix SHAN -o shan_codes.csv
```
4) 使用中文参数别名 / Using Chinese aliases:
```bash
python visa_status.py generate-codes --前缀 ABC --日期排除 24 --start 2025-06-01 --end 2025-06-10
```

3) Query statuses (Czech) / 查询状态（捷克）
Run the Czech checker against an input CSV.
对输入 CSV 运行捷克查询器。

Simple example (recommended):
简单示例（推荐）：
```bash
python visa_status.py cz
```

Experimental Playwright backend (browser-use) / 实验性 Playwright 后端：
You can try the Playwright implementation either via the separate subcommand or backend flag.
可以通过独立子命令或 backend 参数尝试 Playwright 实现。

Two ways / 两种方式:
1) Short experimental subcommand / 简写实验子命令:
```bash
python visa_status.py cz-bu
```
2) Backend flag on cz / 在 cz 上通过 backend 参数:
```bash
python visa_status.py cz --backend playwright
```
Fallback will occur to Selenium if Playwright deps missing. / 若缺少 Playwright 依赖会自动回退到 Selenium。
NOTE: browser-use / Playwright path currently requires Python 3.11+ and installation of package + browsers.
注意：browser-use / Playwright 需要 Python 3.11+，并需要安装相应包与浏览器二进制。
Performance & size note / 体积与性能说明:
First run will download a Chromium build (~150MB+) and many optional LLM/cloud deps pulled by browser-use. This is optional: if you only need classic Selenium keep using `cz` without `--backend playwright`. / 首次运行会下载 Chromium (~150MB+) 以及 browser-use 引入的众多可选依赖；若只需经典 Selenium，可继续使用 `cz`（不加 `--backend playwright`）。

### Agent Mode (DeepSeek R1 via SiliconFlow) / Agent 模式（通过 SiliconFlow 使用 DeepSeek R1）

The experimental Playwright path supports an optional LLM Agent to navigate & extract status more robustly.
实验性 Playwright 路径支持可选的 LLM Agent，以在站点结构变化时更稳健地导航与提取状态。

Default model / 默认模型: `deepseek-ai/DeepSeek-R1` (via SiliconFlow proxy).

Environment variables (put them in `.env`):
环境变量（写入 `.env` 文件）：
```
SILICONFLOW_API_KEY=sk-your-key-here
AGENT_MODEL=deepseek-ai/DeepSeek-R1  # 可覆盖为其他 DeepSeek 模型
# 可选：SiliconFlow 自定义基础 URL (若非默认):
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

Usage / 用法:
```bash
python visa_status.py cz-bu --agent
# 或
python visa_status.py cz --backend playwright --agent
```

Customize steps or model / 自定义步数或模型:
```bash
python visa_status.py cz-bu --agent --agent-model deepseek-ai/DeepSeek-R1 --agent-max-steps 16
```

If the API key is missing or the DeepSeek class is unavailable, the tool silently falls back to deterministic mode.
若缺少 API Key 或 DeepSeek 类不可用，将自动回退到确定性模式。

Advanced example (when you need explicit driver control):
高级示例（需要显式驱动控制时使用）：
- Use `--driver-path` to explicitly point to a Chrome binary; if you have multiple Chrome installations and want to explicitly use `chromium-browser` for example. Otherwise the system default Chrome is used.
- 使用 `--driver-path` 显示指定 Chrome 可执行文件位置；若有多个 Chrome 可执行文件存在，使用 `chromium-browser` 时可用此参数指明。否则使用系统默认 Chrome。
- Headless is now the default; omit to stay headless. Use `--headless False` to show browser windows.
- 现在默认无头运行；不加参数即为无头。使用 `--headless False` 显示浏览器窗口。
```bash
python visa_status.py cz --i my_codes.csv --driver-path /path/to/chromedriver --retries 3 --headless
```

Explanation: `--driver-path` lets you point to a specific chromedriver binary when your system driver is incompatible or you want a different Chrome binary. Most users can omit it; omit it and the tool will try `webdriver-manager` (if installed) or system chromedriver.
说明：`--driver-path` 允许指定 chromedriver 可执行文件，用于系统驱动不兼容或需要使用特定 Chrome 时。大多数用户可省略；省略时程序会尝试使用 `webdriver-manager`（如已安装）或系统 chromedriver。

## Commands & parameters (detailed) / 命令与参数（详细）
`generate-codes` — generate a CSV of query codes.
`generate-codes` — 生成查询码 CSV。

- `-o, --out PATH` — output CSV path (default: `query_codes.csv`).
- `-o, --out PATH` — 输出 CSV 路径（默认：`query_codes.csv`）。
- `--start YYYY-MM-DD` — start date for codes generation.
- `--start YYYY-MM-DD` — 生成起始日期（YYYY-MM-DD）。
- `--end YYYY-MM-DD` — end date for codes generation.
- `--end YYYY-MM-DD` — 生成结束日期（YYYY-MM-DD）。
- `--per-day N` — number of codes per day (integer).
- `--per-day N` — 每日生成数量（整数）。
- `--include-weekends` — include weekends when generating.
- `--include-weekends` — 是否包含周末。
- `--exclude-weekdays / --exclude / --排除 / --日期排除 DIGITS` — exclude specific weekdays (1=Mon..7=Sun). Supports formats: `35`, `3 5`, `3,5`. Applied after weekend inclusion logic. / 排除指定星期（1=周一..7=周日），格式支持 `35`、`3 5`、`3,5`，在周末过滤之后应用。
- `--prefix / --前缀 TEXT` — code prefix (default PEKI). / 自定义代码前缀（默认 PEKI）。

`cz` — run the Czech checker (Selenium by default, can switch to Playwright with `--backend playwright`).
`cz` — 运行捷克查询器（默认 Selenium，可通过 `--backend playwright` 使用 Playwright）。
`cz-bu` — experimental Playwright/browser-use short subcommand (same semantics as `cz --backend playwright`).
`cz-bu` — 实验性 Playwright/browser-use 简写子命令（等价于 `cz --backend playwright`）。

- `--i PATH` — input CSV path (default: `query_codes.csv`).
- `--i PATH` — 输入 CSV 路径（默认：`query_codes.csv`）。
- `--driver-path PATH` — explicit chromedriver binary to use (optional).
- `--driver-path PATH` — 指定 chromedriver 可执行文件路径（可选）。
- `--retries N` — per-row retries (default: 3).
- `--retries N` — 每条重试次数（默认：3）。
- `--headless [True|False]` — default True. Pass `--headless False` to show UI.
- `--headless [True|False]` — 默认 True。使用 `--headless False` 显示界面。
- `--backend [selenium|playwright]` (cz only) — choose backend (default selenium). / 仅 cz：选择后端（默认 selenium）。
- `--log-dir PATH` — change log directory (default: `logs`).
- `--log-dir PATH` — 指定日志目录（默认：`logs`）。

## Global options / 全局选项
- `--no-auto-install` — disable automatic dependency installation at startup. When set, the program will not try to pip-install missing packages and will instead fail early with instructions. / `--no-auto-install` — 启动时禁用自动依赖安装。设置后程序不会尝试自动 pip 安装缺失包，而会直接失败并打印相应的操作指引。

Behavior notes:
The checker will skip rows where the status column is non-empty — this enables resume/retry workflows.
若状态列已有值则会跳过该行，从而支持断点续跑与离线重试工作流。

Results are standardized into a small set of normalized statuses (e.g. `Granted`, `Rejected/Closed`, `Proceedings`, `Not Found`, `Unknown`, `Query Failed`).
结果会被标准化为一组状态（例如：`Granted`、`Rejected/Closed`、`Proceedings`、`Not Found`、`Unknown`、`Query Failed`）。

Code generation semantics / 生成语义:
- 默认仅工作日 (Mon-Fri)。`--include-weekends` 加入周六周日。
- 排除列表在最终集合上生效；例如包含周末同时 `--exclude 7` 会移除周日。
- 前缀可通过 `--prefix` 设置；保留大小写；若为空回退为 PEKI。

## Minimal CSV example / 最小 CSV 示例
The tool accepts bilingual headers and expects these columns: date, code, optional status column.
工具接受中英双语标题，期望列为：日期/Date、查询码/Code、可选签证状态/Status。

```csv
日期/Date,查询码/Code,签证状态/Status
2025-06-02,PEKI202506020001,Rejected/Closed / 被拒绝/已关闭
2025-06-02,PEKI202506020002,Not Found / 未找到
2025-06-03,PEKI202506030001,Proceedings / 审理中
2025-06-03,PEKI202506030002,Granted / 已通过
```

## Output / 输出
Each queried row is updated in-place in the CSV and flushed immediately to disk.
每条查询结果会原地写回 CSV 并立即刷新到磁盘。

Failing rows after retries are appended to `logs/fails/YYYY-MM-DD_fails.csv` for offline retry.
重试后仍失败的条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv` 以便离线重试。

## Technical highlights (implementation & algorithms) / 技术亮点（实现与算法）
- CSV-first design: keeps all state in the CSV so the tool can resume and is friendly to auditing.
- CSV 优先设计：所有状态保存在 CSV 中，便于断点续跑与审计。
- Overlay dismissal strategy: targeted selectors for refuse/close buttons are clicked first; if clicks fail the tool dispatches JS MouseEvent clicks and finally hides/removes overlay nodes via JS before attempting form interaction.
- 覆盖层关闭策略：优先点击拒绝/关闭按钮；若点击失败则发送 JS MouseEvent 事件，最后通过 JS 隐藏/移除 DOM 节点后再尝试交互。
- Robust result detection: multi-selector polling, Selenium `.text` read, JS innerText/textContent fallback and a JS page-scan fallback to extract status text when visibility flags are inconsistent.
- 结果检测强化：多选择器轮询、Selenium `.text` 读取、JS innerText/textContent 回退及页面级 JS 扫描以提取状态文本。
- Retries & backoff: configurable retry count, exponential backoff with jitter between attempts to reduce load and spread retries.
- 重试与退避：可配置重试次数，采用带抖动的指数退避以降低对服务的瞬时压力。
- Driver management: prefer an explicit `--driver-path`; otherwise use `webdriver-manager` if installed; includes lightweight driver/session recreation on recoverable errors.
- 驱动管理：优先使用 `--driver-path` 指定驱动，若安装了 `webdriver-manager` 则自动下载；在可恢复的错误时包含轻量级的驱动/会话重建。
- Playwright experimental backend: optional alternative using browser-use + Playwright for potentially faster, lighter sessions (sequential only for now). / Playwright 实验后端：可选的 browser-use + Playwright 方案（当前仅顺序执行）。
- Header matching: case-insensitive and forgiving column matching for `code` and `status` to be tolerant to CSV variants.
- 头匹配：对 `code` 与 `status` 列名使用不区分大小写且宽松的匹配，以兼容不同 CSV 格式。
- Failure diagnostics: only save page HTML snapshots for Unknown/Query Failed rows to avoid noisy debug files; failing rows get per-day failure CSVs.
- 失败诊断：仅为 Unknown/Query Failed 行保存页面 HTML 快照，以减少噪声文件；失败条目按日保存为 CSV。

## Concurrency / 并发 (workers)

- Use `--workers N` to run N parallel workers (default 1). Each worker borrows a browser instance from a driver pool; the module pre-creates up to N ChromeDriver instances. / 使用 `--workers N` 来运行 N 个并行 worker（默认 1）。每个 worker 从驱动池借用一个浏览器实例；模块会预创建最多 N 个 ChromeDriver 实例。

- Immediate flush: completed rows are written back to the CSV immediately to preserve resume semantics; failures are appended to `logs/fails/YYYY-MM-DD_fails.csv`. / 立即刷新：完成的行会立即写回 CSV 以保留断点续跑语义；失败条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv`。

- Ctrl+C behavior: concurrent runs attempt a graceful shutdown on Ctrl+C — pending tasks are cancelled, progress flushed, and browser instances closed. / Ctrl+C 行为：并发运行在 Ctrl+C 时尝试优雅关闭 — 取消挂起任务、刷新进度并关闭浏览器实例。

- Resource guidance: Chrome instances use memory; on low-memory machines limit `--workers`. Start with N around (available_memory_in_MB / 300). Headless (default) reduces UI overhead; if you need to debug, use `--headless False`. / 资源建议：Chrome 实例占用内存；在低内存机器上请限制 `--workers`。可从 N ≈（可用内存(MB) ÷ 300）开始。默认无头可降低开销；调试时使用 `--headless False`。

- When to use alternative designs: if you need stronger isolation or many concurrent sessions, consider a multi-process approach or an external Selenium Grid. / 何时考虑替代设计：如需更强隔离或大量并发会话，请考虑多进程方案或外部 Selenium Grid。

## Reporting / 报告生成（详细分析 Markdown）

运行聚合分析并输出一个详细的 Markdown 报告（包含：总体分布、每日趋势、周/月汇总、周同比变化、工作日分布、积压比 Backlog、SLA 超期、示例与解读）。

- 命令 / Command:
```bash
python visa_status.py report [ -i custom.csv ] [--charts] [-o reports/custom.md]
```
Default input CSV when -i is omitted: `query_codes.csv`.
若未指定 -i/--input，则默认读取 `query_codes.csv`。
- 默认输出目录结构：`reports/<YYYY-MM-DD>/<HH-MM-SS>/summary.md`（精确到秒，多次快照分层隔离；图表 PNG 同目录保存）。顶层按日期分组，避免同日多次覆盖。
- 选项 / Options:
 	- `--charts` 生成 PNG 图（每日成功率 vs 积压、周成功率、状态分布饼图）并在 Markdown 中引用；若缺失 `matplotlib` 且允许自动安装会尝试安装。
 	- `-o` 自定义 Markdown 路径（若提供绝对 / 相对路径将直接写入该位置；否则使用分层目录）。

Markdown 报告章节 / Sections:
1. Overall Distribution / 总体分布：各标准化状态计数与占比（忽略 Not Found）。
2. Daily Trend / 每日趋势：每日通过率、积压(Proceedings)比、累计通过率与累计积压比。
3. Weekly Summary + Δsuccess%：每周成功率及相对上一周的变化百分比。
4. Monthly Summary：月度总览。
5. Weekday Distribution：按星期（0=周一）统计（仅有效行），识别高频受理日。
6. Submission Volume Per Day：每日“有效”提交量（仅统计有结果且非 Not Found 的行；对全日期范围零填充）。
7. Raw Example Per Status：每个状态的原始示例文本。
7.1 SLA Overdue：Proceedings 超过 60 天估算超期统计。
8. Interpretation / 结果解读：辅助判断下签概率与生成查询码策略的提示。

关键指标 / Key Metrics:
- Success rate: Granted / counted （全局忽略 Not Found，无开关）。
- Failures: Rejected/Closed + Query Failed。
- Backlog ratio: Proceedings / (每日有效统计总数)。
- Weekly Δsuccess%: 当前周成功率 - 上一周成功率。
- Processing rate: (Granted + Rejected)/counted。
- Rejection rate: Rejected/Closed / counted。
- SLA Overdue: Proceedings 中超过 60 天仍未出结果的比例与列表。
- ISO Week: 报告标题含当前 UTC ISO 周标签（便于与周汇总对应）。

用途 / Use Cases:
- 判断当前样本期的粗略通过/拒签比例。
- 监控 Backlog（审理中）变化，预估后续结果释放节奏。
- 根据工作日分布优化新查询码的生成（集中在高活跃日）。

语义说明 / Semantics:
- Not Found 行永远不计入任何成功率/拒签率/提交量；无需再添加开关。
- Submission Volume 仅统计“有效行”（非空且非 Not Found），并对日期范围内未出现有效行的日期填 0，便于直观看缺口。
- Effective date range 只覆盖至少存在一条有效行的首尾日期；避免被大量 Not Found 日拉长分析窗口。
- 自动安装 matplotlib：执行 `report --charts` 且缺少 matplotlib 时会尝试安装（如全局未禁用自动安装）。

（旧版本 JSON 摘要已被更全面的 Markdown 报告取代；如仍需 JSON 可复用 `tools/report.py` 内部函数自行调用。）


## Troubleshooting / 故障排查
Ensure Chrome and chromedriver are compatible; if in doubt use `--driver-path` to point to a matching binary.
请确保 Chrome 与 chromedriver 兼容；不确定时请使用 `--driver-path` 指向匹配的可执行文件。

Increase `--retries` for flaky network conditions or re-run only the `logs/fails/YYYY-MM-DD_fails.csv` rows later.
对网络不稳定情况可增加 `--retries`，或对 `logs/fails/YYYY-MM-DD_fails.csv` 中的条目稍后重试。

## Contributing / 贡献指南
Add a country module in `query_modules/` following the module API in `PROJECT_OVERVIEW.md` and open a PR.
在 `query_modules/` 下添加国家模块，遵循 `PROJECT_OVERVIEW.md` 中的模块 API，并提交 PR。

## Links / 相关链接
- Project overview (developer guide): [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- 项目概览（开发者指南）：[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

## License / 许可证
[MIT](LICENSE)

## Contact / 联系
- Issues: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues


