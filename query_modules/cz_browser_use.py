"""Experimental browser-use (Playwright) implementation for Czech visa status queries.

Refactored to leverage the `browser_use` project instead of invoking Playwright directly.

Goals / 目标:
1. Reuse browser-use's BrowserSession lifecycle (统一的浏览器上下文管理)。
2. Keep deterministic (non-LLM) flow to avoid token cost (暂不调用 LLM, 后续可接入 Agent)。
3. Provide a drop‑in replacement for the Selenium backend public API (`update_csv_with_status`).

Why not an LLM Agent yet? / 为什么暂不使用 LLM Agent?
- Each code query is a short, stable form interaction; deterministic DOM ops are faster & cheaper.
- Later we can wrap a batch into a single Agent task with custom actions if site changes frequently.

Future extension ideas / 后续扩展:
- Optional Agent mode: natural language resilient extraction when selectors fail.
- Custom MCP server actions (通过浏览器自动化工具作为外部工具集成)。

Dependencies / 依赖:
    pip install browser-use playwright
    (First run triggers chromium download automatically.)

Concurrency / 并发:
- Still sequential for now. Can be upgraded to async gather or multi-context pooling.

Status: EXPERIMENTAL (feature/browser-use branch only)
"""
from __future__ import annotations

import asyncio
import csv
import os
import random
import time
from typing import List, Optional

try:
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover
    PlaywrightTimeoutError = Exception  # fallback

try:
    from browser_use import BrowserSession, Agent  # type: ignore
    from browser_use.llm import ChatDeepSeek  # type: ignore
except Exception:  # pragma: no cover
    BrowserSession = None  # handled later
    Agent = None  # type: ignore
    ChatDeepSeek = None  # type: ignore

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

def _prepare_llm_env():
    """Prepare DeepSeek / SiliconFlow environment (DeepSeek-only mode)."""
    # Normalize: prefer dedicated DEEPSEEK_API_KEY, fallback to SILICONFLOW_API_KEY
    if 'DEEPSEEK_API_KEY' not in os.environ and 'SILICONFLOW_API_KEY' in os.environ:
        # Mirror for libraries expecting DEEPSEEK_API_KEY
        os.environ.setdefault('DEEPSEEK_API_KEY', os.getenv('SILICONFLOW_API_KEY', ''))
    # Provide a unified generic key variable some integrations might expect
    if 'OPENAI_API_KEY' in os.environ:
        os.environ.pop('OPENAI_API_KEY')  # enforce no openai usage
    if 'OPENAI_BASE_URL' in os.environ:
        os.environ.pop('OPENAI_BASE_URL')

def _map_status_text(raw_out: str) -> str:
    low = raw_out.lower()
    if 'not found' in low:
        return 'Not Found / 未找到'
    if 'proceed' in low and 'granted' not in low and 'approved' not in low:
        return 'Proceedings / 审理中'
    if any(k in low for k in ['granted', 'approved', 'for information on how to proceed']):
        return 'Granted / 已通过'
    if any(k in low for k in ['rejected', 'closed']):
        return 'Rejected/Closed / 被拒绝/已关闭'
    return 'Unknown Status / 未知状态' + f'(agent_output: {raw_out[:120]})'

