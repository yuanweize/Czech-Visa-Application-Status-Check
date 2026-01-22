#!/usr/bin/env python3
"""Report generator / 报告生成器 (Markdown analytics)

Current design (2025): this module focuses on producing a comprehensive Markdown analytics report.
Legacy JSON + simple markdown helpers remain (`generate_summary`, `write_json`, `write_markdown`) but
the CLI path (`python visa_status.py report`) now invokes `generate_detailed_summary` + `write_detailed_markdown`.

Key behavioral rules / 行为规则:
- Empty status cells or statuses normalized to 'Not Found' are excluded from *all* effective statistics (no flag to include).
- Normalization trims bilingual suffix after ' / ' and maps variants to a canonical status set.
- Submission volume per day counts only effective (non-empty & non Not Found) rows and zero-fills the full calendar span.
- Effective date range excludes days containing only Not Found or empty statuses.
- SLA overdue heuristic: Proceedings older than 60 days vs current Proceedings.

Optional charts / 可选图表: enabled with `--charts` (matplotlib required / 需要 matplotlib)。

"""
from __future__ import annotations
import csv, json, argparse, os, datetime, math, re
from collections import Counter, OrderedDict, defaultdict

NORMALIZE_MAP = {
    'granted': 'Granted',
    'approved': 'Granted',
    'rejected/closed': 'Rejected/Closed',
    'rejected': 'Rejected/Closed',
    'closed': 'Rejected/Closed',
    'proceedings': 'Proceedings',
    'in proceedings': 'Proceedings',
    'unknown': 'Unknown',
    'query failed': 'Query Failed',
    'not found': 'Not Found',
}

STATUS_ORDER = [
    'Granted', 'Rejected/Closed', 'Proceedings', 'Not Found', 'Unknown', 'Query Failed'
]

NOT_FOUND_PAT = re.compile(r'^\s*not\s*found', re.IGNORECASE)


def normalize_status(raw: str) -> str:
    if not raw:
        return ''
    # strip bilingual suffix like ' / 已通过'
    primary = raw.split('/') [0].strip()
    low = primary.lower()
    for k, v in NORMALIZE_MAP.items():
        if k in low:
            return v
    return primary or raw.strip()


def load_csv(path: str):
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError('Empty CSV / 空CSV')
    header = rows[0]
    return header, rows[1:]


def find_status_col(header):
    candidates = ['签证状态/Status', '状态', 'status', '签证状态']
    lower_map = {h.lower(): i for i, h in enumerate(header)}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    # fallback: find column containing 'status'
    for i, h in enumerate(header):
        if h and 'status' in h.lower():
            return i
    return None


def generate_summary(header, data_rows):
    status_idx = find_status_col(header)
    total_rows = len(data_rows)
    counted_rows = 0
    counter = Counter()
    raw_examples = {}
    for r in data_rows:
        if status_idx is None or status_idx >= len(r):
            continue
        raw = (r[status_idx] or '').strip()
        if not raw:
            continue
        if NOT_FOUND_PAT.match(raw):
            continue
        norm = normalize_status(raw)
        if not norm:
            continue
        counter[norm] += 1
        counted_rows += 1
        raw_examples.setdefault(norm, raw)

    # order results
    ordered = OrderedDict()
    for s in STATUS_ORDER:
        if counter.get(s):
            ordered[s] = counter[s]
    # include any other statuses
    for s, v in counter.items():
        if s not in ordered:
            ordered[s] = v

    success = counter.get('Granted', 0)
    failures = counter.get('Rejected/Closed', 0) + counter.get('Query Failed', 0)
    success_rate = (success / counted_rows) if counted_rows else 0.0

    summary = {
        'generated_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'total_rows_scanned': total_rows,
        'rows_counted': counted_rows,
        'distribution': ordered,
        'success': success,
        'failures': failures,
        'success_rate': round(success_rate, 4),
        'raw_example_per_status': raw_examples,
    }
    return summary

