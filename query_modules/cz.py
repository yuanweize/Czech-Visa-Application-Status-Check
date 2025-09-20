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


def _find_col(header: list[str], name: str) -> Optional[int]:
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
        # some rare messages use the word but may indicate closure — keep as proceedings fallback
        return 'Rejected/被拒绝'
    return 'Unknown Status/未知状态'+f"(status_text/状态文本: {text})"


async def _ensure_ready(page, nav_sem: asyncio.Semaphore | None = None) -> bool:
    """Ensure the input is present; only navigate when necessary.
    Returns True if a navigation was performed, else False.
    """
    try:
        await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=3000, state='attached')
        return False
    except Exception:
        pass
    # Navigate only if input not available
    if nav_sem is None:
        await page.goto(IPC_URL, wait_until='domcontentloaded', timeout=20000)
    else:
        async with nav_sem:
            await page.goto(IPC_URL, wait_until='domcontentloaded', timeout=20000)
    # wait once more for input
    await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=15000, state='attached')
    return True


async def _maybe_hide_overlays(page):
    """Hide cookie/overlay elements once per page lifecycle to reduce overhead."""
    try:
        already = await page.evaluate("(() => window.__overlay_done === true)()")
    except Exception:
        already = False
    if already:
        return
    try:
        await page.add_script_tag(content="""
        (function(){
          try { window.__overlay_done = true; } catch (e) {}
          var sels=['.cookies__wrapper','.cookie-consent','.gdpr-banner','.modal__window','.modal-backdrop','[data-cookie]','[data-cookies-edit]'];
          sels.forEach(function(s){ document.querySelectorAll(s).forEach(function(e){ try{ e.style.display='none'; e.style.pointerEvents='none'; e.style.zIndex='-9999'; }catch(ex){} }); });
          try { document.querySelectorAll('button.button__outline,button.button__close').forEach(function(b){ try{ b.click(); }catch(e){} }); } catch(e){}
        })();
        """)
    except Exception:
        try:
            await page.evaluate("document.querySelectorAll('.cookies__wrapper,.modal__window').forEach(e=>{try{e.style.display='none';e.style.pointerEvents='none';}catch(_){}})")
        except Exception:
            pass


async def _process_one(page, code: str, nav_sem: asyncio.Semaphore | None = None):
    # Ensure page ready; avoid navigating for every single code
    loop = asyncio.get_event_loop()
    t_nav0 = loop.time()
    did_nav = await _ensure_ready(page, nav_sem)
    t_nav1 = loop.time()

    # Hide overlays once per page lifecycle
    await _maybe_hide_overlays(page)

    # Input and submit
    try:
        input_el = await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=15000)
    except Exception:
        # try once more after a quick JS overlay clear
        try:
            await page.evaluate("document.querySelectorAll('.cookies__wrapper,.modal__window').forEach(e=>{e.style.display='none'})")
        except Exception:
            pass
        input_el = await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=15000)

    # Set value via fill (retries minimal) + light jitter to desync bursts
    t_fill0 = loop.time()
    # jitter 30~120ms
    try:
        await asyncio.sleep(random.uniform(0.03, 0.12))
    except Exception:
        pass
    await input_el.fill(code)

    # Submit: prefer button[type=submit]
    btn = await page.query_selector("button[type='submit']")
    if btn is None:
        # try text contains
        btn = await page.query_selector("xpath=//button[contains(., 'Validate') or contains(., 'validate') or contains(., 'ověřit')]")
    if btn is not None:
        try:
            await btn.click()
        except Exception:
            try:
                await page.evaluate("arguments[0].click();", btn)
            except Exception:
                pass
    t_fill1 = loop.time()

    # Wait for a result text using several candidates; accept first non-empty
    selectors = [
        '.alert__content', '.alert', '.result', '.status', '.ipc-result', '.application-status', '[role=alert]', '[aria-live]'
    ]
    text = ''
    t_read0 = loop.time()
    end = loop.time() + 15.0
    while loop.time() < end and not text:
        for s in selectors:
            try:
                el = await page.query_selector(s)
            except Exception:
                el = None
            if el:
                try:
                    t = (await el.inner_text()) or ''
                except Exception:
                    try:
                        t = (await el.text_content()) or ''
                    except Exception:
                        t = ''
                if t and t.strip():
                    text = t.strip()
                    break
        if not text:
            # page-wide quick scan via JS
            try:
                js = "var sels=arguments[0]; for (var i=0;i<sels.length;i++){var nodes=document.querySelectorAll(sels[i]); for (var j=0;j<nodes.length;j++){ try{ var t=(nodes[j].innerText||nodes[j].textContent||'').trim(); if(t) return t; }catch(e){} } } return '';"
                t = await page.evaluate(js, selectors)
                if t and str(t).strip():
                    text = str(t).strip()
                    break
            except Exception:
                pass
            await asyncio.sleep(0.2)

    if not text:
        # treat as transient timeout; caller will decide retries
        raise TimeoutError('No result text found')
    t_read1 = loop.time()

    timings = {
        'nav_s': max(0.0, t_nav1 - t_nav0),
        'fill_s': max(0.0, t_fill1 - t_fill0),
        'read_s': max(0.0, t_read1 - t_read0),
        'navigated': bool(did_nav),
    }
    return _normalize_status(text), timings