async def _agent_query_single(session, code: str, agent_model: str, max_agent_steps: int) -> str:
    if Agent is None or ChatDeepSeek is None:
        return 'Agent Unavailable / Agent不可用'
    _prepare_llm_env()
    task = (
        "Go to {url} . Input Czech visa application number {code}. Read the result. "
        "Return EXACTLY one canonical label: 'Not Found / 未找到' | 'Proceedings / 审理中' | 'Granted / 已通过' | 'Rejected/Closed / 被拒绝/已关闭'. "
        "If unsure choose 'Unknown Status / 未知状态'. Output only that label (bilingual provided)."
    ).format(url=CHECK_URL, code=code)
    # Allow overriding via AGENT_MODEL env (e.g., deepseek-chat). If using SiliconFlow proxy, user sets env and custom base not yet directly wired.
    env_model = os.getenv('AGENT_MODEL') or agent_model or 'deepseek-ai/DeepSeek-R1'
    if ChatDeepSeek is None:
        raise RuntimeError('ChatDeepSeek not available in browser_use installation / 缺少 ChatDeepSeek 类')
    llm = ChatDeepSeek(model=env_model)  # type: ignore
    agent = Agent(task=task, llm=llm, browser_session=session, max_steps=max_agent_steps)
    result = await agent.run()
    return _map_status_text(str(result).strip())

async def _query_single(page, code: str, max_attempts: int = 3) -> str:
    """Drive one query using a Playwright page (via browser_use BrowserSession)."""
    for attempt in range(1, max_attempts + 1):
        try:
            # Small jitter to avoid hammering simultaneous tabs
            await asyncio.sleep(random.uniform(0.05, 0.25))
            # Robust navigation with internal retries for transient net::ERR_ABORTED
            nav_ok = False
            last_nav_err = None
            for nav_try in range(1, 4):  # internal navigation retries (no new window creation)
                try:
                    await page.goto(CHECK_URL, wait_until='domcontentloaded')
                    nav_ok = True
                    break
                except Exception as ne:  # capture aborted / transient
                    msg = str(ne)
                    last_nav_err = ne
                    if 'ERR_ABORTED' in msg or 'Timed out' in msg or 'Navigation timeout' in msg:
                        await asyncio.sleep(0.4 * nav_try + random.uniform(0, 0.3))
                        # If aborted repeatedly, try hard refresh or a new page (only once)
                        if nav_try == 2:
                            try:
                                # hard reload current page
                                await page.reload(wait_until='domcontentloaded')
                                nav_ok = True
                                break
                            except Exception:
                                pass
                        continue
                    else:
                        # unrecoverable nav error -> break early
                        break
            if not nav_ok:
                raise last_nav_err or Exception('Navigation failed')
            # Aggressive overlay suppression
            try:
                await page.evaluate(
                    """
                    (()=>{const sels=['.cookies__wrapper','.cookie-consent','.gdpr-banner','.modal__window','.modal-backdrop'];
                    for (const s of sels){for(const el of document.querySelectorAll(s)){el.style.display='none';el.style.visibility='hidden';el.style.pointerEvents='none';}}})();
                    """
                )
            except Exception:
                pass
            try:
                await page.fill('input[name="visaApplicationNumber"]', code, timeout=4000)
            except Exception:
                await page.wait_for_selector('input[name="visaApplicationNumber"]', timeout=8000)
                await page.fill('input[name="visaApplicationNumber"]', code)
            # Submit (try explicit button then Enter fallback)
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
            # Poll for result
            text_found = ''
            end = time.time() + 6
            while time.time() < end:
                for sel in RESULT_SELECTORS:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = (await el.inner_text()).strip()
                            if txt:
                                text_found = txt
                                break
                    except Exception:
                        continue
                if text_found:
                    break
                await asyncio.sleep(0.25)
            if not text_found:
                # One more quick scan via JS (DOM text) before giving up
                try:
                    dom_text = await page.evaluate('(document.body && document.body.innerText) ? document.body.innerText.slice(0,5000) : ""')
                    if dom_text:
                        lowered = dom_text.lower()
                        for pred, label in STATUS_MAP:
                            if pred(lowered):
                                return label
                except Exception:
                    pass
                raise PlaywrightTimeoutError('No result text (after DOM scan)')
            low = text_found.lower()
            for pred, label in STATUS_MAP:
                if pred(low):
                    return label
            return 'Unknown Status / 未知状态' + f'(status_text/状态文本: {low})'
        except Exception as e:  # retry or fail
            if attempt < max_attempts:
                # If aborted navigation previously, add a slightly longer backoff
                backoff = 0.5 + attempt * 0.4 + random.uniform(0, 0.3)
                if 'ERR_ABORTED' in str(e):
                    backoff += 0.6
                await asyncio.sleep(backoff)
                continue
            return 'Query Failed / 查询失败' + f'(error: {e})'

