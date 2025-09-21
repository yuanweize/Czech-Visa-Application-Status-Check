import argparse
import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Optional


STATUS_MAP = {
    'not found': 'n', '未找到': 'n', 'notfound': 'n',
    'granted': 'g', '已通过': 'g',
    'proceedings': 'p', '审理中': 'p', 'processing': 'p',
    'rejected': 'r', '被拒绝': 'r',
}


def normalize_status(value: str) -> str:
    if not value:
        return 'other'
    v = value.strip().lower()
    # Often like "Granted/已通过" — split by '/'
    if '/' in v:
        v = v.split('/', 1)[0].strip()
    # Remove spaces for keys like "not found"
    key = v.replace(' ', '')
    # direct
    if v in STATUS_MAP:
        return STATUS_MAP[v]
    if key in STATUS_MAP:
        return STATUS_MAP[key]
    # try contains
    for k, sym in STATUS_MAP.items():
        if k in v:
            return sym
    return 'other'


def parse_fm_arg(fm: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Parse -fm like "target:foo@bar,freq_minutes:60" or "t:foo,f:40" or "f:40"."""
    if not fm:
        return None, None
    target = None
    freq = None
    parts = [p.strip() for p in fm.split(',') if p.strip()]
    for part in parts:
        if ':' not in part:
            # tolerate single value like "f40"? keep strict per spec
            continue
        k, v = part.split(':', 1)
        k = k.strip().lower()
        v = v.strip()
        if k in ('target', 't'):
            target = v
        elif k in ('freq_minutes', 'f'):
            try:
                freq = int(v)
            except ValueError:
                pass
    return target, freq


def decide_output_path(in_path: str, out_path: Optional[str], json_mode: bool = True) -> str:
    if out_path:
        return out_path
    base_dir = os.path.dirname(os.path.abspath(in_path)) or '.'
    base_name = os.path.splitext(os.path.basename(in_path))[0]
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = '.json' if json_mode else '.csv'
    return os.path.join(base_dir, f"{base_name}_Cleaned_{ts}{suffix}")


def load_latest_status_per_code(csv_path: str) -> Dict[str, Tuple[str, str]]:
    """Return mapping code -> (date_str, status_key) for latest date (lexicographic YYYY-MM-DD)."""
    latest: Dict[str, Tuple[str, str]] = {}
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Expect headers like 日期/Date, 查询码/Code, 签证状态/Status
        # Try to detect columns by substring
        cols = reader.fieldnames or []
        def find_col(candidates: List[str]) -> Optional[str]:
            for c in cols:
                lc = c.lower()
                if any(x in lc for x in candidates):
                    return c
            return None
        date_col = find_col(['date', '日期']) or cols[0]
        code_col = find_col(['code', '查询码']) or cols[1]
        status_col = find_col(['status', '状态']) or cols[2]
        for row in reader:
            code = (row.get(code_col) or '').strip().upper()
            if not code:
                continue
            date_val = (row.get(date_col) or '').strip()
            status_raw = (row.get(status_col) or '').strip()
            skey = normalize_status(status_raw)
            # keep the latest by date string (CSV uses YYYY-MM-DD)
            prev = latest.get(code)
            if prev is None or date_val > prev[0]:
                latest[code] = (date_val, skey)
    return latest


def build_code_entries(codes: List[str], target: Optional[str], freq: Optional[int]) -> List[dict]:
    out = []
    for c in sorted(codes):
        item = {'code': c}
        if target:
            item['channel'] = 'email'
            item['target'] = target
        if isinstance(freq, int):
            item['freq_minutes'] = freq
        out.append(item)
    return out


def summarize(counts: Dict[str, int]) -> str:
    labels = {'g': 'Granted/已通过', 'p': 'Proceedings/审理中', 'r': 'Rejected/被拒绝', 'n': 'Not Found/未找到', 'other': 'Other/其他'}
    parts = []
    total = sum(counts.values())
    for k in ('g', 'p', 'r', 'n', 'other'):
        if counts.get(k):
            parts.append(f"{labels[k]}: {counts[k]}")
    return f"Total: {total} | " + ", ".join(parts)


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(
        prog='clean',
        description='Clean CSV by status and output JSON for CODES_JSON. 删除CSV中的未找到或按指定类型筛选，并输出用于CODES_JSON的JSON文件。',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Examples / 示例:\n'
            '  python visa_status.py cl\n'
            '    -> Remove all Not Found and output JSON. / 剔除所有“未找到”，输出 JSON。\n'
            '  python visa_status.py cl -k gp\n'
            '    -> Keep only Granted & Proceedings. / 仅保留 通过 与 审理中。\n'
            '  python visa_status.py cl -k g,r\n'
            '    -> Keep only Granted & Rejected. / 仅保留 通过 与 拒绝。\n'
            '  python visa_status.py cl -fm t:you@mail.com,f:60\n'
            '    -> Output JSON with channel=email, target=you@mail.com, freq_minutes=60. / 输出含邮件与频率字段的 JSON。\n'
            '  python visa_status.py clean -i data.csv -o out.json\n'
            '    -> Specify input and output. / 指定输入与输出。\n'
        )
    )
    parser.add_argument('-i', '--input', '--in', dest='input', default='query_codes.csv',
                        help='Input CSV path (default: query_codes.csv) / 输入CSV路径（默认 query_codes.csv）')
    parser.add_argument('-o', '--output', '--out', dest='output', default=None,
                        help='Output file path (default: <input>_Cleaned_<timestamp>.json) / 输出文件路径（默认 <输入>_Cleaned_时间戳.json）')
    parser.add_argument('-k', '--keep', dest='keep', default=None,
                        help='Keep only types: combination of n,g,p,r (e.g. "gp", "g,r"). No -k means drop Not Found only. / 仅保留类型：n,g,p,r的组合（如"gp"、"g,r"）。不指定则只剔除未找到。')
    parser.add_argument('-fm', '--for-monitor', dest='fm', default=None,
                        help='Format fields for monitor JSON, e.g. "target:you@mail.com,freq_minutes:60" or "t:you@mail.com,f:60" or "f:40". / 为监控生成字段，如 "target:你@mail.com,freq_minutes:60" 或 "t:你@mail.com,f:60" 或仅 "f:40"')

    args, _ = parser.parse_known_args(argv)

    src = args.input
    if not os.path.exists(src):
        print(f"Input CSV not found: {src} / 未找到输入CSV：{src}")
        return

    latest = load_latest_status_per_code(src)
    # Count statuses on final snapshot
    counts: Dict[str, int] = defaultdict(int)
    for _, (_, skey) in latest.items():
        counts[skey] += 1

    # Decide keep set
    selected: List[str] = []
    if args.keep:
        keep_raw = args.keep.replace(',', '').strip().lower()
        keep_set = set(ch for ch in keep_raw if ch in {'n', 'g', 'p', 'r'})
        for code, (_, skey) in latest.items():
            if skey in keep_set:
                selected.append(code)
    else:
        # default: drop Not Found only
        for code, (_, skey) in latest.items():
            if skey != 'n':
                selected.append(code)

    kept_counts: Dict[str, int] = defaultdict(int)
    removed_counts: Dict[str, int] = defaultdict(int)
    selected_set = set(selected)
    for code, (_, skey) in latest.items():
        if code in selected_set:
            kept_counts[skey] += 1
        else:
            removed_counts[skey] += 1

    target, freq = parse_fm_arg(args.fm)
    out_items = build_code_entries(selected, target, freq)
    out_path = decide_output_path(src, args.output, json_mode=True)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(out_items, f, ensure_ascii=False, indent=2)

    # Summary (EN/中文)
    total_codes = len(latest)
    kept_total = len(selected)
    removed_total = total_codes - kept_total
    print("Clean summary / 清理结果:")
    print(f"  Input / 输入: {src}")
    print(f"  Output(JSON) / 输出(JSON): {out_path}")
    print(f"  Codes total / 总数: {total_codes}, kept / 保留: {kept_total}, removed / 删除: {removed_total}")
    if args.keep:
        print(f"  Keep filter / 保留类型: {args.keep} (n=Not Found, g=Granted, p=Proceedings, r=Rejected)")
    else:
        print("  Default / 默认: removed all Not Found codes / 剔除所有 未找到")
    print("  Kept by status / 按状态保留统计:")
    for k in ('g', 'p', 'r', 'n', 'other'):
        if kept_counts.get(k):
            print(f"    - {k}: {kept_counts[k]}")
    print("  Removed by status / 按状态删除统计:")
    for k in ('g', 'p', 'r', 'n', 'other'):
        if removed_counts.get(k):
            print(f"    - {k}: {removed_counts[k]}")


if __name__ == '__main__':
    main()
