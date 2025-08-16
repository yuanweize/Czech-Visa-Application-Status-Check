

# Czech Visa Application Status Check / 捷克签证状态批量查询

<!-- Badges -->
[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![hits](https://img.shields.io/badge/usage-experimental-orange)](README.md)


Bulk generator and checker for Czech visa application status — generate Czech visa/resident query codes and check statuses on the official IPC portal. 本项目用于批量生成捷克签证/居留查询码并在捷克内政部公开页面批量查询签证申请状态，导出 CSV。


Repository / 仓库: https://github.com/yuanweize/Czech-Visa-Application-Status-Check

## Quick start / 快速开始

1. Install dependencies / 安装依赖

```bash
python -m pip install -r requirements.txt
```

2. Generate query codes / 生成查询码

```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-08-15 --per-day 5
```

3. Query statuses (Czech example) / 查询签证状态（捷克示例）

```bash
python visa_status.py cz --i my_codes.csv
```

Use `python visa_status.py -h` to list available commands. / 使用 `python visa_status.py -h` 查看可用命令。

## Key behaviors / 主要行为

- Retries: Czech module retries transient errors up to 3 times; final failures are labeled `Query Failed`. / 重试：捷克查询模块对瞬时错误重试最多3次，最终失败标记为 `Query Failed`。
- Incremental save: results are flushed to CSV after each query to avoid losing long-run progress. / 实时保存：每条查询后立即写回CSV，避免长时间运行中断造成数据丢失。

## New features / 新增功能说明

- Auto dependency management: on startup the main program checks for critical Python packages (`selenium`, `webdriver-manager`, `openpyxl`). If missing, it will automatically install them unless `--no-auto-install` is provided. Install events and outcomes are logged to `logs/install_YYYY-MM-DD.log`. / 自动依赖管理：主程序启动时会检测关键依赖并在缺失时自动安装（可通过 `--no-auto-install` 禁用）。安装记录写入 `logs/install_YYYY-MM-DD.log`。
- ChromeDriver handling: If `chromedriver` is not in PATH, but `webdriver-manager` is available, the program uses `webdriver-manager` to download the correct driver automatically at runtime (multi-platform). If neither is available the program logs a warning and will attempt to run with any system chromedriver if present. You can override by passing `--driver-path` to point to a chromedriver binary. / ChromeDriver 处理：若 PATH 中未发现 chromedriver，但安装了 `webdriver-manager`，程序将在运行时自动下载匹配的驱动（支持多平台）。也可通过 `--driver-path` 指定本地驱动路径。
- Logging and failures: installation actions are logged under `logs/`. Query failures (final, after retries) are appended to `logs/fails/YYYY-MM-DD_fails.csv` with date, code, status and optional error notes for later inspection and retry. / 日志与失败记录：安装与检测写入 `logs/`，查询在重试后仍失败的项会写入 `logs/fails`，便于离线重试。

## Global options / 全局选项

- `--retries <n>` — default 3. Controls how many times each query is retried (can be overridden per subcommand). / 全局重试次数，默认 3。
- `--no-auto-install` — disable automatic dependency installation at startup. / 禁用启动时的自动依赖安装。
- `--log-dir <dir>` — change the log directory (default: `logs`). / 指定日志目录。
- `--headless` — enable headless mode globally (subcommands can override). / 全局无头模式。

## Internationalization / 国际化支持

- This project uses bilingual prompts and documentation (English + 中文) by design: all commands, help text and user-facing prompts include both English and Chinese versions. There is no runtime language-switch flag; the CLI and logs are presented bilingually and encoded as UTF-8. / 本项目采用中英双语提示和文档：所有命令、帮助与提示均包含中英文说明，无需运行时切换语言，日志与输出均为 UTF-8 编码。

- Note: a small `utils/i18n.py` helper was previously used during development but has been removed per project preference; all prompts and messages are now inlined bilingual strings directly in code. / 注意：开发过程中曾使用小型 `utils/i18n.py` 帮助器，现已移除；所有提示与消息现已直接嵌入代码为中英双语字符串。

## Commands / 命令说明

- `generate-codes` — generate a CSV of query codes. / 生成查询码的CSV。Options / 选项：
	- `-o, --out`  output CSV path (default: query_codes.csv) / 输出CSV路径（默认: query_codes.csv）
	- `--start`    start date (YYYY-MM-DD) / 起始日期（YYYY-MM-DD）
	- `--end`      end date (YYYY-MM-DD) / 结束日期（YYYY-MM-DD）
	- `--per-day`  items per day (int) / 每日期的条目数量（整数）
	- `--include-weekends` include weekends / 是否包含周末

- `cz` — Czech status checker. / 捷克批量查询器。Options / 选项：
	- `--i` CSV input path (default: query_codes.csv) / CSV 输入路径（默认: query_codes.csv）

Example / 示例:

```bash
python visa_status.py generate-codes -o codes.csv --start 2025-07-01 --end 2025-07-10 --per-day 3
python visa_status.py cz --i codes.csv
```

## Troubleshooting / 故障排查

- Occasional `Query Failed` entries usually indicate transient network or page rendering issues; retry later or re-run failed entries. / 若出现 `Query Failed`，通常为瞬时网络或页面渲染问题，可稍后重试失败条目。
- Ensure Chrome and ChromeDriver are available and compatible when running Selenium locally. / 本地运行 Selenium 时请确保 Chrome/ChromeDriver 版本兼容。

## Tests / 测试

Unit tests were previously included but have been removed from this repository. If you need test coverage, tests can be re-added; I can help create focused tests for generation and parsing logic. / 单元测试已从仓库移除。如需我可协助重新加入针对生成与解析逻辑的测试。

## More details / 更多信息

See the project overview for architecture and design notes:

[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)

## Sample CSV / 示例 CSV

- English (top) / 中文（下方）—— this shows the minimal CSV shape the tools expect: date, query code, and an optional status column. / 英文（上）/ 中文（下）—— 下例展示工具期望的最小 CSV 格式：日期、查询码，可选的状态列。

English:

```csv
# Czech Visa Application Status Check / 捷克签证状态批量查询

[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/) [![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A small, bilingual (EN / 中文) CLI tool to generate Czech visa/resident query codes and bulk-check application status on the official IPC portal. Results are written back into the input CSV (per-row flush) and failures are logged for offline retry. 一个小型中英双语命令行工具，用于生成捷克签证/居留查询码并在捷克 IPC 官网批量查询申请状态，查询结果按行写回原 CSV，并对失败项做离线记录。

Repository: https://github.com/yuanweize/Czech-Visa-Application-Status-Check

## Quick start / 快速开始

1. Install dependencies

```bash
python -m pip install -r requirements.txt
```

2. Generate query codes

```bash
python visa_status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-08-15 --per-day 5
```

3. Query statuses (Czech)

```bash
python visa_status.py cz --i my_codes.csv
```

Use `python visa_status.py -h` for command help. / 使用 `python visa_status.py -h` 获取命令帮助。

## Minimal CSV shape / 最小 CSV 格式

The tool expects a CSV with a date, query code and an optional status column. The repository uses UTF-8 and bilingual headers are accepted. 下例展示最小 CSV 结构；仓库使用 UTF-8 编码，接受中英双语列名。

```csv
日期/Date,查询码/Code,签证状态/Status
2025-06-02,PEKI202506020001,Rejected/Closed / 被拒绝/已关闭
2025-06-02,PEKI202506020002,Not Found / 未找到
2025-06-02,PEKI202506020003,Not Found / 未找到
2025-06-03,PEKI202506030001,Proceedings / 审理中
2025-06-03,PEKI202506030002,Granted / 已通过
```

## Commands / 命令

- `generate-codes` — create PEKI-style codes and write a CSV. 选项： `-o/--out` 输出路径，`--start`/`--end` 日期区间，`--per-day` 每日条目数，`--include-weekends` 是否包含周末。
- `cz` — run the Czech IPC checker against an input CSV. 选项：`--i` CSV 输入路径（默认 `query_codes.csv`）。

Examples:

```bash
python visa_status.py generate-codes -o codes.csv --start 2025-07-01 --end 2025-07-10 --per-day 3
python visa_status.py cz --i codes.csv
```

## Behavior highlights / 行为要点

- Incremental save: each row is flushed immediately after query. / 实时保存：逐行刷新。
- Retries & backoff: per-query retry with configurable attempts and jitter; final failures are marked `Query Failed`. / 重试与退避：每条可配置重试与抖动，最终失败标记为 `Query Failed`。
- Overlay handling: targets cookie/modal selectors (e.g. refuse and close buttons) with JS fallbacks to avoid blocking. / 覆盖层处理：优先点击拒绝/关闭按钮并使用 JS 回退以避免阻塞表单。
- Failure logs: failing rows after retries are appended to `logs/fails/YYYY-MM-DD_fails.csv`. / 失败记录：重试后仍失败的条目追加到 `logs/fails`。

## Troubleshooting / 故障排查

- Ensure Chrome and ChromeDriver are installed and compatible with the local Chrome version. / 请确保本机 Chrome 与 ChromeDriver 版本匹配。
- If many `Query Failed` occur, try re-running the failed CSV rows or increase `--retries`. / 若大量 `Query Failed`，建议重试或增加 `--retries`。

## Project notes / 其他说明

- Bilingual in-code prompts: the project presents both English and Chinese messages in logs and CLI output. / 代码中嵌入中英双语提示。
- Driver handling: you can pass `--driver-path` to specify chromedriver, otherwise `webdriver-manager` is used if installed. / 可通过 `--driver-path` 指定 chromedriver，否则如已安装 `webdriver-manager` 则会自动下载匹配驱动。

See `PROJECT_OVERVIEW.md` for architecture details. / 详见 `PROJECT_OVERVIEW.md`。

## License / 许可证

MIT


