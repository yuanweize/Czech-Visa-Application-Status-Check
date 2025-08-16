# Czech Visa Application Status Check / 捷克签证状态批量查询

A small CLI to generate visa application query codes and bulk-check application status on the Czech Immigration Office website.
一个用于生成签证申请查询码并在捷克移民局网站批量查询申请状态的小型命令行工具。

[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)  
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## Tech stack / 技术栈
- Python 3.8+.
- Python 3.8+。
- Selenium WebDriver (Chrome) for browser automation.
- 使用 Selenium WebDriver（Chrome）进行浏览器自动化。
- webdriver-manager (optional) to auto-download chromedriver when available.
- webdriver-manager（可选）在可用时用于自动下载 chromedriver。
- CSV-based I/O using Python's stdlib (csv) — no Excel / openpyxl dependency.
- 使用 Python 标准库的 CSV（csv）进行输入输出 — 无 Excel / openpyxl 依赖。
- Basic logging to file under `logs/`.
- 基本日志写入 `logs/` 目录。

## What it does / 功能简介
- Generate visa application query codes and write them to a CSV for later querying.
- 生成签证申请查询码并写入 CSV 以供后续查询。
- Read a CSV of codes and query the Czech Immigration Office website per-row, then write normalized results back to the CSV immediately.
- 读取包含查询码的 CSV，逐行查询捷克移民局网站，并将标准化结果立即写回 CSV。
- Save failing rows after retries to daily failure files in `logs/fails/` for offline retry.
- 在重试后仍失败的条目保存到 `logs/fails/` 的按日文件，便于离线重试。

## Project structure (for contributors) / 项目结构（面向贡献者）
- `visa_status.py` — CLI entrypoint and dispatcher that registers country modules and exposes commands.
- `visa_status.py` — CLI 入口与调度器，负责注册国家模块并暴露命令。
- `query_modules/` — directory containing one module per country (e.g. `cz.py`). Each module implements a simple querying interface.
- `query_modules/` — 存放每个国家模块的目录（例如 `cz.py`），每个模块实现统一的查询接口。
- `tools/generate_codes.py` — code generator utility.
- `tools/generate_codes.py` — 查询码生成工具。
- `logs/` — run and fail logs; failing rows are appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- `logs/` — 运行与失败日志；失败条目追加到 `logs/fails/YYYY-MM-DD_fails.csv`。
- `requirements.txt` — Python dependencies (selenium, webdriver-manager, etc.).
- `requirements.txt` — Python 依赖列表（例如 selenium、webdriver-manager 等）。

Design note: the checker is modular — to add support for another country, add a file `query_modules/<iso>.py` implementing the module API described in `PROJECT_OVERVIEW.md` and register it in `visa_status.py`.
设计说明：查询器为模块化设计——要添加新的国家支持，请在 `query_modules/<iso>.py` 下添加文件，按照 `PROJECT_OVERVIEW.md` 中描述的模块 API 实现并在 `visa_status.py` 中注册。

## Quick start / 快速开始
1) Install dependencies / 安装依赖
```bash
python -m pip install -r requirements.txt
```
1）安装依赖
```bash
python -m pip install -r requirements.txt
```

2) Generate codes / 生成查询码
```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-06-30 --per-day 5
```
2）生成查询码
```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-06-30 --per-day 5
```

3) Query statuses (Czech) / 查询状态（捷克）
```bash
python visa_status.py cz --i my_codes.csv --driver-path /path/to/chromedriver --retries 3 --headless
```
3）查询状态（捷克）
```bash
python visa_status.py cz --i my_codes.csv --driver-path /path/to/chromedriver --retries 3 --headless
```

## Commands & parameters (detailed) / 命令与参数（详细）
- `generate-codes` — generate a CSV of query codes.
- `generate-codes` — 生成查询码 CSV。
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

- `cz` — run the Czech checker (example module).
- `cz` — 运行捷克查询器（示例模块）。
  - `--i PATH` — input CSV path (default: `query_codes.csv`).
  - `--i PATH` — 输入 CSV 路径（默认：`query_codes.csv`）。
  - `--driver-path PATH` — explicit chromedriver binary to use (optional).
  - `--driver-path PATH` — 指定 chromedriver 可执行文件路径（可选）。
  - `--retries N` — per-row retries (default: 3).
  - `--retries N` — 每条重试次数（默认：3）。
  - `--headless` — run browser in headless mode (optional).
  - `--headless` — 以无头模式运行浏览器（可选）。
  - `--log-dir PATH` — change log directory (default: `logs`).
  - `--log-dir PATH` — 指定日志目录（默认：`logs`）。

Behavior notes:
- The checker will skip rows where the status column is non-empty — this enables resume/retry workflows.
- 若状态列已有值则会跳过该行，从而支持断点续跑与离线重试工作流。
- Results are standardized into a small set of normalized statuses (e.g. `Granted`, `Rejected/Closed`, `Proceedings`, `Not Found`, `Unknown`, `Query Failed`).
- 结果会被标准化为一组状态（例如：`Granted`、`Rejected/Closed`、`Proceedings`、`Not Found`、`Unknown`、`Query Failed`）。

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
- Each queried row is updated in-place in the CSV and flushed immediately to disk.
- 每条查询结果会原地写回 CSV 并立即刷新到磁盘。
- Failing rows after retries are appended to `logs/fails/YYYY-MM-DD_fails.csv` for offline retry.
- 重试后仍失败的条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv` 以便离线重试。

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
- Header matching: case-insensitive and forgiving column matching for `code` and `status` to be tolerant to CSV variants.
- 头匹配：对 `code` 与 `status` 列名使用不区分大小写且宽松的匹配，以兼容不同 CSV 格式。
- Failure diagnostics: only save page HTML snapshots for Unknown/Query Failed rows to avoid noisy debug files; failing rows get per-day failure CSVs.
- 失败诊断：仅为 Unknown/Query Failed 行保存页面 HTML 快照，以减少噪声文件；失败条目按日保存为 CSV。

## Troubleshooting / 故障排查
- Ensure Chrome and chromedriver are compatible; if in doubt use `--driver-path` to point to a matching binary.
- 请确保 Chrome 与 chromedriver 兼容；不确定时请使用 `--driver-path` 指向匹配的可执行文件。
- Increase `--retries` for flaky network conditions or re-run only the `logs/fails/YYYY-MM-DD_fails.csv` rows later.
- 对网络不稳定情况可增加 `--retries`，或对 `logs/fails/YYYY-MM-DD_fails.csv` 中的条目稍后重试。

## Contributing / 贡献指南
- Add a country module in `query_modules/` following the module API in `PROJECT_OVERVIEW.md` and open a PR.
- 在 `query_modules/` 下添加国家模块，遵循 `PROJECT_OVERVIEW.md` 中的模块 API，并提交 PR。

## Links / 相关链接
- Project overview (developer guide): [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- 项目概览（开发者指南）：[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

## License / 许可证
MIT

## Contact / 联系
- Issues: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues
- 问题反馈：https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues


