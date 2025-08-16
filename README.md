

# Czech Visa Application Status Check / 捷克签证状态批量查询

English and 中文 (bilingual) README for GitHub.

简短说明 | Short description
---|---
This project automates bulk generation of visa query codes and bulk checking of Czech visa application status via the public portal. | 本项目用于批量生成签证查询码，并通过捷克内政部的公开查询页面批量查询签证申请状态，输出为 CSV，便于后续处理或归档。

## Quick start / 快速开始

1. Install dependencies / 安装依赖

```bash
python -m pip install -r requirements.txt
```

2. Generate codes (example) / 生成查询码（示例）

```bash
python Visa_Status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-08-15 --per-day 5
```

3. Query statuses (Czech example) / 查询签证状态（捷克示例）

```bash
python Visa_Status.py cz --i my_codes.csv
```

Notes / 说明
- Use `python Visa_Status.py -h` to list available commands and per-command `-h` for details. / 使用 `python Visa_Status.py -h` 查看命令，子命令可用 `-h` 查看详细参数。

## Behavior improvements (retry and incremental save)

- The Czech query module now retries transient failures up to 3 times and returns a standardized status string like `Not Found`, `Proceedings`, `Granted`, `Rejected/Closed`, or `Query Failed` when all retries fail. / 捷克查询模块在遇到网络或渲染问题时会重试（最多3次），并返回标准化状态（Not Found / Proceedings / Granted / Rejected/Closed / Query Failed）。
- Each query result is flushed to the CSV immediately after retrieval to avoid losing work on long runs. / 每条查询完成后立即写回CSV，防止长时间运行中途失败造成数据丢失。

## Files / 目录结构

- `Visa_Status.py` — main CLI dispatcher / 主程序入口
- `tools/generate_codes.py` — code generator / 查询码生成器
- `query_modules/cz.py` — Czech query module (country-code-based) / 捷克查询器
- `requirements.txt` — Python dependencies / 依赖
- `README.md` — this file / 本文档
- `PROJECT_OVERVIEW.md` — project overview / 项目概览

## Command reference / 命令参考

- `generate-codes` — Generate CSV of query codes. Options: `--start`, `--end`, `--per-day`, `--include-weekends`, `-o/--out`. / 生成查询码，支持参数：`--start`、`--end`、`--per-day`、`--include-weekends`、`-o/--out`。
- `cz` — Query Czech visa statuses. Options: `--i` (CSV input). / 查询捷克签证状态，参数：`--i`（CSV路径）。

## Troubleshooting / 故障排查

- If you see `Query Failed` or `查询失败` occasionally, it is likely a transient network/rendering issue. The module retries automatically; rerun the failed entries after some time. / 若偶尔出现 `Query Failed`/`查询失败`，通常为网络或页面渲染问题，模块会自动重试；可在稍后重试失败条目。
- Make sure Chrome/Chromedriver are compatible and installed if running Selenium locally. / 请确保本地 Chrome 与 Chromedriver 版本兼容并可用。

## Tests / 单元测试

Run tests:

```bash
python -m pytest -q test_generate_codes.py
```

## License & Privacy / 授权与隐私

- Do not commit `.env`, credential files, or downloaded pages containing personal data. Add them to `.gitignore`. / 请勿提交包含个人数据的文件到仓库，使用 `.gitignore` 排除它们。

---

For more details see `PROJECT_OVERVIEW.md`.
