#!/usr/bin/env python3
"""Czech visa status checker (Playwright-only, asyncio-based)

Essential features only:
- Parameters: CSV path, headless, workers, retries (default 3)
- Async concurrency with N workers using Playwright (Chromium)
- Immediate per-row CSV flush; failures appended to logs/fails/DATE_fails.csv

CSV expectations:
- Header includes a code column (default name: '查询码/Code')
- A status column '签证状态/Status' will be created if missing
"""
from __future__ import annotations

import asyncio
import csv
import datetime
import os
from typing import Optional
import random

IPC_URL = 'https://ipc.gov.cz/en/status-of-your-application/'

# Global browser and context tracking for cleanup
_global_browser = None
_active_contexts = set()


# =============================================================================
# Utility Functions
# =============================================================================

def _find_col(header: list[str], name: str) -> Optional[int]:
    """Find column index by name (case-insensitive, partial match)."""
    if name in header:
        return header.index(name)
    nl = name.lower()
    for i, h in enumerate(header):
        if h and h.lower() == nl:
            return i
    for i, h in enumerate(header):
        if h and nl in h.lower():
            return i
    return None


def _normalize_status(text: str) -> str:
    """Normalize raw status text to standardized format."""
    if not text:
        return 'Unknown/未知'
    low = text.strip().lower()
    if 'not found' in low:
        return 'Not Found/未找到'
    if 'still' in low and 'proceedings' in low:
        return 'Proceedings/审理中'
    if 'granted' in low or 'approved' in low or 'for information on how to proceed' in low:
        return 'Granted/已通过'
    if 'proceedings' in low:
        return 'Rejected/被拒绝'
    return 'Unknown Status/未知状态' + f"(status_text/状态文本: {text})"


# =============================================================================
# Browser Page Helpers
# =============================================================================

async def _handle_cookies(page) -> None:
    """Handle cookie consent dialog if present.
    
    Uses Playwright's locator API for clean element interaction.
    The site shows a cookie banner that must be dismissed before form interaction.
    """
    try:
        # Try to find and click the "Agree with all" button
        cookie_btn = page.locator("button.button__primary", has_text="Agree with all")
        await cookie_btn.click(timeout=2000)
        # Brief wait for dialog to close
        await page.wait_for_timeout(300)
    except Exception:
        # Cookie dialog may not appear, already dismissed, or timed out - all OK
        pass


async def _ensure_ready(page, nav_sem: asyncio.Semaphore | None = None) -> bool:
    """Ensure the page is ready with the visa input visible.
    
    Returns True if navigation was performed, False if page was already ready.
    """
    # Check if we're already on the right page with form ready
    try:
        input_el = page.locator("input[name='visaApplicationNumber']")
        if await input_el.is_visible(timeout=1000):
            return False
    except Exception:
        pass
    
    # Need to navigate
    async def do_navigate():
        await page.goto(IPC_URL, wait_until='domcontentloaded', timeout=20000)
        await _handle_cookies(page)
        # Wait for the visa input field to be visible
        await page.locator("input[name='visaApplicationNumber']").wait_for(state='visible', timeout=15000)
    
    if nav_sem:
        async with nav_sem:
            await do_navigate()
    else:
        await do_navigate()
    
    return True


async def _process_one(page, code: str, nav_sem: asyncio.Semaphore | None = None) -> tuple[str, dict]:
    """Process a single visa code query.
    
    Args:
        page: Playwright page instance
        code: Visa application number to query
        nav_sem: Optional semaphore for rate limiting navigation
    
    Returns:
        Tuple of (normalized_status, timings_dict)
    """
    loop = asyncio.get_event_loop()
    t_start = loop.time()
    
    # Ensure page is ready
    did_nav = await _ensure_ready(page, nav_sem)
    t_nav = loop.time()
    
    # Add slight jitter to avoid synchronized bursts (30-120ms)
    await asyncio.sleep(random.uniform(0.03, 0.12))
    
    # Fill the visa application number
    input_el = page.locator("input[name='visaApplicationNumber']")
    await input_el.clear()
    await input_el.fill(code)
    
    # Submit the form
    submit_btn = page.locator("button[type='submit']")
    await submit_btn.click()
    t_submit = loop.time()
    
    # Wait for result
    text = await _wait_for_result(page)
    t_result = loop.time()
    
    if not text:
        raise TimeoutError('No result text found')
    
    timings = {
        'nav_s': max(0.0, t_nav - t_start),
        'fill_s': max(0.0, t_submit - t_nav),
        'read_s': max(0.0, t_result - t_submit),
        'navigated': did_nav,
    }
    
    return _normalize_status(text), timings