async def _process_codes(
    codes: List[str],
    max_attempts: int,
    headless: bool,
    use_agent: bool = False,
    agent_model: str = 'deepseek-ai/DeepSeek-R1',
    max_agent_steps: int = 12,
    progress_cb=None,
    workers: int = 1,
) -> List[str]:
    """Process codes with optional concurrency.

    Concurrency model: up to `workers` BrowserSession instances; each code becomes an async task
    that obtains a session (round-robin). Results are written in original order.
    Agent mode also supported but be cautious with rate limits.
    """
    if BrowserSession is None:
        raise RuntimeError('browser-use not installed / 未安装 browser-use')
    # We keep a SINGLE BrowserSession (global semaphore limit=1), but emulate concurrency via multiple tabs/pages.
    requested_workers = max(1, int(workers) if workers else 1)
    if use_agent and requested_workers > 1:
        # Agent path manipulates navigation & reasoning; keep single tab for determinism & token control.
        print('[Info] Agent mode forces single tab / Agent 模式强制单标签')
        requested_workers = 1

    # Single session only
    try:
        session = BrowserSession(headless=headless, viewport={'width': 1200, 'height': 800})
    except Exception as e:
        raise RuntimeError(f'Failed to start BrowserSession: {e}')

    agent_env_ok = bool(os.getenv('DEEPSEEK_API_KEY') or os.getenv('SILICONFLOW_API_KEY'))
    agent_ready = use_agent and Agent is not None and ChatDeepSeek is not None and agent_env_ok
    if use_agent and not agent_ready:
        if Agent is None or ChatDeepSeek is None:
            print('[Warn] DeepSeek agent classes not importable; fallback deterministic / DeepSeek Agent 类不可导入，回退确定性模式')
        elif not agent_env_ok:
            print('[Warn] Missing DEEPSEEK_API_KEY (or SILICONFLOW_API_KEY); fallback deterministic / 缺少 DeepSeek 密钥，回退确定性模式')
    if agent_ready:
        print(f'[Info] Agent mode ON model={agent_model} max_steps={max_agent_steps} workers={workers} / Agent 模式启用 并发={workers}')

    results: List[Optional[str]] = [None] * len(codes)

    if agent_ready:
        # Sequential (single tab)
        for i, code in enumerate(codes):
            try:
                status = await _agent_query_single(session, code, agent_model, max_agent_steps)
            except Exception as e:
                status = 'Query Failed / 查询失败' + f'(agent_error: {e})'
            results[i] = status
            if progress_cb:
                try:
                    progress_cb(code, status)
                except Exception:
                    pass
    else:
        # Multi-tab deterministic concurrency
        base_page = await session.get_current_page()
        pages = [base_page]
        # Create extra pages up to requested_workers
        # Safety cap: never exceed 6 tabs regardless of requested_workers to avoid window explosion
        cap = min(requested_workers, 6)
        if requested_workers > cap:
            print(f'[Info] Requested {requested_workers} tabs capped to {cap} / 申请 {requested_workers} 标签，限制为 {cap}')
        for i in range(1, cap):
            try:
                new_page = await base_page.context.new_page()
                pages.append(new_page)
            except Exception as e:
                print(f'[Warn] Cannot open extra tab {i}: {e} / 无法打开额外标签，减少并发')
                break
        if len(pages) > 1:
            print(f'[Info] Multi-tab mode: {len(pages)} tabs / 多标签并发数: {len(pages)}')

        async def _run_one(idx: int, code: str):
            page = pages[idx % len(pages)]
            try:
                status = await _query_single(page, code, max_attempts=max_attempts)
            except Exception as e:
                status = 'Query Failed / 查询失败' + f'(error: {e})'
            results[idx] = status
            if progress_cb:
                try:
                    progress_cb(code, status)
                except Exception:
                    pass

        # Stagger tasks slightly to avoid burst navigation collisions
        tasks = []
        for i, c in enumerate(codes):
            tasks.append(asyncio.create_task(_run_one(i, c)))
            if len(pages) > 1 and (i < len(codes)-1):
                await asyncio.sleep(0.05)  # tiny stagger
        await asyncio.gather(*tasks)

    # Close session
    try:
        await session.close()
    except Exception:
        pass
    # Replace any None with fallback
    return [r if r is not None else 'Query Failed / 查询失败(unknown)' for r in results]

