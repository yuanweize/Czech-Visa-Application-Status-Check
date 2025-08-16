
import argparse
import sys
import importlib

# 工具注册表：key为命令名，值为(模块路径, 主函数名)
TOOLS = {
    'generate-codes': ('tools.generate_codes', 'main'),
}

# 查询器注册表，所有国家查询模块均用二字国家码命名（如cz、us、de等）
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

    # 生成器子命令
    gen_parser = subparsers.add_parser('generate-codes', help='批量生成查询码（支持自定义日期、数量等）')
    gen_parser.add_argument('-o', '--out', default='query_codes.csv', help='输出csv路径')
    gen_parser.add_argument('--start', help='起始日期 YYYY-MM-DD')
    gen_parser.add_argument('--end', help='结束日期 YYYY-MM-DD')
    gen_parser.add_argument('--per-day', type=int, default=5, help='每个日期的序列数')
    gen_parser.add_argument('--include-weekends', action='store_true', help='包含周末')

    # 查询器子命令（以国家码命名）
    for country_code, (mod_path, _) in QUERY_MODULES.items():
        q_parser = subparsers.add_parser(country_code, help=f'{country_code.upper()}签证状态批量查询')
        q_parser.add_argument('--i', default='query_codes.csv', help='csv文件路径')
        # 可扩展更多参数

    # 只将本子命令后的参数传递给对应工具
    cmd_args = sys.argv[2:]
    args = parser.parse_args()

    if args.command in TOOLS:
        mod_name, func_name = TOOLS[args.command]
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        func(cmd_args)
    elif args.command in QUERY_MODULES:
        mod_name, func_name = QUERY_MODULES[args.command]
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        # 只传递--i参数
        import argparse as ap
        q_parser = ap.ArgumentParser()
        q_parser.add_argument('--i', default='query_codes.csv')
        q_args, _ = q_parser.parse_known_args(cmd_args)
        func(q_args.i)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