async def _wait_for_result(page, timeout: float = 15.0) -> str:
    """Wait for and extract result text from alert elements."""
    loop = asyncio.get_event_loop()
    result_selectors = [
        ".alert__content",
        ".alert",
        "[role='alert']",
        "[aria-live]"
    ]
    
    text = ''
    end_time = loop.time() + timeout
    
    while loop.time() < end_time and not text:
        for selector in result_selectors:
            try:
                result_el = page.locator(selector)
                if await result_el.count() > 0 and await result_el.first.is_visible(timeout=500):
                    raw_text = await result_el.first.inner_text()
                    if raw_text and raw_text.strip():
                        text = raw_text.strip()
                        break
            except Exception:
                continue
        
        if not text:
            await asyncio.sleep(0.2)
    
    return text


async def _process_oam(page, oam_config: dict, nav_sem: asyncio.Semaphore | None = None) -> tuple[str, dict]:
    """Process an OAM reference number query.
    
    Args:
        page: Playwright page instance
        oam_config: Dict with keys: serial, suffix (optional), type, year
        nav_sem: Optional semaphore for rate limiting navigation
    
    Returns:
        Tuple of (normalized_status, timings_dict)
    """
    loop = asyncio.get_event_loop()
    t_start = loop.time()
    
    # Ensure page is ready
    did_nav = await _ensure_ready(page, nav_sem)
    t_nav = loop.time()
    
    # Add slight jitter
    await asyncio.sleep(random.uniform(0.03, 0.12))
    
    # Fill OAM form fields using correct name selectors
    # Serial number input (NOT the disabled OAM prefix)
    serial_input = page.locator("input[name='proceedings.referenceNumber']")
    await serial_input.clear()
    await serial_input.fill(oam_config['serial'])
    
    # Fill suffix if provided (optional)
    if oam_config.get('suffix'):
        suffix_input = page.locator("input[name='proceedings.additionalSuffix']")
        await suffix_input.clear()
        await suffix_input.fill(oam_config['suffix'])
    
    # Select type from React Select dropdown
    type_value = oam_config['type']
    type_dropdown = page.locator(".react-select:has(input[name='proceedings.category']) .react-select__control")
    await type_dropdown.click()
    await page.wait_for_timeout(300)  # Wait for dropdown to open
    
    # Click the option with matching text
    type_option = page.locator(f".react-select__option:has-text('{type_value}')")
    if await type_option.count() > 0:
        await type_option.first.click()
    else:
        # Fallback: type and enter
        await page.keyboard.type(type_value)
        await page.keyboard.press("Enter")
    
    await page.wait_for_timeout(150)
    
    # Select year from React Select dropdown
    year_value = str(oam_config['year'])
    year_dropdown = page.locator(".react-select:has(input[name='proceedings.year']) .react-select__control")
    await year_dropdown.click()
    await page.wait_for_timeout(300)
    
    year_option = page.locator(f".react-select__option:has-text('{year_value}')")
    if await year_option.count() > 0:
        await year_option.first.click()
    else:
        await page.keyboard.type(year_value)
        await page.keyboard.press("Enter")
    
    t_fill = loop.time()
    
    # Submit the form
    submit_btn = page.locator("button[type='submit']")
    await submit_btn.click()
    t_submit = loop.time()
    
    # Wait for result
    text = await _wait_for_result(page)
    t_result = loop.time()
    
    if not text:
        raise TimeoutError('No result text found')
    
    timings = {
        'nav_s': max(0.0, t_nav - t_start),
        'fill_s': max(0.0, t_submit - t_fill),
        'read_s': max(0.0, t_result - t_submit),
        'navigated': did_nav,
    }
    
    return _normalize_status(text), timings


# =============================================================================
# Browser Context Management
# =============================================================================

async def _create_browser_context(browser):
    """Create a new browser context with resource blocking.
    
    Blocks images and fonts to reduce bandwidth and speed up queries.
    """
    context = await browser.new_context()
    
    async def route_handler(route):
        try:
            if route.request.resource_type in {"image", "font"}:
                await route.abort()
            else:
                await route.continue_()
        except Exception:
            try:
                await route.continue_()
            except Exception:
                pass
    
    try:
        await context.route("**/*", route_handler)
        _active_contexts.add(context)
    except Exception:
        pass
    
    return context