async def _worker(name: str, browser, queue: asyncio.Queue, result_cb, retries: int, nav_sem: asyncio.Semaphore):
    # Create context with lighter resources and sane timeouts
    context = await browser.new_context()
    # Block heavy resources to reduce load (await continue/abort correctly)
    async def _route_handler(route):
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
        await context.route("**/*", _route_handler)
    except Exception:
        pass
    page = await context.new_page()
    try:
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(20000)
    except Exception:
        pass
    # Pre-warm: navigate and hide overlays once
    try:
        await _ensure_ready(page, nav_sem)
        await _maybe_hide_overlays(page)
    except Exception:
        pass
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            idx, code = item
            status = 'Query Failed/查询失败'
            err = ''
            attempts_used = 0
            for attempt in range(1, retries + 1):
                attempts_used = attempt
                try:
                    # In case page was closed between attempts, recreate it
                    try:
                        if page.is_closed():
                            try:
                                await context.close()
                            except Exception:
                                pass
                            context = await browser.new_context()
                            try:
                                await context.route("**/*", _route_handler)
                            except Exception:
                                pass
                            page = await context.new_page()
                            try:
                                page.set_default_timeout(15000)
                                page.set_default_navigation_timeout(20000)
                            except Exception:
                                pass
                    except Exception:
                        pass

                    status, timings = await _process_one(page, code, nav_sem)
                    err = ''
                    break
                except Exception as e:
                    err = str(e)
                    # If page/context/browser was closed or transport disconnected, try to recreate context/page and retry
                    closed_signals = (
                        'has been closed',
                        'Target page, context or browser has been closed',
                        'Connection closed while reading from the driver',
                        'browser has been closed',
                    )
                    if any(sig.lower() in err.lower() for sig in closed_signals):
                        try:
                            if not page.is_closed():
                                await page.close()
                        except Exception:
                            pass
                        try:
                            await context.close()
                        except Exception:
                            pass
                        try:
                            context = await browser.new_context()
                            try:
                                await context.route("**/*", _route_handler)
                            except Exception:
                                pass
                            page = await context.new_page()
                            try:
                                page.set_default_timeout(15000)
                                page.set_default_navigation_timeout(20000)
                            except Exception:
                                pass
                        except Exception:
                            # If even creating a new context fails, likely browser is down; propagate
                            pass
                    if attempt < retries:
                        await asyncio.sleep(1.0 + 0.5 * attempt)
                    else:
                        status = 'Query Failed/查询失败'
            # If an exception path occurred, timings may not exist
            try:
                _t = timings
            except NameError:
                _t = {'nav_s': 0.0, 'fill_s': 0.0, 'read_s': 0.0, 'navigated': False}
            await result_cb(idx, code, status, err, attempts_used, _t)
            queue.task_done()
    finally:
        try:
            await context.close()
        except Exception:
            pass


