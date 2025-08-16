#!/usr/bin/env python3
"""
生成查询码并保存为 csv 文件。

规则：PEKIYYYYMMDDssss，示例：PEKI202507290001
 - YYYY：年份（默认 2025）
 - MMDD：月份日期（例如 0729）
 - ssss：序列号，4 位，起始 0001

生成范围：从 6 月 1 日 到 8 月 15 日（含），仅包含周一到周五。
每个日期生成序列号 0001 到 0005（共 5 个）。
"""

from datetime import date, timedelta, datetime
import csv

def generate_codes(start_date: date = None, end_date: date = None, per_day: int = 5, include_weekends: bool = False):
    if start_date is None:
        start_date = date(2025, 6, 1)
    if end_date is None:
        end_date = date.today()
    delta = timedelta(days=1)
    rows = []
    cur = start_date
    while cur <= end_date:
        if include_weekends or cur.weekday() < 5:
            mmdd = f"{cur.month:02d}{cur.day:02d}"
            y = f"{cur.year}"
            for seq in range(1, per_day + 1):
                code = f"PEKI{y}{mmdd}{seq:04d}"
                rows.append((cur.isoformat(), code))
        cur = cur + delta
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
    args = p.parse_args(argv)

    start = parse_date(args.start) if args.start else None
    end = parse_date(args.end) if args.end else None

    rows = generate_codes(start_date=start, end_date=end, per_day=args.per_day, include_weekends=args.include_weekends)
    save_to_csv(rows, args.out)
    print(f"Generated {len(rows)} query codes, saved to {args.out} / 生成 {len(rows)} 条查询码，已保存到 {args.out}")

if __name__ == "__main__":
    main()
