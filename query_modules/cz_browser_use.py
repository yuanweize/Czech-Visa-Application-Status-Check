"""Experimental Browser-Use (Playwright-based) implementation for Czech visa status queries.

This module mirrors the public API of `query_modules.cz.update_csv_with_status` so that
we can switch between Selenium and Browser-Use backends.

Status: EXPERIMENTAL (feature/browser-use branch only)

Key differences vs Selenium version:
- Uses `browser_use` Agent + Playwright instead of raw Selenium WebDriver.
- Navigates and extracts result text with a simpler deterministic (non-LLM) flow to avoid token costs.
- Retains CSV update semantics (incremental writes, bilingual messages).

We avoid invoking an LLM for now: we directly drive the page with Playwright.
If later we want autonomous navigation or resilient DOM adaptation, we can introduce an Agent.

Prerequisites:
  pip install browser-use
  playwright install chromium   (browser-use should auto-manage, but explicitly run if needed)

Limitations:
- Playwright headless option is honored.
- Concurrency: simple async batching; not as optimized as Selenium thread pool yet.

"""
from __future__ import annotations

import asyncio
import csv
import os
import random
import time
from typing import List

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Target URL
CHECK_URL = 'https://ipc.gov.cz/en/status-of-your-application/'

RESULT_SELECTORS = [
    '.alert__content', '.alert', '.result', '.status', '.ipc-result', '.application-status', '[role=alert]', '[aria-live]'
]

# Mapping heuristics (lowercased text)
STATUS_MAP = [
    (lambda t: 'not found' in t, 'Not Found / 未找到'),
    (lambda t: ('still' in t and 'proceedings' in t), 'Proceedings / 审理中'),
    (lambda t: any(k in t for k in ['for information on how to proceed', 'granted', 'approved']), 'Granted / 已通过'),
    (lambda t: 'proceedings' in t, 'Rejected/Closed / 被拒绝/已关闭'),
]

async def _query_single(page, code: str, max_attempts: int = 3) -> str:
    for attempt in range(1, max_attempts + 1):
        try:
            await page.goto(CHECK_URL, wait_until='domcontentloaded')
            # Dismiss known overlays (cookie banners) heuristically
            try:
                await page.add_init_script("""
                    (()=>{
                      const sels=['.cookies__wrapper','.cookie-consent','.gdpr-banner','.modal__window','.modal-backdrop'];
                      for (const s of sels){ document.querySelectorAll(s).forEach(e=>{ e.style.display='none'; e.style.visibility='hidden'; e.style.pointerEvents='none';}); }
                    })();
                """)
            except Exception:
                pass
            try:
                await page.fill('input[name="visaApplicationNumber"]', code, timeout=4000)
            except Exception:
                # fallback: wait then retry
                await page.wait_for_selector('input[name="visaApplicationNumber"]', timeout=8000)
                await page.fill('input[name="visaApplicationNumber"]', code)

            # Submit form: try explicit button then fallback pressing Enter
            try:
                btn = await page.query_selector('button[type="submit"]')
                if btn:
                    await btn.click()
                else:
                    await page.press('input[name="visaApplicationNumber"]', 'Enter')
            except Exception:
                try:
                    await page.press('input[name="visaApplicationNumber"]', 'Enter')
                except Exception:
                    pass

            # Wait for any result selectors
            text_found = ''
            end = time.time() + 6
            while time.time() < end:
                for sel in RESULT_SELECTORS:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            raw = (await el.inner_text()).strip()
                            if raw:
                                text_found = raw
                                break
                    except Exception:
                        continue
                if text_found:
                    break
                await asyncio.sleep(0.25)
            if not text_found:
                raise PlaywrightTimeoutError('No result text')
            norm = text_found.lower()
            for pred, label in STATUS_MAP:
                try:
                    if pred(norm):
                        return label
                except Exception:
                    continue
            return 'Unknown Status / 未知状态' + f'(status_text/状态文本: {norm})'
        except Exception as e:
            if attempt < max_attempts:
                await asyncio.sleep(0.6 + attempt * 0.4 + random.uniform(0, 0.4))
                continue
            return 'Query Failed / 查询失败' + f'(error: {e})'

async def _process_codes(codes: List[str], max_attempts: int, headless: bool) -> List[str]:
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(viewport={'width': 1200, 'height': 800})
        page = await context.new_page()
        for code in codes:
            status = await _query_single(page, code, max_attempts=max_attempts)
            results.append(status)
        await context.close()
        await browser.close()
    return results

def update_csv_with_status(csv_path: str, code_col='查询码/Code', status_col='签证状态/Status', headless=True, retries=None, log_dir='logs', workers: int = 1, per_query_delay=0.5, jitter=0.5):
    """Public entry point mirroring Selenium signature minus driver_path.

    Currently executes sequentially (workers ignored) to keep implementation minimal.
    """
    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found / [错误] 未找到CSV文件: {csv_path}")
        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if not rows:
        print('[Error] Empty CSV / 空CSV')
        return
    header = rows[0]

    def find_col(name):
        if name in header:
            return header.index(name)
        nl = name.lower()
        for i, h in enumerate(header):
            if h.lower() == nl:
                return i
        for i, h in enumerate(header):
            if nl in h.lower():
                return i
        return None

    code_idx = find_col(code_col)
    if code_idx is None:
        print('Code column not found / 未找到查询码列')
        return
    status_idx = find_col(status_col)
    if status_idx is None:
        header.append(status_col)
        status_idx = len(header) - 1

    pending_codes = []
    row_refs = []
    for r in rows[1:]:
        while len(r) < len(header):
            r.append('')
        if not r[code_idx]:
            continue
        # skip if already has status
        if r[status_idx] and str(r[status_idx]).strip():
            continue
        pending_codes.append(r[code_idx])
        row_refs.append(r)
    if not pending_codes:
        print('No pending codes / 没有需要查询的编码')
        return
    max_attempts = retries if (retries and retries > 0) else 3

    # Run queries (sequential for now)
    statuses = asyncio.run(_process_codes(pending_codes, max_attempts=max_attempts, headless=headless))
    for code, row, status in zip(pending_codes, row_refs, statuses):
        row[status_idx] = status
        print(f"{code} -> {status}")
        # flush after each code
        with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
            w = csv.writer(wf)
            w.writerow(header)
            w.writerows(rows[1:])
        try:
            d = float(per_query_delay) if per_query_delay is not None else 0.5
            j = float(jitter) if jitter is not None else 0.5
            time.sleep(max(0.0, d + random.uniform(0, j)))
        except Exception:
            pass
    print('Done (browser-use experimental) / 完成（browser-use 实验版）')

if __name__ == '__main__':
    # simple manual test
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='query_codes.csv')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--retries', type=int, default=3)
    args = ap.parse_args()
    update_csv_with_status(args.csv, headless=args.headless, retries=args.retries)