async def _worker(name: str, browser, queue: asyncio.Queue, result_cb, retries: int, nav_sem: asyncio.Semaphore):
    """Worker that processes codes from queue.
    
    Each worker maintains its own browser context and page, processing
    codes until it receives a None sentinel value.
    """
    context = await _create_browser_context(browser)
    page = await context.new_page()
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(20000)
    
    try:
        # Pre-warm: navigate once at startup
        try:
            await _ensure_ready(page, nav_sem)
        except Exception:
            pass
        
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            
            idx, code = item
            status = 'Query Failed/查询失败'
            err = ''
            timings = {'nav_s': 0.0, 'fill_s': 0.0, 'read_s': 0.0, 'navigated': False}
            attempts_used = 0
            
            for attempt in range(1, retries + 1):
                attempts_used = attempt
                try:
                    # Check if page needs recreation
                    if page.is_closed():
                        try: await context.close()
                        except Exception: pass
                        context = await _create_browser_context(browser)
                        page = await context.new_page()
                        page.set_default_timeout(15000)
                    
                    # Create mock cfg for ZOV
                    cfg = type('cfg', (), {'code': code, 'query_type': 'zov'})()
                    status, timings = await _execute_single_query(page, cfg, nav_sem)
                    err = ''
                    break
                    
                except Exception as e:
                    err = str(e)
                    # Check for closed signals
                    if any(sig in err.lower() for sig in ('closed', 'connection')):
                        try: await context.close()
                        except Exception: pass
                        try:
                            context = await _create_browser_context(browser)
                            page = await context.new_page()
                            page.set_default_timeout(15000)
                        except Exception: pass
                    
                    if attempt < retries:
                        await asyncio.sleep(1.0 + 0.5 * attempt)
                    else:
                        status = 'Query Failed/查询失败'
            
            await result_cb(idx, code, status, err, attempts_used, timings)
            queue.task_done()
            
    finally:
        try:
            await context.close()
            _active_contexts.discard(context)
        except Exception:
            pass


# =============================================================================
# Main Run Function
# =============================================================================

