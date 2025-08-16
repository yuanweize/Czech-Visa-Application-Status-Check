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

## Links / 链接
- README (user guide): [README.md](README.md)
- README（用户指南）：[README.md](README.md)

*** End of overview / 概览结束 ***
