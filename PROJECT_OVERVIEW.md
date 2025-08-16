 # Project Overview / 项目概览

Czech Visa Application Status Check — a bilingual (EN/中文) tool to generate visa query codes and bulk-check application status on the Czech public portal. 本项目用于生成签证查询码并批量查询捷克签证申请状态，输出 CSV，支持扩展其他国家查询模块。

## Goals / 目标

- Provide a small, extendable CLI that can generate query codes and query statuses from a CSV. / 提供可扩展的命令行工具，用于生成查询码并基于CSV批量查询签证状态。
- Ensure robustness for long runs: retries on transient failures, and incremental save to avoid data loss. / 在长时间批量查询中保证鲁棒性：对瞬时失败重试，并即时写回CSV以避免数据丢失。

## Current Features / 当前功能

- Code generator: `tools/generate_codes.py` — generate PEKI-style codes and save to CSV. / 查询码生成器，生成 PEKIYYYYMMDDssss 格式并导出CSV。
- Czech query module: `query_modules/cz.py` — Selenium-based automation with retry and normalized status mapping. / 捷克查询模块，基于 Selenium，带重试和标准化状态映射。
- Main CLI: `Visa_Status.py` — dispatches `generate-codes` and country-code subcommands (e.g., `cz`). / 主程序用于调度生成器和按国家码调用查询模块。
- Tests: `test_generate_codes.py` (pytest). / 单元测试覆盖生成逻辑。

## Usage Examples / 使用示例

Generate codes and query statuses (example):

```bash
python Visa_Status.py generate-codes -o my_codes.csv --start 2025-06-01 --end 2025-08-15 --per-day 5
python Visa_Status.py cz --i my_codes.csv
```

## Behavior and failure handling / 行为与故障处理

- Retries: the Czech module retries up to 3 times on transient errors and returns `Query Failed` for permanent failures. / 重试：捷克模块对瞬时错误重试最多3次，最终失败返回 `Query Failed`。
- Incremental save: each result is flushed after retrieval to minimize data loss on long runs. / 实时保存：每条结果查询后即写回CSV，降低丢失风险。

## Extensibility / 可扩展性

- Add other country modules under `query_modules/` named by ISO-2 code, and register them in `Visa_Status.py`. / 在 `query_modules/` 下以国家码命名新模块并在主程序注册。

## Notes / 注意事项

- Ensure ChromeDriver and Chrome are installed and compatible. / 请确保安装并匹配 Chrome/ChromeDriver。

---

See `README.md` for quick start and commands. / 详见 `README.md`。