async def _run(csv_path: str, headless: bool, workers: int, retries: int, log_dir: str, 
               external_callback=None, suppress_cli: bool = False):
    """Main async run function for batch visa status queries."""
    from playwright.async_api import async_playwright

    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found / [错误] 未找到CSV文件: {csv_path}")
        return

    # Load CSV
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    
    if not rows:
        print('[Error] Empty CSV / 空CSV')
        return
    
    header = rows[0]
    code_idx = _find_col(header, '查询码/Code')
    if code_idx is None:
        raise ValueError(f'Could not find code column 查询码/Code in CSV header: {header}')
    
    status_idx = _find_col(header, '签证状态/Status')
    if status_idx is None:
        header.append('签证状态/Status')
        status_idx = len(header) - 1

    # Prepare queue with codes that need processing
    queue: asyncio.Queue = asyncio.Queue()
    row_map: dict[str, int] = {}
    
    for i, row in enumerate(rows[1:], 1):
        while len(row) < len(header):
            row.append('')
        code = row[code_idx]
        status_cell = str(row[status_idx]).strip() if row[status_idx] else ''
        # Skip if has non-failed status
        if status_cell and 'query failed' not in status_cell.lower():
            continue
        row_map[code] = i
        await queue.put((i, code))

    # Setup failure logging
    rows_lock = asyncio.Lock()
    fails_dir = os.path.join(os.getcwd(), log_dir, 'fails')
    os.makedirs(fails_dir, exist_ok=True)
    fail_file = os.path.join(fails_dir, f"{datetime.date.today().isoformat()}_fails.csv")
    fail_header_needed = not os.path.exists(fail_file)

    # Load existing failure counts
    fail_counts: dict[str, int] = {}
    if os.path.exists(fail_file):
        try:
            with open(fail_file, 'r', encoding='utf-8') as rf:
                cr = csv.reader(rf)
                next(cr, None)  # Skip header
                for r in cr:
                    if len(r) >= 2:
                        c = r[1].strip()
                        if c and c != '查询码/Code':
                            fail_counts[c] = fail_counts.get(c, 0) + 1
        except Exception:
            pass

    # Statistics
    stats = {
        'total': 0, 'success': 0, 'fail': 0,
        'retry_needed': 0, 'retry_success': 0, 'total_attempts': 0,
        'nav_sum': 0.0, 'fill_sum': 0.0, 'read_sum': 0.0,
        'nav_count': 0, 'fill_count': 0, 'read_count': 0, 'nav_events': 0,
    }

    async def on_result(idx: int, code: str, status: str, err: str, attempts_used: int, timings: dict):
        nonlocal fail_header_needed
        async with rows_lock:
            rows[idx][status_idx] = status
            
            # Flush CSV
            try:
                from monitor.utils.file_ops import write_csv_atomic
                write_csv_atomic(csv_path, header, rows[1:])
            except Exception as e:
                print(f"[Warning] Failed to write CSV '{csv_path}': {e}")
            
            # Log failures
            if isinstance(status, str) and 'query failed' in status.lower():
                try:
                    new_count = fail_counts.get(code, 0) + 1
                    fail_counts[code] = new_count
                    with open(fail_file, 'a', newline='', encoding='utf-8') as ff:
                        fw = csv.writer(ff)
                        if fail_header_needed:
                            fw.writerow(['日期/Date', '查询码/Code', '状态/Status', '备注/Remark', '连续失败次数/Consecutive_Fail_Count'])
                            fail_header_needed = False
                        fw.writerow([datetime.date.today().isoformat(), code, status, err or '', new_count])
                except Exception:
                    pass
            
            # Update statistics
            stats['total'] += 1
            stats['total_attempts'] += attempts_used
            stats['nav_sum'] += float(timings.get('nav_s', 0.0))
            stats['fill_sum'] += float(timings.get('fill_s', 0.0))
            stats['read_sum'] += float(timings.get('read_s', 0.0))
            stats['nav_count'] += 1
            stats['fill_count'] += 1
            stats['read_count'] += 1
            if timings.get('navigated'):
                stats['nav_events'] += 1
            
            failed = isinstance(status, str) and 'query failed' in status.lower()
            if failed:
                stats['fail'] += 1
            else:
                stats['success'] += 1
                if attempts_used > 1:
                    stats['retry_success'] += 1
            if attempts_used > 1:
                stats['retry_needed'] += 1
        
        # CLI output
        if not suppress_cli:
            print(f"{code} -> {status}")
        
        # External callback
        if external_callback:
            try:
                if asyncio.iscoroutinefunction(external_callback):
                    await external_callback(code, status, err, attempts_used, timings)
                else:
                    external_callback(code, status, err, attempts_used, timings)
            except Exception:
                pass

    # Launch browser and workers
    async with async_playwright() as p:
        global _global_browser
        if _global_browser is None or not _global_browser.is_connected():
            _global_browser = await p.chromium.launch(headless=headless)
        browser = _global_browser
        
        try:
            pending = len(row_map)
            if pending <= 0:
                print('Nothing to do: no pending codes / 无需处理：没有待查询的代码')
                return
            
            configured = max(1, int(workers or 1))
            effective_workers = min(configured, pending)
            max_nav = min(6, effective_workers) if effective_workers > 1 else 1
            
            if not suppress_cli:
                print(f"[Init] pending={pending} configured_workers={configured} effective_workers={effective_workers} nav_cap={max_nav}")
            
            nav_sem = asyncio.Semaphore(max_nav)
            tasks = []
            start_ts = asyncio.get_event_loop().time()
            
            for i in range(effective_workers):
                tasks.append(asyncio.create_task(_worker(f"w{i+1}", browser, queue, on_result, retries, nav_sem)))
            
            # Add sentinels
            for _ in range(effective_workers):
                await queue.put(None)
            
            await queue.join()
            for t in tasks:
                await t
            
            # Print summary
            if not suppress_cli:
                try:
                    end_ts = asyncio.get_event_loop().time()
                    elapsed = max(0.0, end_ts - start_ts)
                    total = stats['total'] or 1
                    success = stats['success']
                    fail = stats['fail']
                    retry_needed = stats['retry_needed']
                    retry_success = stats['retry_success']
                    avg_attempts = stats['total_attempts'] / stats['total'] if stats['total'] else 0.0
                    overall_rate = success / total * 100.0
                    retry_success_rate = (retry_success / retry_needed * 100.0) if retry_needed else 0.0
                    tps = (stats['total'] / elapsed) if elapsed > 0 else 0.0
                    
                    print("\n===== Run Summary / 运行总结 =====")
                    print(f"Processed codes / 处理总数: {stats['total']}")
                    print(f"Success / 成功: {success}")
                    print(f"Failed / 失败: {fail}")
                    print(f"Overall success rate / 总体成功率: {overall_rate:.2f}%")
                    print(f"Codes needing retries / 需要重试的代码数: {retry_needed}")
                    print(f"Retry success count / 重试后成功数: {retry_success}")
                    print(f"Retry success rate / 重试成功率: {retry_success_rate:.2f}%")
                    print(f"Average attempts per code / 平均尝试次数: {avg_attempts:.2f}")
                    print(f"Elapsed time / 运行用时: {elapsed:.2f}s")
                    print(f"Throughput / 吞吐量: {tps:.2f} codes/s")
                    
                    nav_avg = stats['nav_sum'] / max(stats['nav_count'], 1)
                    fill_avg = stats['fill_sum'] / max(stats['fill_count'], 1)
                    read_avg = stats['read_sum'] / max(stats['read_count'], 1)
                    nav_avg_if_nav = stats['nav_sum'] / max(stats['nav_events'], 1) if stats['nav_events'] else 0.0
                    
                    print(f"Avg navigation time (overall) / 导航平均时间: {nav_avg:.3f}s")
                    print(f"Avg navigation time (when navigated) / 导航平均时间(发生导航): {nav_avg_if_nav:.3f}s")
                    print(f"Avg fill+submit time / 填表+提交平均: {fill_avg:.3f}s")
                    print(f"Avg result wait time / 读结果平均: {read_avg:.3f}s")
                    print("================================\n")
                except Exception:
                    pass
        finally:
            pass  # Browser cleanup managed by cleanup_browser()


