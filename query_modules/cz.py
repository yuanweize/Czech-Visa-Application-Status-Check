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


async def _process_one(page, code: str) -> str:
    # Navigate
    await page.goto(IPC_URL, wait_until='domcontentloaded')

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
        input_el = await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=5000)
    except Exception:
        # try once more after a quick JS overlay clear
        try:
            await page.evaluate("document.querySelectorAll('.cookies__wrapper,.modal__window').forEach(e=>{e.style.display='none'})")
        except Exception:
            pass
        input_el = await page.wait_for_selector("input[name='visaApplicationNumber']", timeout=6000)

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
    end = asyncio.get_event_loop().time() + 8.0
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


async def _worker(name: str, browser, queue: asyncio.Queue, result_cb, retries: int):
    context = await browser.new_context()
    page = await context.new_page()
    try:
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            idx, code = item
            status = 'Query Failed / 查询失败'
            err = ''
            for attempt in range(1, retries + 1):
                try:
                    status = await _process_one(page, code)
                    err = ''
                    break
                except Exception as e:
                    err = str(e)
                    if attempt < retries:
                        await asyncio.sleep(0.8 + 0.2 * attempt)
                    else:
                        status = 'Query Failed / 查询失败'
            await result_cb(idx, code, status, err)
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
        if row[status_idx] and str(row[status_idx]).strip():
            continue
        row_map[code] = i
        await queue.put((i, code))

    # Result callback with immediate CSV flush and failure logging
    rows_lock = asyncio.Lock()
    fails_dir = os.path.join(os.getcwd(), log_dir, 'fails')
    os.makedirs(fails_dir, exist_ok=True)
    fail_file = os.path.join(fails_dir, f"{datetime.date.today().isoformat()}_fails.csv")
    fail_header_needed = not os.path.exists(fail_file)

    async def on_result(idx: int, code: str, status: str, err: str):
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
                    with open(fail_file, 'a', newline='', encoding='utf-8') as ff:
                        fw = csv.writer(ff)
                        if fail_header_needed:
                            fw.writerow(['日期/Date', '查询码/Code', '状态/Status', '备注/Remark'])
                            fail_header_needed = False
                        fw.writerow([datetime.date.today().isoformat(), code, status, err or ''])
            except Exception:
                pass
        print(f"{code} -> {status}")

    # Launch browser and workers
    async with async_playwright() as p:
        # Ensure Chromium is available; if missing the user should run: python -m playwright install chromium
        browser = await p.chromium.launch(headless=headless)
        try:
            workers = max(1, int(workers or 1))
            tasks = []
            for i in range(workers):
                tasks.append(asyncio.create_task(_worker(f"w{i+1}", browser, queue, on_result, retries)))
            # Add sentinels
            for _ in range(workers):
                await queue.put(None)
            await queue.join()
            for t in tasks:
                await t
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