def update_csv_with_status(csv_path: str, code_col='查询码/Code', status_col='签证状态/Status', headless=True, retries=None, log_dir='logs', workers: int = 1, per_query_delay=0.5, jitter=0.5, use_agent: bool = False, agent_model: str = 'deepseek-ai/DeepSeek-R1', max_agent_steps: int = 12, **_ignored):
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
        print('Hint: generate new codes or clear some status cells to re-query. / 提示：生成新代码或清空部分状态列后再试。')
        return
    max_attempts = retries if (retries and retries > 0) else 3

    # Run queries (sequential for now) with safe loop handling
    def _run(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Nested event loop scenario (e.g., in notebook) -> use create_task and gather via new loop
            return asyncio.ensure_future(coro)  # caller would need to await; for CLI we expect no nested loop
        return asyncio.run(coro)

    # Streaming progress callback writes results as soon as they are available to avoid loss on interruption (Ctrl+C)
    def _progress(code: str, status: str):
        # find corresponding row (row_refs maintain order with pending_codes)
        try:
            idx = pending_codes.index(code)
            row = row_refs[idx]
            row[status_idx] = status
            print(f"{code} -> {status}")
            with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
                w = csv.writer(wf)
                w.writerow(header)
                w.writerows(rows[1:])
        except Exception:
            print(f"[Warn] Failed to persist status for {code}")

    statuses = _run(_process_codes(
        pending_codes,
        max_attempts=max_attempts,
        headless=headless,
        use_agent=use_agent,
        agent_model=agent_model,
        max_agent_steps=max_agent_steps,
        progress_cb=_progress,
        workers=workers,
    ))
    # If returned a Task (unlikely in CLI), await it (statuses list already persisted row by row)
    if hasattr(statuses, 'done') and not getattr(statuses, 'done')():  # pragma: no cover
        statuses = asyncio.get_event_loop().run_until_complete(statuses)
    # Per-query delay loop (already wrote statuses). Sleep after each completed status to mimic prior pacing.
    try:
        d = float(per_query_delay) if per_query_delay is not None else 0.5
        j = float(jitter) if jitter is not None else 0.5
        # already processed len(pending_codes) queries, approximate pacing total sleep
        # Keep old behavior: sleep per code; now aggregate for simplicity.
        total_sleep = 0.0
        for _ in pending_codes:
            total_sleep += max(0.0, d + random.uniform(0, j))
        # Cap total sleep so it doesn't explode for large batches
        time.sleep(min(total_sleep, 5 + len(pending_codes) * 0.2))
    except Exception:
        pass
    mode_note = 'agent' if use_agent else 'deterministic'
    print(f'Done (browser-use {mode_note}) / 完成（browser-use {"智能Agent" if use_agent else "确定性"} 模式）')

if __name__ == '__main__':
    # simple manual test
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--csv', default='query_codes.csv')
    ap.add_argument('--headless', action='store_true')
    ap.add_argument('--retries', type=int, default=3)
    args = ap.parse_args()
    update_csv_with_status(args.csv, headless=args.headless, retries=args.retries)
