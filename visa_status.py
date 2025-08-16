
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

    # 全局选项 / Global options
    parser.add_argument('--retries', type=int, default=3, help='Retries per query (default: 3) / 每条查询的重试次数（默认: 3）')
    parser.add_argument('--no-auto-install', action='store_true', help='Disable auto-install of missing deps at startup / 启动时禁用自动安装缺失依赖')
    parser.add_argument('--log-dir', default='logs', help='Logs directory (default: logs) / 日志目录（默认: logs）')
    parser.add_argument('--headless', action='store_true', help='Enable headless mode globally / 全局启用无头模式（子命令可覆盖）')

    # 生成器子命令
    gen_parser = subparsers.add_parser('generate-codes', help='Generate a CSV of query codes / 生成查询码CSV（支持自定义日期与数量）')
    gen_parser.add_argument('-o', '--out', default='query_codes.csv', help='output CSV path / 输出 CSV 路径')
    gen_parser.add_argument('--start', help='start date YYYY-MM-DD / 起始日期（YYYY-MM-DD）')
    gen_parser.add_argument('--end', help='end date YYYY-MM-DD / 结束日期（YYYY-MM-DD）')
    gen_parser.add_argument('--per-day', type=int, default=5, help='items per day / 每日期条目数')
    gen_parser.add_argument('--include-weekends', action='store_true', help='include weekends / 包含周末')

    # 查询器子命令（以国家码命名）
    for country_code, (mod_path, _) in QUERY_MODULES.items():
        q_parser = subparsers.add_parser(country_code, help=f'{country_code.upper()} visa-status checker / {country_code.upper()}签证状态批量查询')
        q_parser.add_argument('--i', default='query_codes.csv', help='CSV input path (default: query_codes.csv) / CSV 文件路径（默认: query_codes.csv）')
        q_parser.add_argument('--driver-path', default=None, help='ChromeDriver executable path (optional) / ChromeDriver 可执行文件路径（可选）')
        q_parser.add_argument('--headless', action='store_true', help='Run browser headless / 以无头模式运行浏览器')
        # 可扩展更多参数

    # 在运行前进行依赖检查：selenium、webdriver_manager
    def check_and_install_deps(auto_install: bool, logs_dir_name: str):
        import shutil
        import subprocess
        import datetime
        import os

        logs_dir = os.path.join(os.getcwd(), logs_dir_name)
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, f"install_{datetime.date.today().isoformat()}.log")

        def log(msg: str):
            # msg should be bilingual where possible (EN / 中文)
            ts = datetime.datetime.now().isoformat(sep=' ', timespec='seconds')
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write(f"[{ts}] {msg}\n")

        missing = []
        try:
            import selenium  # noqa: F401
            log('selenium: present / selenium: 已安装')
        except Exception:
            missing.append('selenium')
            log('selenium: missing / selenium: 未安装')
        try:
            import webdriver_manager  # noqa: F401
            log('webdriver-manager: present / webdriver-manager: 已安装')
        except Exception:
            missing.append('webdriver-manager')
            log('webdriver-manager: missing / webdriver-manager: 未安装')
        try:
            import openpyxl  # noqa: F401
            log('openpyxl: present / openpyxl: 已安装')
        except Exception:
            missing.append('openpyxl')
            log('openpyxl: missing / openpyxl: 未安装')

        chromedriver_found = False
        # check PATH for chromedriver
        if shutil.which('chromedriver') or shutil.which('chromedriver.exe'):
            chromedriver_found = True
            log('chromedriver: found in PATH / chromedriver: 在 PATH 中找到')
        else:
            log('chromedriver: not found in PATH / chromedriver: 未在 PATH 中找到')

        if missing:
            log('Missing packages: ' + ', '.join(missing) + ' / 缺失的包: ' + ', '.join(missing))
            if auto_install:
                log('Auto-install enabled; attempting pip install / 自动安装已启用，尝试通过 pip 安装')
                try:
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing)
                    log('pip install succeeded for: ' + ', '.join(missing) + ' / pip 安装成功: ' + ', '.join(missing))
                except Exception as e:
                    log('pip install failed: ' + str(e) + ' / pip 安装失败: ' + str(e))
            else:
                log('Auto-install disabled; skipping pip install / 未启用自动安装，跳过 pip 安装')

        # After install attempt, check for webdriver-manager availability
        try:
            import webdriver_manager  # noqa: F401
            has_wdm = True
            log('webdriver-manager: available after install check / webdriver-manager: 安装检查后可用')
        except Exception:
            has_wdm = False
            log('webdriver-manager: still not available / webdriver-manager: 仍然不可用')

        if not chromedriver_found:
            if has_wdm:
                log('Will use webdriver-manager to download chromedriver at runtime / 将使用 webdriver-manager 在运行时下载 chromedriver')
            else:
                # no chromedriver and no webdriver-manager: log warning
                log('Warning: chromedriver not found and webdriver-manager not available. User must install chromedriver or provide --driver-path / 警告：未找到 chromedriver 且 webdriver-manager 不可用。请安装 chromedriver 或使用 --driver-path 指定驱动路径')

    # run dependency check with chosen behavior (use parse_known_args to read global opts before full parse)
    known_args, _ = parser.parse_known_args()
    check_and_install_deps(auto_install=not known_args.no_auto_install, logs_dir_name=known_args.log_dir)

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
        # 只传递 --i、--driver-path、--headless 参数到查询模块
        import argparse as ap
        q_parser = ap.ArgumentParser()
        q_parser.add_argument('--i', default='query_codes.csv')
        q_parser.add_argument('--driver-path', default=None)
        q_parser.add_argument('--headless', action='store_true')
        q_parser.add_argument('--retries', type=int, default=None, help='针对该子命令的重试次数，覆盖全局 --retries')
        q_args, _ = q_parser.parse_known_args(cmd_args)
        # 决定最终参数：优先子命令本身的设置，其次全局设置
        headless_val = bool(q_args.headless) or bool(args.headless)
        retries_val = q_args.retries if (q_args.retries is not None) else args.retries
        try:
            func(q_args.i, driver_path=q_args.driver_path, headless=headless_val, retries=retries_val, log_dir=args.log_dir)
        except TypeError:
            # 兼容旧模块签名，仅传入csv路径
            func(q_args.i)
    # no separate setup command anymore; dependency handled at startup
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
