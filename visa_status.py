
import argparse
import sys
import importlib

# 工具注册表：key为命令名，值为(模块路径, 主函数名)
TOOLS = {
    'generate-codes': ('tools.generate_codes', 'main'),
}

# 查询器注册表（Playwright-only），所有国家查询模块均用二字国家码命名（如cz、us、de等）
QUERY_MODULES = {
    'cz': ('query_modules.cz', 'update_csv_with_status'),
    # 未来可扩展更多国家，如 'us': ('query_modules.us', 'update_csv_with_status')
}

def main():
    parser = argparse.ArgumentParser(
        description='Visa_Status: 一站式签证批量工具主程序\n\n'
                    '所有查询模块均以二字国家码命名（如cz、us、de），便于扩展。\n'
                    '用法示例：\n'
                    '  python visa_status.py generate-codes -o my.csv --start 2025-06-01\n'
                    '  python visa_status.py cz --i my.csv\n',
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='可用子命令')

    # 全局选项 / Global options
    parser.add_argument('-r', '--retries', type=int, default=3, help='Retries per query (default: 3) / 每条查询的重试次数（默认: 3）')
    parser.add_argument('-l', '--log-dir', default='logs', help='Logs directory (default: logs) / 日志目录（默认: logs）')

    # 生成器子命令
    gen_parser = subparsers.add_parser('generate-codes', aliases=['gen', 'gc'], help='Generate a CSV of query codes / 生成查询码CSV（支持自定义日期与数量）')
    gen_parser.add_argument('-o', '--out', default='query_codes.csv', help='output CSV path / 输出 CSV 路径')
    gen_parser.add_argument('-s', '--start', help='start date YYYY-MM-DD / 起始日期（YYYY-MM-DD）')
    gen_parser.add_argument('-e', '--end', help='end date YYYY-MM-DD / 结束日期（YYYY-MM-DD）')
    gen_parser.add_argument('-n', '--per-day', type=int, default=5, help='items per day / 每日期条目数')
    gen_parser.add_argument('-w', '--include-weekends', action='store_true', help='include weekends / 包含周末')
    gen_parser.add_argument('-x', '--exclude-weekdays', '--exclude', '--排除', '--日期排除',
                            help='Exclude weekdays digits (1=Mon..7=Sun), e.g. 35 or "3 5" / 排除指定星期(1=周一..7=周日)，如 35 或 "3 5"',
                            default=None)
    gen_parser.add_argument('-p', '--prefix', '--前缀',
                            help='Code prefix (default: PEKI) / 代码前缀（默认: PEKI）',
                            default='PEKI')

    # 报告子命令 / report subcommand
    rep_parser = subparsers.add_parser('report', aliases=['rep', 'r'], help='Generate detailed Markdown report / 生成详细 Markdown 报告')
    rep_parser.add_argument('-i', '--input', required=False, default='query_codes.csv',
                            help='Input CSV path (default: query_codes.csv) / 输入 CSV 路径（默认: query_codes.csv）')
    rep_parser.add_argument('-o', '--out', help='Output Markdown path (default: reports/summary_TIMESTAMP.md) / 输出 Markdown 路径（默认 reports/summary_时间戳.md）')
    rep_parser.add_argument('-c', '--charts', action='store_true', help='Generate charts (requires matplotlib) / 生成图表（需要 matplotlib）')
    # 查询器子命令（以国家码命名，Playwright-only）
    for country_code, (mod_path, _) in QUERY_MODULES.items():
        aliases = ['c'] if country_code == 'cz' else []
        q_parser = subparsers.add_parser(country_code, aliases=aliases, help=f'{country_code.upper()} visa-status checker (Playwright) / {country_code.upper()}签证状态批量查询（Playwright）')
        q_parser.add_argument('-i', '--i', default='query_codes.csv', help='CSV input path (default: query_codes.csv) / CSV 文件路径（默认: query_codes.csv）')
        # Headless now defaults to True. Provide optional value so legacy "--headless" (no value) still works.
        q_parser.add_argument('-H', '--headless', nargs='?', const='true', default=None, metavar='[BOOL]',
                              help='Headless mode (default True). Use "--headless False" to SHOW browser. Accepts true/false/on/off/yes/no/0/1 / 无头模式(默认 True)。使用 "--headless False" 显示浏览器。接受 true/false/on/off/yes/no/0/1')
        q_parser.add_argument('-w', '--workers', type=int, default=1, help='Number of concurrent workers (pages) / 并发 worker 数 (默认: 1)')

    # 依赖提示（精简，仅记录 Playwright 与 matplotlib 提示）
    def check_notes(logs_dir_name: str):
        import datetime, os
        logs_dir = os.path.join(os.getcwd(), logs_dir_name)
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, f"install_{datetime.date.today().isoformat()}.log")

        def log(msg: str):
            ts = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write(f"[{ts}] {msg}\n")

        try:
            import playwright  # noqa: F401
            log('playwright: present / playwright: 已安装')
        except Exception:
            log('playwright: missing (install with: pip install playwright; then python -m playwright install chromium) / playwright: 未安装（使用 pip install playwright；随后 python -m playwright install chromium）')

        want_matplotlib = '--charts' in sys.argv and 'report' in sys.argv
        try:
            import matplotlib  # noqa: F401
            log('matplotlib: present / matplotlib: 已安装')
        except Exception:
            if want_matplotlib:
                log('matplotlib: missing (required for --charts) / matplotlib: 未安装（--charts 需要）')

    # run dependency notes
    _known_args, _ = parser.parse_known_args()
    check_notes(logs_dir_name=_known_args.log_dir)

    # 记录原始子命令 token（用于后续更可靠地切分参数）
    original_subcmd = None
    if len(sys.argv) > 1:
        # 找到第一个既不是全局选项（-r/-l 等）又不是其值的 token，作为子命令初步猜测
        # 简化：如果 token 不以 '-' 开头，则认为是子命令
        for tok in sys.argv[1:]:
            if not tok.startswith('-'):
                original_subcmd = tok
                break

    args = parser.parse_args()

    # 统一别名映射，防止 argparse 在特定 Python 版本/实现下返回别名值导致匹配失败
    alias_map = {
        'gc': 'generate-codes',
        'gen': 'generate-codes',
        'rep': 'report',
        'r': 'report',
        'c': 'cz',
    }
    if args.command in alias_map:
        args.command = alias_map[args.command]

    # 动态切分子命令后续参数（支持全局参数位于子命令之前，例如: -r 2 gc -n 5）
    cmd_args = []
    if original_subcmd:
        try:
            # 定位原始出现位置，再取其后的所有参数
            idx = sys.argv.index(original_subcmd)
            cmd_args = sys.argv[idx + 1:]
        except ValueError:
            cmd_args = sys.argv[2:]
    else:
        cmd_args = sys.argv[2:]

    if args.command in TOOLS:
        mod_name, func_name = TOOLS[args.command]
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        func(cmd_args)
    elif args.command == 'report':
        # 专门处理报告：只生成 Markdown
        import tools.report as report_mod
        import datetime, os, shutil
        input_csv = args.input
        if input_csv == 'query_codes.csv':
            print('Using default input CSV: query_codes.csv (override with -i) / 使用默认输入文件 query_codes.csv（可用 -i 指定）')
        out_md = args.out
        generate_charts = args.charts
        # 若需要图表且未安装 matplotlib，尝试自动安装一次
        if generate_charts:
            # At this point dependency check may already have installed matplotlib if --charts was present.
            # Re-verify and attempt a one-shot install if still missing (user might have disabled auto-install earlier).
            try:
                import matplotlib  # noqa: F401
            except Exception:
                try:
                    import subprocess
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'matplotlib'])
                except Exception:
                    print('Warning: auto-install matplotlib failed; charts may not be generated / 警告：自动安装 matplotlib 失败，图表可能无法生成')
        if not out_md:
            now = datetime.datetime.now()
            date_part = now.strftime('%Y-%m-%d')
            time_part = now.strftime('%H-%M-%S')
            base_dir = os.path.join('reports', date_part, time_part)
            os.makedirs(base_dir, exist_ok=True)
            out_md = os.path.join(base_dir, 'summary.md')
        else:
            os.makedirs(os.path.dirname(out_md) or '.', exist_ok=True)
        # 在报告目录内归档输入 CSV（保留原文件名） / Archive input CSV into the report folder
        try:
            if os.path.exists(input_csv):
                dest_csv = os.path.join(os.path.dirname(out_md), os.path.basename(input_csv))
                # Avoid self-copy if already same path
                if os.path.abspath(input_csv) != os.path.abspath(dest_csv):
                    shutil.copy2(input_csv, dest_csv)
                print(f"Archived input CSV: {dest_csv} / 已归档输入CSV：{dest_csv}")
            else:
                print(f"Warning: input CSV not found, skip archive: {input_csv} / 警告：未找到输入CSV，跳过归档：{input_csv}")
        except Exception as e:
            print(f"Warning: failed to archive input CSV: {e} / 警告：归档输入CSV失败：{e}")
        header, rows = report_mod.load_csv(input_csv)
        summary = report_mod.generate_detailed_summary(header, rows, charts=generate_charts, out_markdown_path=out_md)
        report_mod.write_detailed_markdown(summary, out_md, include_charts=generate_charts)
        print(f"Markdown report written: {out_md} / 详细报告已生成")
    elif args.command in QUERY_MODULES:
        mod_name, func_name = QUERY_MODULES[args.command]
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        import argparse as ap
        q_parser = ap.ArgumentParser()
        q_parser.add_argument('-i', '--i', default='query_codes.csv')
        q_parser.add_argument('-H', '--headless', nargs='?', const='true', default=None)
        q_parser.add_argument('-w', '--workers', type=int, default=1)
        q_parser.add_argument('-r', '--retries', type=int, default=None, help='针对该子命令的重试次数，覆盖全局 --retries')
        q_args, _ = q_parser.parse_known_args(cmd_args)

        def _parse_bool(val, default_true=True):
            if val is None:
                return True if default_true else False
            if isinstance(val, bool):
                return val
            s = str(val).strip().lower()
            if s in ('1', 'true', 't', 'yes', 'y', 'on'):
                return True
            if s in ('0', 'false', 'f', 'no', 'n', 'off'):
                return False
            return True if default_true else False

        headless_val = _parse_bool(q_args.headless, default_true=True)

        if q_args.headless is None and headless_val:
            print('Headless mode: ON (default). Use --headless False to show browser. / 无头模式：开启（默认）。使用 --headless False 显示浏览器。')
        elif q_args.headless is not None and not headless_val:
            print('Headless mode: OFF (UI visible). / 无头模式：关闭（显示浏览器）。')
        retries_val = q_args.retries if (q_args.retries is not None) else args.retries
        try:
            func(q_args.i, headless=headless_val, workers=q_args.workers, retries=retries_val, log_dir=args.log_dir)
        except TypeError:
            func(q_args.i)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