# =============================================================================
# Public API
# =============================================================================

def update_csv_with_status(csv_path: str,
                           headless: bool = True,
                           workers: int = 1,
                           retries: Optional[int] = 3,
                           log_dir: str = 'logs',
                           **_ignored):
    """Sync wrapper for CLI usage.
    
    Args:
        csv_path: input CSV path
        headless: run Chromium headless (default True)
        workers: number of concurrent workers
        retries: per-row retries (default 3)
        log_dir: logs directory for fails CSVs
    """
    r = 3 if retries is None else max(1, int(retries))
    try:
        asyncio.run(_run(csv_path, bool(headless), int(workers or 1), r, log_dir))
    except KeyboardInterrupt:
        print('\nInterrupted by user / 已中断')
    except Exception as e:
        error_msg = str(e).lower()
        if 'socket' not in error_msg and 'connection' not in error_msg and 'closed' not in error_msg:
            print(f'\nError: {e}')


async def query_codes_async(codes: list[str], 
                           headless: bool = True, 
                           workers: int = 1, 
                           retries: int = 3,
                           result_callback=None,
                           suppress_cli: bool = False) -> dict[str, dict]:
    """Third-party async API for monitor/scheduler integration.
    
    Args:
        codes: List of visa application codes to query
        headless: Whether to run headless
        workers: Number of concurrent workers
        retries: Retry count per code
        result_callback: Async callback for real-time results
        suppress_cli: Suppress CLI output
    
    Returns:
        Dict mapping code to result dict with status, error, attempts, timings
    """
    if not codes:
        return {}
    
    import tempfile
    
    # Create temp CSV to leverage existing _run infrastructure
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as f:
        temp_csv_path = f.name
        writer = csv.writer(f)
        writer.writerow(['查询码/Code', '签证状态/Status'])
        for code in codes:
            writer.writerow([code, ''])
    
    results = {}
    results_lock = asyncio.Lock()
    
    async def callback_wrapper(code: str, status: str, err: str, attempts_used: int, timings: dict):
        async with results_lock:
            results[code] = {
                'status': status,
                'error': err,
                'attempts': attempts_used,
                'timings': timings
            }
        
        if result_callback:
            try:
                if asyncio.iscoroutinefunction(result_callback):
                    await result_callback(code, status, err, attempts_used, timings)
                else:
                    result_callback(code, status, err, attempts_used, timings)
            except Exception:
                pass
    
    try:
        await _run(temp_csv_path, headless, workers, retries, 'logs', callback_wrapper, suppress_cli=suppress_cli)
    finally:
        try:
            os.unlink(temp_csv_path)
        except Exception:
            pass
    
    return results


async def cleanup_browser():
    """Clean up global browser instance."""
    global _global_browser
    if _global_browser:
        try:
            await _global_browser.close()
            print("Browser closed successfully")
        except Exception as e:
            print(f"Error closing browser: {e}")
        finally:
            _global_browser = None
            # Also clear active contexts tracking as the browser is gone
            _active_contexts.clear()

async def force_cleanup_all():
    """Forcefully close all tracked contexts and the browser."""
    global _global_browser, _active_contexts
    for ctx in list(_active_contexts):
        try:
            await ctx.close()
        except Exception:
            pass
    _active_contexts.clear()
    await cleanup_browser()


