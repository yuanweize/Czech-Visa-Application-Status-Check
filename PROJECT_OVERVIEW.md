# Project Overview / 项目概览

Czech Visa Application Status Check is a compact, bilingual (EN / 中文) CLI tool that generates PEKI-style query codes and bulk-checks visa application status on the Czech public IPC portal. It focuses on reliability for long runs, simple extensibility for new country modules, and clear bilingual output for users.

## Goals / 目标

- Provide a small, extendable CLI to generate and query visa application codes from CSV. / 提供可扩展的命令行工具，用于基于 CSV 生成并查询签证申请状态。
- Minimize data loss during long runs by flushing each result to the CSV and using retries/backoff. / 通过逐行写回与重试/退避策略减少长时间运行中的数据丢失。

## Current features / 当前功能

- Code generator: `tools/generate_codes.py` — generates PEKI-style codes and writes CSV. / 查询码生成器，生成 PEKIYYYYMMDDssss 风格的查询码并导出 CSV。
- Czech query module: `query_modules/cz.py` — Selenium-driven automation with overlay dismissal, retries/backoff, and normalized status mapping. / 捷克查询模块，基于 Selenium，包含覆盖层处理、重试/退避与状态标准化。
- CLI dispatcher: `visa_status.py` — subcommands for `generate-codes` and country modules (e.g., `cz`). / 主程序 `visa_status.py`：调度生成器及按国家码调用查询模块（例如 `cz`）。
- CSV-first operation: reads a CSV and writes status inline per row, flushing after each query. / CSV 优先：读取 CSV 并在每条查询后即时写回状态。
- Failure logs: final failures appended to `logs/fails/YYYY-MM-DD_fails.csv` for offline inspection and retry. / 失败记录：最终失败条目追加到 `logs/fails` 以便离线重试。

## Usage (short) / 使用示例

```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-08-15 --per-day 5
python visa_status.py cz --i my_codes.csv
```

## Behavior & reliability / 行为与可靠性

- Retries: configurable per-query retries; permanent failures are marked `Query Failed`. / 重试：支持配置每条重试次数；最终失败标注为 `Query Failed`。
- Incremental save: results are written back to the CSV after each row to avoid losing progress. / 实时保存：每条查询完成后写回 CSV，避免进度丢失。
- Overlay handling: targeted selectors and JS fallbacks are used to close cookies and modals that block interaction. / 覆盖层处理：优先点击拒绝/关闭按钮并使用 JS 回退以避免阻塞表单。

## Extensibility / 可扩展性

- Add new country modules in `query_modules/` named by ISO-2 code (e.g. `cz.py`) and register them in `visa_status.py`. Modules should accept an input code and return a normalized status string. / 在 `query_modules/` 下以国家码命名新模块（例如 `cz.py`），并在 `visa_status.py` 注册；模块应接受输入查询码并返回标准化状态字符串。

## Notes / 注意事项

- Chrome & ChromeDriver: ensure local Chrome and chromedriver are compatible, or supply `--driver-path`. / Chrome 与 ChromeDriver：请确保本机 Chrome 与 chromedriver 匹配，或通过 `--driver-path` 指定驱动路径。
- Bilingual messages: the CLI and logs include both English and Chinese by design. / 中英双语：CLI 与日志默认中英双语输出。

For quick start and examples see `README.md`.
