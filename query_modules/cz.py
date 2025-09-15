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
        return 'Unknown / 未知'
    low = text.strip().lower()
    if 'not found' in low:
        return 'Not Found / 未找到'
    if 'still' in low and 'proceedings' in low:
        return 'Proceedings / 审理中'
    if 'granted' in low or 'approved' in low or 'for information on how to proceed' in low:
        return 'Granted / 已通过'
    if 'proceedings' in low:
        # some rare messages use the word but may indicate closure — keep as proceedings fallback
        return 'Rejected/Closed / 被拒绝/已关闭'
    return 'Unknown Status / 未知状态'+f"(status_text/状态文本: {text})"


async def _process_one(page, code: str, nav_sem: asyncio.Semaphore | None = None) -> str:
    # Navigate
    if nav_sem is None:
        await page.goto(IPC_URL, wait_until='domcontentloaded', timeout=20000)
    else:
        async with nav_sem:
            await page.goto(IPC_URL, wait_until='domcontentloaded', timeout=20000)

    # Try to hide cookie/overlay elements quickly (best-effort, no exceptions)
    try:
        await page.add_script_tag(content="""
        (function(){
          var sels=['.cookies__wrapper','.cookie-consent','.gdpr-banner','.modal__window','.modal-backdrop','[data-cookie]','[data-cookies-edit]'];
          sels.forEach(function(s){ document.querySelectorAll(s).forEach(function(e){ try{ e.style.display='none'; e.style.pointerEvents='none'; e.style.zIndex='-9999'; }catch(ex){} }); });
          document.querySelectorAll('button.button__outline,button.button__close').forEach(function(b){ try{ b.click(); }catch(e){} });
        })();
        """)
    except Exception:
        pass

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

    # Set value via fill (retries minimal)
    await input_el.click()
    await input_el.fill('')
    await input_el.type(code, delay=10)

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

    # Wait for a result text using several candidates; accept first non-empty
    selectors = [
        '.alert__content', '.alert', '.result', '.status', '.ipc-result', '.application-status', '[role=alert]', '[aria-live]'
    ]
    text = ''
    end = asyncio.get_event_loop().time() + 15.0
    while asyncio.get_event_loop().time() < end and not text:
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

    return _normalize_status(text)


async def _worker(name: str, browser, queue: asyncio.Queue, result_cb, retries: int, nav_sem: asyncio.Semaphore):
    # Create context with lighter resources and sane timeouts
    context = await browser.new_context()
    # Block heavy resources to reduce load
    try:
        await context.route("**/*", lambda route: route.abort() if route.request.resource_type in {"image", "font"} else route.continue_())
    except Exception:
        pass
    page = await context.new_page()
    try:
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(20000)
    except Exception:
        pass
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            idx, code = item
            status = 'Query Failed / 查询失败'
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
                                await context.route("**/*", lambda route: route.abort() if route.request.resource_type in {"image", "font"} else route.continue_())
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

                    status = await _process_one(page, code, nav_sem)
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
                                await context.route("**/*", lambda route: route.abort() if route.request.resource_type in {"image", "font"} else route.continue_())
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
                        status = 'Query Failed / 查询失败'
            await result_cb(idx, code, status, err, attempts_used)
            queue.task_done()
    finally:
        try:
            await context.close()
        except Exception:
            pass


async def _run(csv_path: str, headless: bool, workers: int, retries: int, log_dir: str):
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
        # 逻辑调整：如果状态为空或者为 Query Failed / 查询失败，则视为“未完成”需要重新查询。
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

    async def on_result(idx: int, code: str, status: str, err: str, attempts_used: int):
        nonlocal fail_header_needed
        async with rows_lock:
            rows[idx][status_idx] = status
            # flush CSV
            try:
                with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
                    w = csv.writer(wf)
                    w.writerow(header)
                    w.writerows(rows[1:])
            except Exception:
                pass
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
            failed = isinstance(status, str) and 'query failed' in status.lower()
            if failed:
                stats['fail'] += 1
            else:
                stats['success'] += 1
                if attempts_used > 1:
                    stats['retry_success'] += 1
            if attempts_used > 1:
                stats['retry_needed'] += 1
        print(f"{code} -> {status}")

    # Launch browser and workers
    async with async_playwright() as p:
        # Ensure Chromium is available; if missing the user should run: python -m playwright install chromium
        browser = await p.chromium.launch(headless=headless)
        try:
            workers = max(1, int(workers or 1))
            # Limit simultaneous navigations to reduce server resets
            max_nav = min(6, workers) if workers > 1 else 1
            nav_sem = asyncio.Semaphore(max_nav)
            tasks = []
            for i in range(workers):
                tasks.append(asyncio.create_task(_worker(f"w{i+1}", browser, queue, on_result, retries, nav_sem)))
            # Add sentinels
            for _ in range(workers):
                await queue.put(None)
            await queue.join()
            for t in tasks:
                await t
            # 输出总结统计
            try:
                total = stats['total'] or 1  # avoid zero division
                success = stats['success']
                fail = stats['fail']
                retry_needed = stats['retry_needed']
                retry_success = stats['retry_success']
                avg_attempts = stats['total_attempts'] / stats['total'] if stats['total'] else 0.0
                overall_rate = success / total * 100.0
                retry_success_rate = (retry_success / retry_needed * 100.0) if retry_needed else 0.0
                print("\n===== Run Summary / 运行总结 =====")
                print(f"Processed codes / 处理总数: {stats['total']}")
                print(f"Success (final status not failed) / 成功: {success}")
                print(f"Failed (still Query Failed) / 失败: {fail}")
                print(f"Overall success rate / 总体成功率: {overall_rate:.2f}%")
                print(f"Codes needing retries (>1 attempts) / 需要重试的代码数: {retry_needed}")
                print(f"Retry success count / 重试后成功数: {retry_success}")
                print(f"Retry success rate / 重试成功率: {retry_success_rate:.2f}%")
                print(f"Average attempts per code / 平均尝试次数: {avg_attempts:.2f}")
                print("================================\n")
            except Exception:
                pass
        finally:
            try:
                await browser.close()
            except Exception:
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