async def _run(csv_path: str, headless: bool, workers: int, retries: int, log_dir: str, external_callback=None, suppress_cli: bool = False):
    from playwright.async_api import async_playwright

    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found / [错误] 未找到CSV文件: {csv_path}")
        return

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

    # Prepare queue
    queue: asyncio.Queue = asyncio.Queue()
    row_map: dict[str, int] = {}
    for i, row in enumerate(rows[1:], 1):
        while len(row) < len(header):
            row.append('')
        code = row[code_idx]
        # 逻辑调整：如果状态为空或者为 Query Failed/查询失败，则视为“未完成”需要重新查询。
        # 之前实现：只要非空就跳过，导致之前的失败记录无法重试。
        status_cell = str(row[status_idx]).strip() if row[status_idx] else ''
        if status_cell and 'query failed' not in status_cell.lower():
            # 已有一个非失败的最终状态（如 Not Found / Proceedings / Granted 等），跳过
            continue
        row_map[code] = i
        await queue.put((i, code))

    # Result callback with immediate CSV flush and failure logging
    rows_lock = asyncio.Lock()
    fails_dir = os.path.join(os.getcwd(), log_dir, 'fails')
    os.makedirs(fails_dir, exist_ok=True)
    fail_file = os.path.join(fails_dir, f"{datetime.date.today().isoformat()}_fails.csv")
    fail_header_needed = not os.path.exists(fail_file)

    # 读取已有失败文件，构建累积失败计数 (code -> count)
    fail_counts: dict[str, int] = {}
    if os.path.exists(fail_file):
        try:
            with open(fail_file, 'r', encoding='utf-8') as rf:
                cr = csv.reader(rf)
                header_line = True
                for r in cr:
                    if header_line:
                        header_line = False
                        continue
                    if not r:
                        continue
                    if len(r) < 2:
                        continue
                    c = r[1].strip()
                    if not c or c == '查询码/Code':
                        continue
                    fail_counts[c] = fail_counts.get(c, 0) + 1
        except Exception:
            pass

    # 统计信息
    stats = {
        'total': 0,
        'success': 0,
        'fail': 0,
        'retry_needed': 0,
        'retry_success': 0,
        'total_attempts': 0,
    }

    async def on_result(idx: int, code: str, status: str, err: str, attempts_used: int, timings: dict):
        nonlocal fail_header_needed
        async with rows_lock:
            rows[idx][status_idx] = status
            # flush CSV
            try:
                # Write to a temp file then replace to avoid partial writes
                tmp_path = csv_path + '.tmp'
                with open(tmp_path, 'w', newline='', encoding='utf-8') as wf:
                    w = csv.writer(wf)
                    w.writerow(header)
                    w.writerows(rows[1:])
                try:
                    os.replace(tmp_path, csv_path)
                except Exception:
                    # Fallback to direct write if replace fails (e.g., on locked FS)
                    with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
                        w = csv.writer(wf)
                        w.writerow(header)
                        w.writerows(rows[1:])
            except Exception as e:
                print(f"[Warning] Failed to write CSV '{csv_path}': {e}")
            # append to fails
            try:
                if isinstance(status, str) and 'query failed' in status.lower():
                    # 更新连续失败次数
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
            # 更新统计
            stats['total'] += 1
            stats['total_attempts'] += attempts_used
            # phase timings
            try:
                stats.setdefault('nav_sum', 0.0)
                stats.setdefault('fill_sum', 0.0)
                stats.setdefault('read_sum', 0.0)
                stats.setdefault('nav_count', 0)
                stats.setdefault('fill_count', 0)
                stats.setdefault('read_count', 0)
                stats.setdefault('nav_events', 0)
                stats['nav_sum'] += float(timings.get('nav_s', 0.0) or 0.0)
                stats['fill_sum'] += float(timings.get('fill_s', 0.0) or 0.0)
                stats['read_sum'] += float(timings.get('read_s', 0.0) or 0.0)
                stats['nav_count'] += 1
                stats['fill_count'] += 1
                stats['read_count'] += 1
                if timings.get('navigated'):
                    stats['nav_events'] += 1
            except Exception:
                pass
            failed = isinstance(status, str) and 'query failed' in status.lower()
            if failed:
                stats['fail'] += 1
            else:
                stats['success'] += 1
                if attempts_used > 1:
                    stats['retry_success'] += 1
            if attempts_used > 1:
                stats['retry_needed'] += 1
        
        # CLI输出（可抑制，用于Monitor模式去重）
        if not suppress_cli:
            print(f"{code} -> {status}")
        
        # 外部回调 - 新增功能，不影响CLI
        if external_callback:
            try:
                if asyncio.iscoroutinefunction(external_callback):
                    await external_callback(code, status, err, attempts_used, timings)
                else:
                    external_callback(code, status, err, attempts_used, timings)
            except Exception:
                # 外部回调失败不影响主流程
                pass

    # Launch browser and workers
    async with async_playwright() as p:
    # Ensure Chromium is available; if missing the user should run: python -m playwright install chromium
        global _global_browser
        if _global_browser is None or _global_browser.is_connected() == False:
            _global_browser = await p.chromium.launch(headless=headless)
        browser = _global_browser
        try:
            # Determine effective worker count: don't spawn more than pending codes
            pending = len(row_map)
            if pending <= 0:
                print('Nothing to do: no pending codes (all have non-failed statuses) / 无需处理：没有待查询的代码（均为非失败状态）')
                return
            configured = max(1, int(workers or 1))
            effective_workers = min(configured, pending)
            # Limit simultaneous navigations to reduce server pressure (cap=6)
            max_nav = min(6, effective_workers) if effective_workers > 1 else 1
            if not suppress_cli:
                print(f"[Init] pending={pending} configured_workers={configured} effective_workers={effective_workers} nav_cap={max_nav}")
            nav_sem = asyncio.Semaphore(max_nav)
            tasks = []
            # Start timing for worker phase
            start_ts = asyncio.get_event_loop().time()
            for i in range(effective_workers):
                tasks.append(asyncio.create_task(_worker(f"w{i+1}", browser, queue, on_result, retries, nav_sem)))
            # Add sentinels
            for _ in range(effective_workers):
                await queue.put(None)
            await queue.join()
            for t in tasks:
                await t
            # 输出总结统计
            try:
                end_ts = asyncio.get_event_loop().time()
                elapsed = max(0.0, end_ts - start_ts)
                total = stats['total'] or 1  # avoid zero division
                success = stats['success']
                fail = stats['fail']
                retry_needed = stats['retry_needed']
                retry_success = stats['retry_success']
                avg_attempts = stats['total_attempts'] / stats['total'] if stats['total'] else 0.0
                overall_rate = success / total * 100.0
                retry_success_rate = (retry_success / retry_needed * 100.0) if retry_needed else 0.0
                tps = (stats['total'] / elapsed) if elapsed > 0 else 0.0
                if not suppress_cli:
                    print("\n===== Run Summary / 运行总结 =====")
                    print(f"Processed codes / 处理总数: {stats['total']}")
                    print(f"Success (final status not failed) / 成功: {success}")
                    print(f"Failed (still Query Failed) / 失败: {fail}")
                    print(f"Overall success rate / 总体成功率: {overall_rate:.2f}%")
                    print(f"Codes needing retries (>1 attempts) / 需要重试的代码数: {retry_needed}")
                    print(f"Retry success count / 重试后成功数: {retry_success}")
                    print(f"Retry success rate / 重试成功率: {retry_success_rate:.2f}%")
                    print(f"Average attempts per code / 平均尝试次数: {avg_attempts:.2f}")
                    print(f"Elapsed time / 运行用时: {elapsed:.2f}s")
                    print(f"Throughput / 吞吐量: {tps:.2f} codes/s")
                    # Phase timing summary
                    nav_avg_overall = (stats.get('nav_sum', 0.0) / stats.get('nav_count', 1))
                    fill_avg = (stats.get('fill_sum', 0.0) / stats.get('fill_count', 1))
                    read_avg = (stats.get('read_sum', 0.0) / stats.get('read_count', 1))
                    nav_avg_if_nav = (stats.get('nav_sum', 0.0) / stats.get('nav_events', 1)) if stats.get('nav_events', 0) else 0.0
                    print(f"Avg navigation time (overall) / 导航平均时间(总体): {nav_avg_overall:.3f}s")
                    print(f"Avg navigation time (when navigated) / 导航平均时间(发生导航): {nav_avg_if_nav:.3f}s (count={stats.get('nav_events', 0)})")
                    print(f"Avg fill+submit time / 填表+提交平均: {fill_avg:.3f}s")
                    print(f"Avg result wait time / 读结果平均: {read_avg:.3f}s")
                    print("================================\n")
            except Exception:
                pass
        finally:
            # 不再自动关闭浏览器 - 由外部调用cleanup_browser()管理
            # Browser will be closed by external cleanup_browser() call
            pass


