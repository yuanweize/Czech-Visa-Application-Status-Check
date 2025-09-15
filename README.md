 # Czech Visa Application Status Check / 捷克签证状态批量查询

A small CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)  
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Tech stack / 技术栈
Python 3.10+。

Playwright (Chromium) for browser automation (headless by default).
使用 Playwright (Chromium) 进行浏览器自动化（默认无头）。

CSV-based I/O using Python's stdlib (`csv`).
使用 Python 标准库的 CSV（`csv`）进行输入输出。

Basic logging to files under `logs/`（失败行归档至 `logs/fails/`）。
基本日志写入 `logs/` 目录（失败行归档在 `logs/fails/`）。

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
- `requirements.txt` — Python dependencies (playwright; optional matplotlib).

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
python visa_status.py gen
```

Advanced examples / 高级用法示例：
1) 从2025年6月1日到2025年6月30日之间，以每天5个查询码的量生成查询码 / Generate 5 per day for June:
```bash
python visa_status.py gen -o my_codes.csv -s 2025-06-01 -e 2025-06-30 -n 5
```
2) 排除周三与周五(3,5) / Exclude Wed & Fri while keeping only weekdays (default already excludes weekends):
```bash
python visa_status.py gen -s 2025-06-01 -e 2025-06-14 -x 35 -o no_wed_fri.csv
```
	可等价使用 `--exclude 3,5` 或 `--排除 35`。
3) 包含周末但排除周日，且使用自定义前缀 SHAN / Include weekends, exclude Sunday, custom prefix:
```bash
python visa_status.py gen -s 2025-06-01 -e 2025-06-07 -w --exclude 7 -p SHAN -o shan_codes.csv
```
4) 使用中文参数别名 / Using Chinese aliases:
```bash
python visa_status.py gen --前缀 ABC --日期排除 24 -s 2025-06-01 -e 2025-06-10
```

3) Query statuses (Czech, Playwright-only) / 查询状态（捷克，Playwright）
Simple example（默认读取 `query_codes.csv`）:
简单示例（默认读取 `query_codes.csv`）:
```bash
python visa_status.py c
```

Show UI (headless off) and 4 workers / 显示界面并开 4 个 worker：
```bash
python visa_status.py c -H False -w 4
```

Notes:
- Requires `playwright` and a Chromium runtime. Install once:
	- pip install playwright
	- python -m playwright install chromium
- 需要安装 `playwright` 与 Chromium 运行时（首次一次性安装）。

<!-- Agent mode and alternative backends have been removed in 2025 refactor to keep the tool minimal and deterministic. -->

Parameters（cz）/ 参数（cz）：
- `-i, --i PATH` — input CSV path (default: `query_codes.csv`). / 输入 CSV（默认 `query_codes.csv`）
- `-H, --headless [True|False]` — default True; pass False to show UI. / 默认 True；传 False 显示界面
- `-w, --workers N` — async workers (pages) sharing one browser. / 并发 worker 数（同一浏览器的多个页面）
- `-r, --retries N` — per-row retries (default 3, global). / 每条重试次数（默认 3，全局）

## Commands & parameters (detailed) / 命令与参数（详细）
`generate-codes` (aliases: `gen`, `gc`) — generate a CSV of query codes.
`generate-codes`（别名：`gen`、`gc`）— 生成查询码 CSV。

- `-o, --out PATH` — output CSV path (default: `query_codes.csv`).
- `-o, --out PATH` — 输出 CSV 路径（默认：`query_codes.csv`）。
- `-s, --start YYYY-MM-DD` — start date for codes generation. / 生成起始日期
- `-e, --end YYYY-MM-DD` — end date for codes generation. / 生成结束日期
- `-n, --per-day N` — number of codes per day (integer). / 每日数量
- `-w, --include-weekends` — include weekends when generating. / 包含周末
- `-x, --exclude-weekdays / --exclude / --排除 / --日期排除 DIGITS` — exclude specific weekdays (1=Mon..7=Sun). / 排除指定星期
- `-p, --prefix / --前缀 TEXT` — code prefix (default PEKI). / 自定义前缀

`cz` (alias: `c`) — run the Czech checker (Playwright-only).
`cz`（别名：`c`）— 运行捷克查询器（仅 Playwright）。

- `-i, --i PATH` — input CSV path (default: `query_codes.csv`). / 输入 CSV
- `-r, --retries N` — per-row retries (default: 3, global). / 每条重试次数（全局）
- `-H, --headless [True|False]` — default True; pass False to show UI. / 无头模式
- `-w, --workers N` — concurrent workers (pages). / 并发 worker 数
- `-l, --log-dir PATH` — change log directory (default: `logs`). / 日志目录

## Global options / 全局选项
 -r/--retries, -l/--log-dir
 全局：-r/--retries，-l/--log-dir

Behavior notes:
- The checker will skip rows whose status is already a non-failed final value; rows with `Query Failed / 查询失败` are treated as pending and will be retried on the next run.
- 若某行状态已是非失败的最终值则跳过；若为 `Query Failed / 查询失败` 则视为未完成，下次运行会重查。

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

Failing rows after retries are appended to `logs/fails/YYYY-MM-DD_fails.csv` with an extra column `连续失败次数/Consecutive_Fail_Count` to accumulate consecutive failures across runs (per day).
重试后仍失败的条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv`，并新增列 `连续失败次数/Consecutive_Fail_Count` 用于跨多次运行（当日）累积连续失败次数。