# 新的详细分析生成器 / Detailed analytics generator
def generate_detailed_summary(header, data_rows, charts=False, out_markdown_path=None):
    date_idx = None
    # 尝试定位日期列
    for i, h in enumerate(header):
        if h and ('日期' in h or 'date' in h.lower()):
            date_idx = i
            break
    status_idx = find_status_col(header)
    total_rows = len(data_rows)
    norm_counter = Counter()
    raw_examples = {}
    daily = defaultdict(Counter)        # date -> status -> count
    weekly = defaultdict(Counter)       # ISO year-week -> status -> count
    monthly = defaultdict(Counter)      # YYYY-MM -> status -> count
    weekday = Counter()                 # weekday index 0=Mon
    submission_volume_daily = Counter() # counted rows per day (已计入统计的有效行: 有状态且非 Not Found)
    first_date = None
    last_date = None

    def parse_date(s: str):
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.datetime.strptime(s.strip(), fmt).date()
            except Exception:
                pass
        return None

    effective_dates = set()
    for row in data_rows:
        # date parsing
        d_obj = None
        if date_idx is not None and date_idx < len(row):
            d_raw = row[date_idx].strip()
            if d_raw:
                d_obj = parse_date(d_raw)
                if d_obj:
                    if first_date is None or d_obj < first_date:
                        first_date = d_obj
                    if last_date is None or d_obj > last_date:
                        last_date = d_obj
        if status_idx is None or status_idx >= len(row):
            continue
        raw = (row[status_idx] or '').strip()
        if not raw:
            continue
        if NOT_FOUND_PAT.match(raw):
            continue
        norm = normalize_status(raw)
        if not norm:
            continue
        norm_counter[norm] += 1
        raw_examples.setdefault(norm, raw)
        if d_obj:
            daily[d_obj][norm] += 1
            iso_year, iso_week, _ = d_obj.isocalendar()
            weekly[f"{iso_year}-W{iso_week:02d}"][norm] += 1
            monthly[d_obj.strftime('%Y-%m')][norm] += 1
            weekday[d_obj.weekday()] += 1
            effective_dates.add(d_obj)
            submission_volume_daily[d_obj] += 1  # 仅记录有效行

    total_counted = sum(norm_counter.values())
    success = norm_counter.get('Granted', 0)
    failures = norm_counter.get('Rejected/Closed', 0) + norm_counter.get('Query Failed', 0)
    success_rate = (success / total_counted) if total_counted else 0.0

    # 计算趋势：按日期的累计通过率与日增量
    daily_trend = []
    cumulative_total = 0
    cumulative_success = 0
    cumulative_proceedings = 0
    for d in sorted(daily.keys()):
        day_total = sum(daily[d].values())
        day_success = daily[d].get('Granted', 0)
        day_proceed = daily[d].get('Proceedings', 0)
        cumulative_total += day_total
        cumulative_success += day_success
        cumulative_proceedings += day_proceed
        backlog_ratio = (day_proceed / day_total) if day_total else 0.0
        cumulative_backlog_ratio = (cumulative_proceedings / cumulative_total) if cumulative_total else 0.0
        daily_trend.append({
            'date': d.isoformat(),
            'day_total': day_total,
            'day_success': day_success,
            'day_success_rate': round(day_success / day_total, 4) if day_total else 0.0,
            'cumulative_total': cumulative_total,
            'cumulative_success': cumulative_success,
            'cumulative_success_rate': round(cumulative_success / cumulative_total, 4) if cumulative_total else 0.0,
            'day_proceedings': day_proceed,
            'day_backlog_ratio': round(backlog_ratio, 4),
            'cumulative_proceedings': cumulative_proceedings,
            'cumulative_backlog_ratio': round(cumulative_backlog_ratio, 4)
        })

    # 周 / 月 汇总
    def summarize_bucket(counter_map):
        out = []
        for bucket, c in sorted(counter_map.items()):
            bucket_total = sum(c.values())
            bucket_success = c.get('Granted', 0)
            out.append({
                'bucket': bucket,
                'distribution': dict(c),
                'total': bucket_total,
                'success': bucket_success,
                'success_rate': round(bucket_success / bucket_total, 4) if bucket_total else 0.0
            })
        return out

    weekly_summary = summarize_bucket(weekly)
    # 增加 week-over-week 变化 / add deltas
    weekly_deltas = []
    prev = None
    for w in weekly_summary:
        if prev:
            change = round(w['success_rate'] - prev['success_rate'], 4)
            weekly_deltas.append({'week': w['bucket'], 'success_rate': w['success_rate'], 'delta_vs_prev': change})
        else:
            weekly_deltas.append({'week': w['bucket'], 'success_rate': w['success_rate'], 'delta_vs_prev': None})
        prev = w
    monthly_summary = summarize_bucket(monthly)

    # 工作日分布 (只统计有状态的记录) / Weekday distribution for counted rows
    weekday_map = {i: weekday.get(i, 0) for i in range(7)}

    # 状态排序
    ordered = OrderedDict()
    for s in STATUS_ORDER:
        if norm_counter.get(s):
            ordered[s] = norm_counter[s]
    for s, v in norm_counter.items():
        if s not in ordered:
            ordered[s] = v

    # 有效日期范围
    eff_first = min(effective_dates) if effective_dates else None
    eff_last = max(effective_dates) if effective_dates else None
    eff_span = ((eff_last - eff_first).days + 1) if (eff_first and eff_last) else 0

    processed = success + norm_counter.get('Rejected/Closed', 0)
    processing_rate = (processed / total_counted) if total_counted else 0.0
    rejection_rate = (norm_counter.get('Rejected/Closed', 0) / total_counted) if total_counted else 0.0

    # SLA 超时 (60天): 对出现 Proceedings 的日期估算是否 >60 天仍未出结果
    sla_days = 60
    today = datetime.date.today()
    overdue_counts = 0
    overdue_details = []
    if eff_last:
        for d in sorted(daily.keys()):
            age = (today - d).days
            if age > sla_days:
                proc = daily[d].get('Proceedings', 0)
                if proc > 0:
                    overdue_counts += proc
                    overdue_details.append({'date': d.isoformat(), 'proceedings': proc, 'age_days': age})
    sla_overdue_ratio = (overdue_counts / norm_counter.get('Proceedings', 1)) if norm_counter.get('Proceedings', 0) else 0.0

    detailed = {
        'generated_at': datetime.datetime.utcnow().isoformat() + 'Z',
        'date_range': {
            'first_date': first_date.isoformat() if first_date else None,
            'last_date': last_date.isoformat() if last_date else None,
            'days_span': ((last_date - first_date).days + 1) if (first_date and last_date) else 0
        },
        'effective_date_range': {
            'first_effective_date': eff_first.isoformat() if eff_first else None,
            'last_effective_date': eff_last.isoformat() if eff_last else None,
            'effective_days_span': eff_span
        },
        'total_rows_scanned': total_rows,
        'rows_counted': total_counted,
        'distribution': ordered,
        'success': success,
        'failures': failures,
        'success_rate': round(success_rate, 4),
        'processing_rate': round(processing_rate, 4),
        'rejection_rate': round(rejection_rate, 4),
        'raw_example_per_status': raw_examples,
        'daily_trend': daily_trend,
    'weekly_summary': weekly_summary,
    'weekly_deltas': weekly_deltas,
        'monthly_summary': monthly_summary,
        'weekday_distribution': weekday_map,
        'weekday_peak': max(weekday_map, key=lambda k: weekday_map[k]) if weekday_map else None,
        'submission_volume_daily': {d.isoformat(): submission_volume_daily[d] for d in sorted(submission_volume_daily.keys())},
        'sla_assumption_days': sla_days,
        'overdue_proceedings_count': overdue_counts,
        'overdue_proceedings_ratio_vs_current_proceedings': round(sla_overdue_ratio, 4),
        'overdue_details': overdue_details,
    }
    # 可选图表
    if charts and out_markdown_path:
        try:
            import matplotlib.pyplot as plt
            base_dir = os.path.dirname(out_markdown_path) or '.'
            dates = [x['date'] for x in detailed['daily_trend']]
            if dates:
                succ_rate = [x['day_success_rate']*100 for x in detailed['daily_trend']]
                backlog_rate = [x['day_backlog_ratio']*100 for x in detailed['daily_trend']]
                plt.figure(figsize=(10,4))
                plt.plot(dates, succ_rate, label='Day Success%')
                plt.plot(dates, backlog_rate, label='Day Backlog%')
                plt.xticks(rotation=45, ha='right', fontsize=7)
                plt.ylabel('%')
                plt.title('Daily Success vs Backlog')
                plt.legend(); plt.tight_layout()
                p1 = os.path.join(base_dir, 'chart_daily_success_backlog.png')
                plt.savefig(p1); plt.close()
                detailed.setdefault('charts', []).append(p1)
            w_weeks = [w['bucket'] for w in detailed['weekly_summary']]
            if w_weeks:
                w_rates = [w['success_rate']*100 for w in detailed['weekly_summary']]
                import matplotlib.pyplot as plt
                plt.figure(figsize=(8,4))
                plt.bar(w_weeks, w_rates)
                plt.xticks(rotation=45, ha='right', fontsize=8)
                plt.ylabel('Success%'); plt.title('Weekly Success Rate')
                plt.tight_layout(); p2 = os.path.join(base_dir, 'chart_weekly_success.png')
                plt.savefig(p2); plt.close()
                detailed.setdefault('charts', []).append(p2)
            if detailed['distribution']:
                labels = list(detailed['distribution'].keys())
                values = list(detailed['distribution'].values())
                plt.figure(figsize=(6,6))
                plt.pie(values, labels=labels, autopct='%1.1f%%')
                plt.title('Status Distribution')
                p3 = os.path.join(base_dir, 'chart_distribution.png')
                plt.savefig(p3); plt.close()
                detailed.setdefault('charts', []).append(p3)
        except Exception as e:
            detailed['chart_error'] = f'Chart generation failed: {e}'
    return detailed