def update_csv_with_status(csv_path: str,
                           headless: bool = True,
                           workers: int = 1,
                           retries: Optional[int] = 3,
                           log_dir: str = 'logs',
                           **_ignored):
    """Sync wrapper used by CLI. Only essential args exposed.

    - csv_path: input CSV path
    - headless: run Chromium headless (default True). Use False to show UI.
    - workers: number of concurrent workers (pages) sharing one browser
    - retries: per-row retries (default 3)
    - log_dir: logs directory (for fails CSVs)
    """
    r = 3 if retries is None else max(1, int(retries))
    try:
        asyncio.run(_run(csv_path, bool(headless), int(workers or 1), r, log_dir))
    except KeyboardInterrupt:
        print('\nInterrupted by user / 已中断')
    except Exception as e:
        # 完全静默socket相关的异常，避免噪音
        error_msg = str(e).lower()
        if 'socket' not in error_msg and 'connection' not in error_msg and 'closed' not in error_msg:
            print(f'\nError: {e}')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='CZ visa checker (Playwright-only) / 捷克签证查询（仅 Playwright）')
    p.add_argument('--i', default='query_codes.csv', help='CSV input path / CSV 文件路径')
    p.add_argument('--headless', nargs='?', const='true', default=None, metavar='[BOOL]',
                   help='Headless (default True). Use "--headless False" to show UI / 无头(默认 True)，使用 "--headless False" 显示界面')
    p.add_argument('--workers', type=int, default=1, help='Concurrent workers (pages) / 并发 worker 数')
    p.add_argument('--retries', type=int, default=3, help='Retries per row / 每条重试次数')
    args = p.parse_args()

    def _parse_bool(val, default_true=True):
        if val is None:
            return True if default_true else False
        if isinstance(val, bool):
            return val
        s = str(val).strip().lower()
        if s in ('1','true','t','yes','y','on'): return True
        if s in ('0','false','f','no','n','off'): return False
        return True if default_true else False

    headless_val = _parse_bool(args.headless, default_true=True)
    update_csv_with_status(args.i, headless=headless_val, workers=args.workers, retries=args.retries)