async def _execute_single_query(page, cfg, nav_sem):
    """Internal helper to execute a single ZOV or OAM query."""
    code = cfg.code if hasattr(cfg, 'code') else cfg.get('code')
    query_type = (cfg.query_type if hasattr(cfg, 'query_type') else cfg.get('query_type', 'zov')).lower()
    
    if query_type == 'oam':
        oam_cfg = {
            'serial': cfg.oam_serial if hasattr(cfg, 'oam_serial') else cfg.get('oam_serial'),
            'suffix': cfg.oam_suffix if hasattr(cfg, 'oam_suffix') else cfg.get('oam_suffix'),
            'type': cfg.oam_type if hasattr(cfg, 'oam_type') else cfg.get('oam_type'),
            'year': cfg.oam_year if hasattr(cfg, 'oam_year') else cfg.get('oam_year')
        }
        return await _process_oam(page, oam_cfg, nav_sem)
    return await _process_one(page, code, nav_sem)


async def query_configs_async(configs: list,
                              headless: bool = True,
                              workers: int = 1,
                              retries: int = 3,
                              result_callback=None,
                              suppress_cli: bool = False) -> dict[str, dict]:
    """Unified query API that handles both ZOV and OAM query types.
    
    This is the preferred API for scheduler integration as it supports
    both query types via CodeConfig objects.
    
    Args:
        configs: List of CodeConfig objects (or dicts with matching keys)
        headless: Whether to run headless
        workers: Number of concurrent workers
        retries: Retry count per code
        result_callback: Async callback for real-time results
        suppress_cli: Suppress CLI output
    
    Returns:
        Dict mapping code to result dict with status, error, attempts, timings
    """
async def query_configs_async(configs: list,
                               headless: bool = True,
                               workers: int = 1,
                               retries: int = 3,
                               result_callback=None,
                               suppress_cli: bool = False) -> dict[str, dict]:
    """Unified query API that handles both ZOV and OAM query types."""
    if not configs: return {}
    
    from playwright.async_api import async_playwright
    results = {}
    results_lock = asyncio.Lock()
    
    async def on_result(code, status, err, attempts, timings):
        async with results_lock:
            results[code] = {'status': status, 'error': err, 'attempts': attempts, 'timings': timings}
        if result_callback:
            try:
                if asyncio.iscoroutinefunction(result_callback):
                    await result_callback(code, status, err, attempts, timings)
                else:
                    result_callback(code, status, err, attempts, timings)
            except Exception: pass

    async with async_playwright() as p:
        global _global_browser
        if _global_browser is None or not _global_browser.is_connected():
            _global_browser = await p.chromium.launch(headless=headless)
        
        context = await _create_browser_context(_global_browser)
        page = await context.new_page()
        page.set_default_timeout(15000)
        
        try:
            nav_sem = asyncio.Semaphore(min(6, workers))
            await _ensure_ready(page, nav_sem)
            
            for cfg in configs:
                code = cfg.code if hasattr(cfg, 'code') else cfg.get('code')
                status, err, timings = 'Query Failed/查询失败', '', {}
                
                try:
                    status, timings = await _execute_single_query(page, cfg, nav_sem)
                except Exception as e:
                    err = str(e)
                
                await on_result(code, status, err, 1, timings)
        finally:
            await context.close()
            _active_contexts.discard(context)
            
    return results


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == '__main__':
    import argparse
    
    def _parse_bool(val, default_true=True):
        if val is None:
            return default_true
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ('1', 'true', 't', 'yes', 'y', 'on'):
            return True
        if s in ('0', 'false', 'f', 'no', 'n', 'off'):
            return False
        return default_true
    
    p = argparse.ArgumentParser(description='CZ visa checker (Playwright-only) / 捷克签证查询')
    p.add_argument('--i', default='query_codes.csv', help='CSV input path / CSV 文件路径')
    p.add_argument('--headless', nargs='?', const='true', default=None, metavar='[BOOL]',
                   help='Headless (default True). Use "--headless False" to show UI')
    p.add_argument('--workers', type=int, default=1, help='Concurrent workers / 并发 worker 数')
    p.add_argument('--retries', type=int, default=3, help='Retries per row / 每条重试次数')
    args = p.parse_args()

    headless_val = _parse_bool(args.headless, default_true=True)
    update_csv_with_status(args.i, headless=headless_val, workers=args.workers, retries=args.retries)
