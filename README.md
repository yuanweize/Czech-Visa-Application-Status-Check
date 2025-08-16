# Czech Visa Application Status Check / 捷克签证状态批量查询

A small CLI to generate PEKI-style query codes and bulk-check application status on the Czech IPC portal.
一个用于生成 PEKI 格式查询码并在捷克 IPC 网站批量查询申请状态的小型命令行工具。

Tech stack / 技术栈
- Python 3.8+.
- Python 3.8+
- Selenium for browser automation (Chrome).
- 使用 Selenium 驱动浏览器自动化（Chrome）。
- webdriver-manager (optional) to auto-download chromedriver.
- webdriver-manager（可选）用于自动下载 chromedriver。
- openpyxl (optional) for Excel support.
- openpyxl（可选）用于 Excel 支持。

What it does / 功能简介
- Generate PEKI-style query codes and write them to CSV.
- 生成 PEKI 风格的查询码并写入 CSV。
- Read a CSV of codes, query the IPC status page per-row, and write normalized results back to the CSV.
- 读取包含查询码的 CSV，逐行查询 IPC 状态并将标准化结果写回 CSV。
- Save failing rows to daily failure files in `logs/fails/` for offline retry.
- 将失败条目保存到 `logs/fails/` 的按日文件，以便离线重试。

Quick start / 快速开始
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

3) Query statuses (Czech) / 查询（捷克）
```bash
python visa_status.py cz --i my_codes.csv
```
3）查询状态（捷克）
```bash
python visa_status.py cz --i my_codes.csv
```

Commands & parameters / 命令与参数
- `generate-codes` — create codes and write CSV. Options: `-o/--out`, `--start`, `--end`, `--per-day`, `--include-weekends`.
- `generate-codes` — 生成查询码并写入 CSV。选项：`-o/--out`、`--start`、`--end`、`--per-day`、`--include-weekends`。
- `cz` — Czech checker. Options: `--i` CSV input path, `--driver-path` explicit chromedriver path, `--retries` number of retries, `--headless` run headless.
- `cz` — 捷克查询器。选项：`--i` CSV 输入路径、`--driver-path` 指定 chromedriver 路径、`--retries` 重试次数、`--headless` 无头运行。

Minimal CSV example / 最小 CSV 示例
The tool accepts bilingual headers and expects: date, code, optional status column.
工具接受中英双语标题，最小列为：日期/Date、查询码/Code、可选签证状态/Status。

```csv
日期/Date,查询码/Code,签证状态/Status
2025-06-02,PEKI202506020001,Rejected/Closed / 被拒绝/已关闭
2025-06-02,PEKI202506020002,Not Found / 未找到
2025-06-03,PEKI202506030001,Proceedings / 审理中
2025-06-03,PEKI202506030002,Granted / 已通过
```

Output / 输出
- Each queried row is updated in-place in the CSV and flushed immediately.
- 每条查询结果会原地写回 CSV 并立即刷新。
- Failing rows after retries are appended to `logs/fails/YYYY-MM-DD_fails.csv`.
- 重试后仍失败的条目会追加到 `logs/fails/YYYY-MM-DD_fails.csv`。

Logs & diagnostics / 日志与诊断
- Installation and run logs are written into `logs/`.
- 安装与运行日志写入 `logs/`。
- Overlay / page HTML snapshots are saved only for Unknown/Query Failed rows to reduce noise.
- 仅在返回 Unknown 或 Query Failed 时保存页面快照，以减少噪声文件。

Troubleshooting / 故障排查
- Ensure Chrome & chromedriver versions match; use `--driver-path` if needed.
- 请确保 Chrome 与 chromedriver 版本匹配；必要时使用 `--driver-path` 指定驱动。
- If many `Query Failed` appear, increase `--retries` or retry failing CSV with the `cz` command.
- 若大量出现 `Query Failed`，可增加 `--retries` 或对失败 CSV 重新运行 `cz` 命令重试。

License / 许可证
MIT

Contact / 联系
- Issues: https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues
- 问题反馈：https://github.com/yuanweize/Czech-Visa-Application-Status-Check/issues