# --- 第三方调用接口 - 专为Monitor等调用者设计 ---
async def query_codes_async(codes: list[str], 
                           headless: bool = True, 
                           workers: int = 1, 
                           retries: int = 3,
                           result_callback=None,
                           suppress_cli: bool = False) -> dict[str, dict]:
    """
    第三方调用接口 - 专为Monitor等调用者设计
    
    直接传递代码列表，复用现有_run函数的完整实现
    通过临时CSV文件桥接，实现真正的实时回调
    
    Args:
        codes: 查询代码列表  
        headless: 是否无头模式
        workers: worker数量
        retries: 重试次数
        result_callback: 实时结果回调 async def callback(code, status, error, attempts, timings)
    
    Returns:
        dict: {code: {'status': str, 'error': str, 'attempts': int, 'timings': dict}}
    """
    if not codes:
        return {}
    
    import tempfile
    
    # 创建临时CSV - 让现有_run函数处理所有浏览器管理
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8', newline='') as f:
        temp_csv_path = f.name
        writer = csv.writer(f)
        writer.writerow(['查询码/Code', '签证状态/Status'])
        for code in codes:
            writer.writerow([code, ''])
    
    # 结果收集
    results = {}
    results_lock = asyncio.Lock()
    
    # 实时回调包装器 - 收集结果并立即通知调用者
    async def external_callback_wrapper(code: str, status: str, err: str, attempts_used: int, timings: dict):
        """外部回调包装器 - 实现真正的实时通知"""
        async with results_lock:
            results[code] = {
                'status': status,
                'error': err,
                'attempts': attempts_used,
                'timings': timings
            }
        
        # 立即调用外部回调，实现实时通知
        if result_callback:
            try:
                if asyncio.iscoroutinefunction(result_callback):
                    await result_callback(code, status, err, attempts_used, timings)
                else:
                    result_callback(code, status, err, attempts_used, timings)
            except Exception:
                pass  # 回调失败不影响主流程
    
    try:
        # 直接复用现有_run函数 - 完整的浏览器管理架构，支持实时回调
        await _run(temp_csv_path, headless, workers, retries, 'logs', external_callback_wrapper, suppress_cli=suppress_cli)
    finally:
        # 清理临时文件
        try:
            os.unlink(temp_csv_path)
        except Exception:
            pass
    
    return results


# 全局浏览器实例管理
_global_browser = None

async def cleanup_browser():
    """清理全局浏览器实例"""
    global _global_browser
    if _global_browser:
        try:
            await _global_browser.close()
            print("Browser closed successfully")
        except Exception as e:
            print(f"Error closing browser: {e}")
        finally:
            _global_browser = None