def write_detailed_markdown(summary: dict, path: str, include_charts=False):
    lines = []
    lines.append('# Visa Status Detailed Report / 签证状态详细分析报告')
    lines.append('')
    # ISO week label
    try:
        from datetime import datetime as _dt
        _now_date = _dt.utcnow().date()
        _iso_year, _iso_week, _ = _now_date.isocalendar()
        lines.append(f"Generated at (UTC): {summary['generated_at']}  (ISO Week: {_iso_year}-W{_iso_week:02d})")
    except Exception:
        lines.append(f"Generated at (UTC): {summary['generated_at']}")
    dr = summary['date_range']
    lines.append(f"Date range (all rows) / 总日期范围: {dr['first_date']} ~ {dr['last_date']} (span: {dr['days_span']})")
    if 'effective_date_range' in summary:
        eff = summary['effective_date_range']
        lines.append(f"Effective range (counted) / 有效范围: {eff['first_effective_date']} ~ {eff['last_effective_date']} (span: {eff['effective_days_span']})")
    lines.append(f"Rows scanned / 扫描行数: {summary['total_rows_scanned']}")
    lines.append(f"Rows counted / 统计行数: {summary['rows_counted']}")
    lines.append('')
    lines.append('## 1. Overall Distribution / 总体分布')
    lines.append('Status | Count | Percent')
    lines.append('---|---:|---:')
    total = summary['rows_counted'] or 1
    for status, count in summary['distribution'].items():
        pct = (count / total) * 100.0
        lines.append(f"{status} | {count} | {pct:.2f}%")
    lines.append('')
    lines.append(f"Success (Granted) / 通过数: {summary['success']}")
    lines.append(f"Failures (Rejected/Closed + Query Failed) / 失败数: {summary['failures']}")
    lines.append(f"Success rate / 通过率: {summary['success_rate']*100:.2f}%")
    if 'processing_rate' in summary:
        lines.append(f"Processing rate / 已处理率: {summary['processing_rate']*100:.2f}%")
    if 'rejection_rate' in summary:
        lines.append(f"Rejection rate / 拒签率: {summary['rejection_rate']*100:.2f}%")
    lines.append('')
    lines.append('## 2. Daily Trend / 每日趋势 (含积压比 Backlog Ratio)')
    lines.append('Date | Day Total | Granted | Proceedings | Day Success% | Day Backlog% | Cumul Total | Cumul Granted | Cumul Success% | Cumul Backlog%')
    lines.append('---|---:|---:|---:|---:|---:|---:|---:|---:|---:')
    for item in summary['daily_trend']:
        lines.append(
            f"{item['date']} | {item['day_total']} | {item['day_success']} | {item['day_proceedings']} | "
            f"{item['day_success_rate']*100:.2f}% | {item['day_backlog_ratio']*100:.2f}% | {item['cumulative_total']} | {item['cumulative_success']} | "
            f"{item['cumulative_success_rate']*100:.2f}% | {item['cumulative_backlog_ratio']*100:.2f}%"
        )
    lines.append('')
    lines.append('## 3. Weekly Summary / 每周汇总 (+ Δsuccess%)')
    lines.append('Week | Total | Granted | Success% | Δ vs Prev | Distribution(JSON)')
    lines.append('---|---:|---:|---:|---:|---')
    # Build dict for delta lookup
    delta_map = {d['week']: d['delta_vs_prev'] for d in summary['weekly_deltas']}
    for w in summary['weekly_summary']:
        delta = delta_map.get(w['bucket'])
        delta_str = '—' if delta is None else f"{delta*100:.2f}%"
        lines.append(f"{w['bucket']} | {w['total']} | {w['success']} | {w['success_rate']*100:.2f}% | {delta_str} | {json.dumps(w['distribution'], ensure_ascii=False)}")
    lines.append('')
    lines.append('## 4. Monthly Summary / 每月汇总')
    lines.append('Month | Total | Granted | Success% | Distribution(JSON)')
    lines.append('---|---:|---:|---:|---')
    for m in summary['monthly_summary']:
        lines.append(f"{m['bucket']} | {m['total']} | {m['success']} | {m['success_rate']*100:.2f}% | {json.dumps(m['distribution'], ensure_ascii=False)}")
    lines.append('')
    lines.append('## 5. Weekday Distribution / 工作日分布')
    lines.append('Weekday(0=Mon) | Count | Percent')
    lines.append('---|---:|---:')
    wd_total = sum(summary['weekday_distribution'].values()) or 1
    for i in range(7):
        c = summary['weekday_distribution'].get(i, 0)
        lines.append(f"{i} | {c} | {c / wd_total * 100:.2f}%")
    lines.append('')
    lines.append(f"Peak weekday (most statuses) / 峰值工作日: {summary['weekday_peak']}")
    lines.append('')
    lines.append('## 6. Submission Volume Per Day (Counted only) / 每日提交量（仅有效计入行, 含0)')
    lines.append('Date | Count')
    lines.append('---|---:')
    dr = summary.get('date_range') or {}
    start_d = dr.get('first_date')
    end_d = dr.get('last_date')
    date_counts = summary['submission_volume_daily']
    try:
        if start_d and end_d:
            import datetime as _dt
            sd = _dt.datetime.strptime(start_d, '%Y-%m-%d').date()
            ed = _dt.datetime.strptime(end_d, '%Y-%m-%d').date()
            cur = sd
            while cur <= ed:
                iso = cur.isoformat()
                lines.append(f"{iso} | {date_counts.get(iso, 0)}")
                cur += _dt.timedelta(days=1)
        else:
            for d, cnt in date_counts.items():
                lines.append(f"{d} | {cnt}")
    except Exception:
        for d, cnt in date_counts.items():
            lines.append(f"{d} | {cnt}")
    lines.append('')
    lines.append('## 7. Raw Example Per Status / 各状态示例原文')
    for s, ex in summary['raw_example_per_status'].items():
        lines.append(f"- {s}: {ex}")
    lines.append('')
    if 'overdue_proceedings_count' in summary:
        lines.append('')
        lines.append('## 7.1 SLA Overdue (60 days) / 超过假设处理期 60 天的审理中统计')
        lines.append(f"Overdue Proceedings count: {summary.get('overdue_proceedings_count')}")
        lines.append(f"Overdue vs current Proceedings ratio: {summary.get('overdue_proceedings_ratio_vs_current_proceedings',0)*100:.2f}%")
        if summary.get('overdue_details'):
            lines.append('Date | Proceedings | AgeDays')
            lines.append('---|---:|---:')
            for od in summary['overdue_details']:
                lines.append(f"{od['date']} | {od['proceedings']} | {od['age_days']}")
    lines.append('')
    lines.append('## 8. Interpretation / 结果解读')
    lines.append('- Granted 与 Rejected/Closed 之比提供当前阶段的粗略通过 / 拒签基线。')
    lines.append('- Backlog(Proceedings) 占比越高，说明仍在审理的申请较多，后续成功率尚有变动空间。')
    lines.append('- Weekly Δsuccess% 可快速识别审批效率是否提升或下降。')
    lines.append('- Weekday 分布支持优化查询码生成集中于活跃工作日（若 0/1 峰值则偏向周一/周二提交）。')
    lines.append('- 若进一步保留历史快照（多次抓取同一查询码），可估算平均处理时长与分布（目前单快照 CSV 不含该信息）。')
    if 'overdue_proceedings_count' in summary:
        lines.append('- SLA 超时统计用于识别办理积压风险。')
    if include_charts and summary.get('charts'):
        lines.append('')
        lines.append('## 9. Charts / 图表')
        for p in summary['charts']:
            lines.append(f"![{os.path.basename(p)}]({os.path.basename(p)})")
    if include_charts and summary.get('chart_error'):
        lines.append(f"Chart generation failed: {summary['chart_error']}")
    content = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def write_json(summary: dict, path: str):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def write_markdown(summary: dict, path: str):
    lines = []
    lines.append('# Visa Status Summary / 签证状态汇总')
    lines.append('')
    lines.append(f"Generated at (UTC) / 生成时间: {summary['generated_at']}")
    lines.append(f"Rows scanned / 扫描行数: {summary['total_rows_scanned']}")
    lines.append(f"Rows counted / 统计行数: {summary['rows_counted']}")
    lines.append('')
    lines.append('## Distribution / 分布')
    lines.append('Status | Count | Percent')
    lines.append('---|---:|---:')
    total = summary['rows_counted'] or 1
    for status, count in summary['distribution'].items():
        pct = (count / total) * 100.0
        lines.append(f"{status} | {count} | {pct:.2f}%")
    lines.append('')
    lines.append(f"Success / 成功(Granted): {summary['success']}")
    lines.append(f"Failures / 失败(Rejected/Closed + Query Failed): {summary['failures']}")
    lines.append(f"Success rate / 成功率: {summary['success_rate']*100:.2f}%")
    lines.append('')
    lines.append('## Raw Example Per Status / 每个状态示例原文')
    for s, ex in summary['raw_example_per_status'].items():
        lines.append(f"- {s}: {ex}")
    content = '\n'.join(lines) + '\n'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def main(argv=None):
    p = argparse.ArgumentParser(description='Generate status distribution report / 生成状态分布报告')
    p.add_argument('-i', '--input', required=True, help='Input CSV path / 输入 CSV 路径')
    p.add_argument('-o', '--out', help='Output JSON path / 输出 JSON 路径 (默认 reports/summary_<date>.json)')
    # （已废弃的 Not Found 包含/排除开关被移除，始终忽略 Not Found 行）
    p.add_argument('--markdown', action='store_true', help='Also write Markdown summary / 生成 Markdown 摘要')
    args = p.parse_args(argv)

    inp = args.input
    if not os.path.exists(inp):
        raise SystemExit(f"Input CSV not found / 未找到输入CSV: {inp}")

    today = datetime.date.today().isoformat()
    out_json = args.out or os.path.join('reports', f'summary_{today}.json')

    header, data_rows = load_csv(inp)
    summary = generate_summary(header, data_rows)
    write_json(summary, out_json)

    if args.markdown:
        out_md = os.path.splitext(out_json)[0] + '.md'
        write_markdown(summary, out_md)
    print(f"Report written: {out_json} / 报告已生成: {out_json}")
    if args.markdown:
        print(f"Markdown written: {out_md} / Markdown 已生成: {out_md}")

if __name__ == '__main__':  # pragma: no cover
    main()
