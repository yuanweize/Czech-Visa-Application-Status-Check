# Project Overview / 项目概览

Czech Visa Application Status Check is a compact CLI to generate PEKI-style query codes and bulk-check application status on the Czech IPC portal.
Czech Visa Application Status Check 是一个用于生成 PEKI 风格查询码并在捷克 IPC 网站批量查询申请状态的小型命令行工具。

## Design goals / 设计目标
- Reliable long-running batches with per-row flush and retries/backoff.
- 支持长期批量运行，通过逐行写回与重试/退避实现鲁棒性。
- Simple module-based extensibility: add `query_modules/<iso>.py` modules.
- 模块化可扩展：在 `query_modules/<iso>.py` 下添加新的国家模块。

## Core components / 核心组件
- `visa_status.py` — CLI dispatcher and entrypoint.
- `visa_status.py` — CLI 调度器与入口点。
- `tools/generate_codes.py` — code generator that writes CSV.
- `tools/generate_codes.py` — 负责生成查询码并导出 CSV。
- `query_modules/cz.py` — Czech Selenium-based querier with overlay handling and status normalization.
- `query_modules/cz.py` — 基于 Selenium 的捷克查询模块，包含覆盖层处理与状态标准化。

## Operation contract / 输入输出约定
- Input: UTF-8 CSV with date, code, optional status column.
- 输入：UTF-8 编码的 CSV，包含日期、查询码、可选状态列。
- Output: inline-updated CSV (each row flushed) and failure CSVs saved under `logs/fails/`.
- 输出：原 CSV 被原地更新（逐行刷新），失败条目另存于 `logs/fails/`。

## Notes / 说明
- The project uses bilingual prompts in-code; there is no runtime language flag.
- 项目在代码中使用中英双语提示；没有运行时语言切换。
- ChromeDriver may be auto-downloaded via webdriver-manager if available.
- 如果已安装 webdriver-manager，chromedriver 可被自动下载。

For usage examples and parameters, see `README.md`.
有关使用示例与参数说明，请参阅 `README.md`。