At the end of each run, a summary is printed, including total processed, success/failed counts, overall success rate, retry-needed count, retry-success count and rate, average attempts, elapsed time, throughput, and phase timings (navigation/fill/read).
每次运行结束会在控制台输出总结：处理总数、成功/失败数、总体成功率、需要重试的数量、重试成功数与成功率、平均尝试次数、运行用时、吞吐量，以及分阶段耗时（导航/填表/读结果）。
  
Performance notes / 性能说明：
- Navigation concurrency is capped (默认 6) to avoid thundering herd during heavy goto events; form filling and result reading proceed concurrently without this cap.
- 导航并发会被限流（默认 6），避免大量 goto 同时触发；表单填写与读取结果不受此限制并可充分并发。
- A light jitter (30–120ms) is applied before filling to desynchronize bursts.
- 在填表前加入轻微抖动（30–120ms），减少瞬时峰值带来的不稳定。
## Technical highlights (implementation) / 技术亮点（实现）
- CSV-first design: keeps all state in the CSV so the tool can resume and is friendly to auditing.
- CSV 优先设计：所有状态保存在 CSV 中，便于断点续跑与审计。
- Overlay dismissal strategy: targeted selectors for refuse/close buttons are clicked first; if clicks fail the tool dispatches JS MouseEvent clicks and finally hides/removes overlay nodes via JS before attempting form interaction.
- 覆盖层关闭策略：优先点击拒绝/关闭按钮；若点击失败则发送 JS MouseEvent 事件，最后通过 JS 隐藏/移除 DOM 节点后再尝试交互。
- Robust result detection: multi-selector polling with Playwright, JS innerText/textContent fallback, and a page-scan when visibility flags are inconsistent.
- 结果检测强化：基于 Playwright 的多选择器轮询、JS innerText/textContent 回退及页面级扫描。
- Retries & backoff: configurable retry count with small backoff between attempts.
- 重试与退避：可配置重试次数，采用带抖动的指数退避以降低对服务的瞬时压力。
- Playwright: single browser, N pages workers; headless by default.
- Playwright：单浏览器、多页面并发；默认无头。
- Header matching: case-insensitive and forgiving column matching for `code` and `status` to be tolerant to CSV variants.
- 头匹配：对 `code` 与 `status` 列名使用不区分大小写且宽松的匹配，以兼容不同 CSV 格式。
  

## Concurrency / 并发 (workers)

- Use `--workers N` to run N parallel workers (default 1). Each worker uses its own page within a single browser instance. / 使用 `--workers N` 运行 N 个并行 worker（默认 1）。每个 worker 在同一浏览器中使用独立页面。

- Immediate flush: completed rows are written back to the CSV immediately to preserve resume semantics; failures are appended to `logs/fails/YYYY-MM-DD_fails.csv`. / 立即刷新：完成的行会立即写回 CSV 以保留断点续跑语义；失败条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv`。

- Ctrl+C behavior: concurrent runs attempt a graceful shutdown on Ctrl+C — pending tasks are cancelled, progress flushed, and browser instances closed. / Ctrl+C 行为：并发运行在 Ctrl+C 时尝试优雅关闭 — 取消挂起任务、刷新进度并关闭浏览器实例。

- Resource guidance: Chrome instances use memory; on low-memory machines limit `--workers`. Start with N around (available_memory_in_MB / 300). Headless (default) reduces UI overhead; if you need to debug, use `--headless False`. / 资源建议：Chrome 实例占用内存；在低内存机器上请限制 `--workers`。可从 N ≈（可用内存(MB) ÷ 300）开始。默认无头可降低开销；调试时使用 `--headless False`。

-- When to use alternative designs: if you need stronger isolation or many concurrent sessions, consider a multi-process model or splitting CSV and running multiple processes. / 何时考虑替代设计：如需更强隔离或大量并发会话，可考虑多进程模型，或将 CSV 拆分并行运行多个进程。

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
Install Playwright and Chromium if you see launch errors:
若启动报错请安装 Playwright 与 Chromium：
1) pip install playwright
2) python -m playwright install chromium

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


