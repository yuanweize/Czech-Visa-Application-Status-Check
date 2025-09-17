# Czech Visa Application Status Check / 捷克签证状态批量查询

A small CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)  
[![license](https:/**User Code Management / 用户代码管理**
The system now includes a user-friendly interface for public users to add and manage their visa codes with email verification:

系统现在包含用户友好的界面，允许公众用户通过邮箱验证来添加和管理他们的签证代码：

**Features / 功能:**
- **Email Verification**: Secure 10-minute verification links for code additions / 邮件验证：代码添加的10分钟安全验证链接
- **Simple Captcha**: Basic math questions to prevent automated abuse / 简单验证码：基础数学题防止自动化滥用
- **Code Management**: Users can view and delete their own codes / 代码管理：用户可查看和删除自己的代码
- **No Quantity Limits**: Users can add as many codes as needed / 无数量限制：用户可根据需要添加任意数量代码
- **6-Digit Verification**: Time-limited verification codes for secure management / 6位验证码：用于安全管理的限时验证码
- **Duplicate Protection**: Comprehensive duplicate detection system prevents monitoring conflicts / 重复保护：全面的重复检测系统防止监控冲突

**Duplicate Detection System / 重复检测系统:**
- **Startup Protection**: Automatically rejects startup when duplicate codes are found in configuration / 启动保护：配置中发现重复代码时自动拒绝启动
- **Web Interface Protection**: Dual-layer detection checks both configuration files and runtime data / Web界面保护：双层检测检查配置文件和运行时数据
- **Privacy-Preserving**: Masks email addresses when showing conflicts (e.g., `use***@example.com`) / 隐私保护：显示冲突时掩码邮箱地址
- **Clear Error Messages**: Provides specific error details for easy troubleshooting / 清晰错误信息：提供具体错误详情便于故障排查s.io/badge/license-MIT-green)](LICENSE)

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
- `monitor/` — monitoring and user management modules (modular architecture):
  - `core/` — core monitoring functionality:
    - `scheduler.py` — priority-based monitoring scheduler with differential updates
    - `config.py` — environment configuration management with hot reload support
  - `server/` — HTTP server and API handling:
    - `http_server.py` — static file server and API integration
    - `api_handler.py` — user management API endpoints with email verification
  - `notification/` — email notification system:
    - `smtp_client.py` — SMTP client with connection pooling and hot reload
    - `user_management.py` — user verification and management emails
  - `utils/` — utility modules:
    - `env_watcher.py` — .env file monitoring and hot reload with watchdog
    - `logger.py` — rotating logger with automatic 2MB rotation and line preservation
    - `signal_handler.py` — graceful shutdown handling for SIGINT/SIGTERM signals
    - `service_manager.py` — systemd service management for Linux deployment
- `query_modules/` — directory containing one module per country (e.g. `cz.py`). Each module implements a simple querying interface.
- `site/` — static website files (HTML, CSS, JS) for user interface
- `tools/generate_codes.py` — code generator utility.
- `logs/` — run and fail logs; failing rows are appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- `requirements.txt` — Python dependencies (playwright; optional matplotlib; watchdog for .env hot reloading).

设计说明：查询器为模块化设计——要添加新的国家支持，请在 `query_modules/<iso>.py` 下添加文件，按照 `PROJECT_OVERVIEW.md` 中描述的模块 API 实现并在 `visa_status.py` 中注册。用户管理功能通过新的模块化架构实现：`monitor/server/api_handler.py` 处理用户API，`monitor/notification/` 处理邮件通知，`monitor/core/scheduler.py` 提供优先级调度，`monitor/utils/env_watcher.py` 提供 .env 热更新支持。

## Quick start (uv) / 快速开始（推荐使用 uv）

uv is a fast Python package and environment manager. You don’t need a global Python after installing uv.
uv 是一个高性能的 Python 包与环境管理器。安装 uv 后无需全局 Python 亦可使用。

1) Install uv / 安装 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Follow the printed instructions to add uv to PATH for the current shell
```

2) Create a virtual environment in this project / 在项目目录创建虚拟环境

```bash
uv venv
```

3) Activate the environment / 激活虚拟环境

- macOS/Linux (bash/zsh):

```bash
source .venv/bin/activate
```

- Windows (Git Bash):

```bash
source .venv/Scripts/activate
```

4) Install dependencies from requirements.txt / 安装依赖

```bash
uv pip install -r requirements.txt
```

5) Install Playwright browsers / 安装 Playwright 浏览器内核

```bash
playwright install
```

6) Run the script / 运行脚本

```bash
python visa_status.py cz
```

—

## Quick start (pip alternative) / 快速开始（pip 方案）
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

<!-- Legacy agent/backends removed in 2025 refactor to keep the tool minimal and deterministic. -->

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

## Monitor & User Management / 监控与用户管理
- Sequential queries; during each cycle a Chromium browser/context/page is created and closed after the cycle to keep idle CPU usage low. 更稳定；每一轮查询才启动 Chromium，完成后立即关闭，空闲时几乎不占用 CPU。
- Email-only notifications. 首次记录或状态变化才通知（主题形如 `[状态] 查询码 - CZ Visa Status`，HTML 包含旧→新变更）。
- Writes `SITE_DIR/status.json` (string-only statuses) and can serve a static site rooted at `SITE_DIR` when `SERVE=true` on `SITE_PORT`.

### User Code Management / 用户代码管理
The system now includes a user-friendly interface for public users to add and manage their visa codes with email verification:

系统现在包含用户友好的界面，允许公众用户通过邮箱验证来添加和管理他们的签证代码：

**Features / 功能:**
- **Email Verification**: Secure 10-minute verification links for code additions / 邮件验证：代码添加的10分钟安全验证链接
- **Simple Captcha**: Basic math questions to prevent automated abuse / 简单验证码：基础数学题防止自动化滥用
- **Code Management**: Users can view and delete their own codes / 代码管理：用户可查看和删除自己的代码
- **No Quantity Limits**: Users can add as many codes as needed / 无数量限制：用户可根据需要添加任意数量代码
- **6-Digit Verification**: Time-limited verification codes for secure management / 6位验证码：用于安全管理的限时验证码

**Architecture / 架构:**
- **Modular Design**: API functionality is organized in `monitor/server/api_handler.py` module with HTTP server in `monitor/server/http_server.py` / 模块化设计：API功能组织在`monitor/server/api_handler.py`模块中，HTTP服务器在`monitor/server/http_server.py`中
- **Priority Scheduler**: Enhanced scheduler with differential code processing in `monitor/core/scheduler.py` / 优先级调度器：在`monitor/core/scheduler.py`中增强的调度器，支持差异化代码处理
- **Email System**: Comprehensive notification system in `monitor/notification/` with SMTP pooling / 邮件系统：位于`monitor/notification/`的全面通知系统，支持SMTP连接池
- **Hot Reload Engine**: Real-time configuration monitoring in `monitor/utils/env_watcher.py` / 热更新引擎：位于`monitor/utils/env_watcher.py`的实时配置监控
- **Configuration Control**: Use `SERVE=true/false` to enable/disable web interface / 配置控制：使用`SERVE=true/false`启用/禁用Web界面
- **Clean Structure**: All monitoring-related modules are contained in `monitor/` folder with organized submodules / 清晰结构：所有监控相关模块都包含在`monitor/`文件夹中，具有组织化的子模块
- **Simplified Duplicate Handling**: Direct startup rejection approach replaces complex merging strategies for reliability / 简化重复处理：直接启动拒绝方式替代复杂合并策略以提高可靠性

**Quick Start / 快速开始:**
```bash
# For web interface with user management (SERVE=true)
# 启用Web界面和用户管理（SERVE=true）
python visa_status.py monitor

# For pure monitoring without web interface (SERVE=false)  
# 纯监控模式，无Web界面（SERVE=false）
python visa_status.py monitor

# Configure in .env file:
# 在.env文件中配置：
SERVE=true   # Enable web interface / 启用Web界面
SERVE=false  # Disable web interface / 禁用Web界面
```

**Access Points / 访问点:**
- Main Website: http://localhost:8000 (when SERVE=true) / 主网站：http://localhost:8000（当SERVE=true时）
- User Management: Built into main website toolbar / 用户管理：集成在主网站工具栏中
- Pure Monitoring: No web interface (when SERVE=false) / 纯监控：无Web界面（当SERVE=false时）
**Hot reloading / .env 热更新**

The monitor supports comprehensive automatic hot reloading of the `.env` configuration file through an advanced file watching system. When enabled, any changes to `.env` are detected in real-time and the configuration is reloaded without restarting the service.

监控器通过高级文件监控系统支持 `.env` 配置文件的全面自动热更新。启用后，对 `.env` 的任何更改都会被实时检测，并在不重启服务的情况下重新加载配置。

**Enhanced Features / 增强功能:**
- **Real-time File Monitoring**: Uses `watchdog` library for instant .env file change detection / 实时文件监控：使用 `watchdog` 库即时检测 .env 文件变化
- **Differential Updates**: Only processes changed codes (added/removed/modified) for maximum efficiency / 差异化更新：仅处理变更的代码（新增/删除/修改），实现最高效率
- **SMTP Connection Pooling**: Reuses connections with intelligent rate limiting to prevent server bans / SMTP连接池：智能复用连接并限制频率，防止服务器封禁
- **Race Condition Protection**: Advanced retry mechanism handles temporary file states during editing / 防竞态条件：高级重试机制处理编辑期间的临时文件状态
- **Automatic Status Updates**: Real-time updates to status.json when notification channels change / 自动状态更新：通知渠道变更时实时更新 status.json
- **Empty Channel Support**: Set `CHANNEL_X=` (empty) to disable notifications for specific codes / 空通道支持：设置 `CHANNEL_X=`（空）来禁用特定代码的通知
- **Thread Safety**: Configuration reload with lock mechanism ensures data consistency / 线程安全：配置重载使用锁机制确保数据一致性
- **Comprehensive Coverage**: Supports all environment variables including base config, SMTP, and query codes / 全面覆盖：支持所有环境变量，包括基础配置、SMTP和查询码

**Supported Configuration Types / 支持的配置类型:**
- **Base Configuration**: `HEADLESS`, `SITE_DIR`, `LOG_DIR`, `SERVE`, `SITE_PORT`, `DEFAULT_FREQ_MINUTES`
- **SMTP Configuration**: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`
- **Query Codes**: Both `CODES_JSON` (JSON format) and `CODE_x`, `CHANNEL_x`, `TARGET_x`, `FREQ_MINUTES_x`, `NOTE_x` (numbered format)

**Technical Architecture / 技术架构:**
- **File Watcher**: `monitor/utils/env_watcher.py` with 0.5s debounce delay / 文件监控器：带0.5秒防抖延迟
- **Configuration Loader**: Enhanced `load_env_config()` with environment variable precedence / 配置加载器：增强的 `load_env_config()` 支持环境变量优先级
- **Scheduler Integration**: Priority-based scheduler with automatic new code detection / 调度器集成：基于优先级的调度器，自动检测新代码

**Activation / 启用:**
- **Enabled automatically in daemon mode** (not `--once`) **when the `watchdog` package is installed**
- **在守护进程模式下自动启用**（非 `--once`）**当安装了 `watchdog` 包时**

If you see `Warning: watchdog not available, .env hot reloading disabled`, install watchdog:
如出现 `Warning: watchdog not available, .env hot reloading disabled`，请安装 watchdog：
```bash
python -m pip install watchdog
# or
uv pip install watchdog
```

- Hot reloading works for both CLI and systemd service modes.
- Configuration changes take effect in the next monitoring cycle.
- 热更新适用于 CLI 和 systemd 服务模式
- 配置更改会在下一个监控周期生效

---Env / 环境变量:
- SITE_DIR: output folder for status.json and static page
- SERVE: true/false, when true start an HTTP server at SITE_PORT rooted at SITE_DIR
- SITE_PORT: default 8000
- MONITOR_LOG_DIR: default logs/monitor
- SMTP_*: email settings; codes via CODES_JSON or numbered CODE_1...

Run / 运行:
- Once / 单次: `python visa_status.py monitor --once -e .env`
- Daemon / 常驻: `python visa_status.py monitor -e .env`

**Hot Reloading / 热更新功能:**
- **Comprehensive File Monitoring**: Advanced `.env` file watching with `watchdog` library and 0.5s debounce
- **Priority-based Processing**: Enhanced scheduler with differential updates for maximum efficiency
- **SMTP Connection Pooling**: Intelligent connection reuse to prevent 450 "too many AUTH" errors
- **Race Condition Protection**: Robust retry mechanism with delays handles file editing states
- **Automatic Log Rotation**: Keeps monitor logs under 2MB with detailed cycle information
- **Empty Channel Support**: Set channel to empty string to disable notifications
- **Real-time Status Updates**: Automatically updates status.json when configurations change
- **Thread-safe Configuration**: Atomic configuration updates with locking mechanism
- Enabled automatically in daemon mode (not `--once`) when `watchdog` package is installed
- Monitors `.env` file for changes and reloads configuration seamlessly
- Configuration changes take effect in the next monitoring cycle
- Supports adding/removing codes, changing frequencies, SMTP settings, etc.
- 在守护进程模式下自动启用（非 `--once`），需要安装 `watchdog` 包
- **全面文件监控**：高级 `.env` 文件监控，使用 `watchdog` 库和0.5秒防抖
- **基于优先级的处理**：增强的调度器，支持差异化更新以实现最高效率
- **SMTP 连接池**：智能连接复用防止 450 "AUTH 过多" 错误
- **防竞态条件**：强大的重试机制处理文件编辑状态
- **自动日志轮换**：保持监控日志在 2MB 以下并包含详细周期信息
- **线程安全配置**：使用锁机制进行原子配置更新
- 监控 `.env` 文件变化并无缝重新加载配置
- 配置更改在下一个监控周期生效
- 支持添加/删除查询码、更改频率、SMTP设置等

Service on Debian (systemd):
- Install: `sudo python visa_status.py monitor --install -e /path/to/.env`
- Start/Status: `sudo python visa_status.py monitor --start` / `python visa_status.py monitor --status`
- Stop/Reload/Uninstall:
  - `sudo python visa_status.py monitor --stop`
  - `sudo python visa_status.py monitor --reload`
  - `sudo python visa_status.py monitor --uninstall`
 - Restart: `sudo python visa_status.py monitor --restart`
 - Notes:
	 - The service prefers using the uv-created virtualenv Python (`.venv/bin/python` on Linux) when available. You can override with `--python-exe /full/path/to/python` during `--install`.
	 - `--status` uses `systemctl --no-pager` to avoid blocking output.
	 - Hot reloading works with systemd services - edit `.env` file and changes will be applied automatically

## Enhanced Logging / 增强日志功能

The monitor includes comprehensive logging with automatic rotation to help with debugging and monitoring.

监控器包含带自动轮换的全面日志记录，有助于调试和监控。

**Features / 功能:**
- **Automatic Log Rotation**: Keeps log files under 2MB, preserves last 1000 lines when rotating / 自动日志轮换：保持日志文件在2MB以下，轮换时保留最后1000行
- **Detailed Cycle Logging**: Logs every monitoring cycle, code processing, and sleep periods / 详细周期日志：记录每个监控周期、代码处理和休眠期间
- **Email Notification Tracking**: Detailed logs of when and why notifications are sent/skipped / 邮件通知跟踪：详细记录通知发送/跳过的时间和原因
- **Error Recovery Logging**: Browser context recreation, retry attempts, configuration reload details / 错误恢复日志：浏览器上下文重建、重试尝试、配置重载详情
- **Performance Monitoring**: Cycle timing, processing counts, and throughput information / 性能监控：周期时间、处理计数和吞吐量信息
- **Hot Reload Tracking**: Detailed logging of .env changes and differential updates / 热更新跟踪：.env变更和差异化更新的详细日志

**Log Location / 日志位置:**
- Default: `logs/monitor/monitor_YYYY-MM-DD.log`
- Configurable via `MONITOR_LOG_DIR` environment variable
- 默认：`logs/monitor/monitor_YYYY-MM-DD.log`
- 可通过 `MONITOR_LOG_DIR` 环境变量配置

**Sample Log Output / 日志示例:**
```
[2025-09-17T10:30:00] Starting monitoring cycle
[2025-09-17T10:30:00] Processing 34 codes (3 added, 1 removed, 2 modified)
[2025-09-17T10:30:01] Processing code=PEKI202508140001 (channel=email, target=user@example.com)
[2025-09-17T10:30:01] code=PEKI202508140001 attempt=1/3 starting query
[2025-09-17T10:30:03] code=PEKI202508140001 attempt=1/3 success: Granted/已通过
[2025-09-17T10:30:03] code=PEKI202508140001 triggering notification (first_time=false, changed=true)
[2025-09-17T10:30:03] notify Email code=PEKI202508140001 to=user@example.com ok=True
[2025-09-17T10:30:45] Cycle summary: processed 34 codes, updating status.json
[2025-09-17T10:30:45] .env file changed detected, reloading configuration
[2025-09-17T10:30:45] Configuration reload: 2 codes added, 1 code removed
[2025-09-17T10:30:45] Sleeping for 60 minutes until next cycle
```

自动日志轮换保持日志文件在 2MB 以下，包含详细的周期信息、代码处理、邮件通知跟踪和热更新日志。

## License / 许可证
[MIT](LICENSE)

## Contact / 联系
- Issues: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues


