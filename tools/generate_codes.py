#!/usr/bin/env python3
"""Query code generator / 查询码生成器

规则 (pattern)：<PREFIX>YYYYMMDDssss  示例：PEKI202507290001
 - PREFIX：可配置前缀（默认 PEKI，可使用 --prefix / --前缀 设置）
 - YYYY：年份
 - MMDD：月份+日期（零填充）
 - ssss：4位序列号（0001 开始）

功能 / Features:
1. 支持指定开始/结束日期（默认：开始=2025-06-01，结束=今天）。
2. 默认仅生成工作日（周一~周五）；使用 --include-weekends 可包含周末。
3. 新增: 可排除指定的星期：--exclude-weekdays 35  (1=周一 ... 7=周日；本例排除周三(3)、周五(5))。
   - 也支持别名: --exclude / --排除 / --日期排除  (值可为连续数字, 逗号或空格分隔，如 "3,5" 或 "35" 或 "3 5")。
4. 新增: 可配置前缀：--prefix SHAN  (默认 PEKI)。

示例 / Examples:
  python visa_status.py generate-codes --start 2025-06-01 --end 2025-06-30 --per-day 5
  python visa_status.py generate-codes --start 2025-06-01 --end 2025-06-30 --per-day 5 \
      --exclude-weekdays 35   # 排除周三与周五
  python visa_status.py generate-codes --start 2025-06-01 --end 2025-06-07 --per-day 3 \
      --include-weekends --prefix SHAN --exclude 7
"""

from datetime import date, timedelta, datetime
import csv
from typing import Iterable, Set

def _parse_exclude_spec(spec: str) -> Set[int]:
    """Parse user exclude weekday spec into a set of weekday codes (1=Mon..7=Sun)."""
    result: Set[int] = set()
    if not spec:
        return result
    # allow separators: comma, space; also allow contiguous digits
    cleaned = spec.replace(',', ' ').strip()
    parts: Iterable[str] = cleaned.split()
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) > 1:
        # contiguous digits like '35'
        parts = list(parts[0])
    for p in parts:
        for ch in p:
            if ch.isdigit():
                v = int(ch)
                if 1 <= v <= 7:
                    result.add(v)
    return result


def generate_codes(start_date: date = None,
                   end_date: date = None,
                   per_day: int = 5,
                   include_weekends: bool = False,
                   exclude_weekdays: Set[int] | None = None,
                   prefix: str = 'PEKI'):
    if start_date is None:
        start_date = date(2025, 6, 1)
    if end_date is None:
        end_date = date.today()
    if exclude_weekdays is None:
        exclude_weekdays = set()
    # Normalize prefix: strip spaces; keep user case but commonly upper-case
    prefix = (prefix or 'PEKI').strip() or 'PEKI'
    delta = timedelta(days=1)
    rows = []
    cur = start_date
    while cur <= end_date:
        weekday_python = cur.weekday()          # 0=Mon .. 6=Sun
        weekday_code = weekday_python + 1       # 1=Mon .. 7=Sun (user facing)
        if weekday_code in exclude_weekdays:
            cur += delta
            continue
        allowed = include_weekends or weekday_python < 5  # weekday_python<5 means Mon-Fri
        if allowed:
            mmdd = f"{cur.month:02d}{cur.day:02d}"
            y = f"{cur.year}"
            for seq in range(1, per_day + 1):
                code = f"{prefix}{y}{mmdd}{seq:04d}"
                rows.append((cur.isoformat(), code))
        cur += delta
    return rows

def save_to_csv(rows, out_path="query_codes.csv"):
    with open(out_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["日期/Date", "查询码/Code"])
        for d, code in rows:
            writer.writerow([d, code])

def parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()

def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Generate query codes and save as CSV / 生成查询码并保存为 CSV")
    p.add_argument("-o", "--out", help="output CSV path (default: query_codes.csv) / 输出 CSV 路径（默认: query_codes.csv）", default="query_codes.csv")
    p.add_argument("--start", help="start date YYYY-MM-DD / 起始日期（YYYY-MM-DD）", default=None)
    p.add_argument("--end", help="end date YYYY-MM-DD / 结束日期（YYYY-MM-DD）", default=None)
    p.add_argument("--per-day", type=int, help="items per day (int) / 每日生成条目数（整数）", default=5)
    p.add_argument("--include-weekends", action="store_true", help="include weekends / 是否包含周末")
    p.add_argument("--exclude-weekdays", "--exclude", "--排除", "--日期排除",
                   help="Weekdays to exclude (digits 1=Mon..7=Sun, e.g. 35 or '3 5') / 需要排除的星期 (1=周一..7=周日，如 35 或 '3 5')",
                   default=None)
    p.add_argument("--prefix", "--前缀",
                   help="Code prefix (default: PEKI) / 代码前缀（默认: PEKI）",
                   default="PEKI")
    args = p.parse_args(argv)

    start = parse_date(args.start) if args.start else None
    end = parse_date(args.end) if args.end else None

    exclude_set = _parse_exclude_spec(args.exclude_weekdays)
    rows = generate_codes(start_date=start,
                          end_date=end,
                          per_day=args.per_day,
                          include_weekends=args.include_weekends,
                          exclude_weekdays=exclude_set,
                          prefix=args.prefix)
    save_to_csv(rows, args.out)
    excl_note = f" excluded={sorted(exclude_set) if exclude_set else 'None'}"
    print(f"Generated {len(rows)} query codes, saved to {args.out}{excl_note} / 生成 {len(rows)} 条查询码，已保存到 {args.out}，排除星期={sorted(exclude_set) if exclude_set else '无'}")

if __name__ == "__main__":
    main()
