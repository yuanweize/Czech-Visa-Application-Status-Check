from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from typing import Dict, Any

from playwright.async_api import async_playwright

from .config import load_env_config, MonitorConfig, CodeConfig
from .notify import send_email
from query_modules.cz import _process_one


STATE_FILE = "status.json"


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _build_email_subject(status: str, code: str) -> str:
        # Example: [Granted / 已通过] PEKI202508190001 - CZ Visa Status
        return f"[{status}] {code} - CZ Visa Status"


def _build_email_body(code: str, status: str, when: str, *, changed: bool, old_status: str | None, notif_label: str) -> str:
        # Simple, clean HTML email with minimal inline styles
        old_to_new = ''
        if changed and old_status:
                old_to_new = f"<tr><td style=\"color:#555;\">状态变化</td><td><b>{old_status}</b> &rarr; <b>{status}</b></td></tr>"
        return f"""
        <div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; line-height:1.6; color:#222;\">
            <div style=\"max-width:680px; margin:24px auto; border:1px solid #eee; border-radius:10px; overflow:hidden; box-shadow:0 4px 14px rgba(0,0,0,.06);\">
                <div style=\"padding:16px 20px; background:#0b5ed7; color:#fff;\">
                    <div style=\"font-weight:600; font-size:16px; letter-spacing:.2px;\">CZ Visa Status 通知</div>
                    <div style=\"margin-top:4px; font-size:13px; opacity:.9;\">Code <b>{code}</b> · 当前状态 <b>{status}</b></div>
                </div>
                <div style=\"padding:16px 20px; background:#fff;\">
                    <table style=\"width:100%; border-collapse:collapse; font-size:14px;\">
                        <tr>
                            <td style=\"width:120px; color:#555;\">查询码</td>
                            <td><code style=\"background:#f6f8fa; padding:2px 6px; border-radius:6px;\">{code}</code></td>
                        </tr>
                        <tr>
                            <td style=\"color:#555;\">通知类型</td>
                            <td>{notif_label}</td>
                        </tr>
                        {old_to_new}
                        <tr>
                            <td style=\"color:#555;\">当前状态</td>
                            <td><b>{status}</b></td>
                        </tr>
                        <tr>
                            <td style=\"color:#555;\">时间</td>
                            <td>{when}</td>
                        </tr>
                    </table>
                </div>
                <div style=\"padding:12px 20px; background:#fafafa; color:#666; font-size:12px; border-top:1px solid #eee;\">
                    说明：当首次查询或状态发生变化时会发送通知；若状态为“查询失败”，不会触发通知。
                </div>
            </div>
        </div>
        """


def _ensure_dir(p: str):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        pass


async def run_once(config: MonitorConfig) -> Dict[str, Any]:
    _ensure_dir(config.site_dir)
    _ensure_dir(config.log_dir)
    state_path = os.path.join(config.site_dir, STATE_FILE)
    log_path = os.path.join(config.log_dir, f"monitor_{dt.date.today().isoformat()}.log")
    # Load previous state
    prev: Dict[str, Any] = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
        except Exception:
            prev = {}

    # Ensure dict structure
    prev.setdefault("items", {})
    items: Dict[str, Any] = prev["items"]

    result_summary: Dict[str, Any] = {
        "checked": 0,
        "changed": 0,
        "notified": 0,
        "time": _now_iso(),
    }

    async with async_playwright() as p:
        # Add small stealth args to reduce headless detection odds
        browser = await p.chromium.launch(
            headless=config.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-gpu"]
        )
        try:
            queue: asyncio.Queue = asyncio.Queue()

            # Build items with channel label and enqueue (Email-only)
            task_map = {}
            for cc in config.codes:
                code = cc.code
                chan = (cc.channel or '').lower()
                chan_label = 'Email' if chan == 'email' else ''
                task_map[code] = {
                    'code': code,
                    'chan': chan,
                    'chan_label': chan_label,
                    'target': cc.target,
                }
                await queue.put(code)

            # Determine effective worker count: don't spawn more workers than codes
            num_codes = len(task_map)
            configured_workers = max(1, int(config.workers))
            workers = min(configured_workers, max(1, num_codes)) if num_codes > 0 else 0

            # Align navigation throttling with effective worker count
            nav_cap = min(10, max(1, workers)) if workers > 0 else 1
            nav_sem = asyncio.Semaphore(nav_cap)

            # Startup log
            try:
                with open(log_path, 'a', encoding='utf-8') as lf:
                    lf.write(f"[{_now_iso()}] startup codes={num_codes} configured_workers={configured_workers} effective_workers={workers} nav_cap={nav_cap}\n")
            except Exception:
                pass

            result_lock = asyncio.Lock()

            async def handle_result(code: str, status: str):
                nonlocal items, result_summary
                when = _now_iso()
                async with result_lock:
                    result_summary["checked"] += 1
                    meta = task_map[code]
                    old = items.get(code)
                    first_time = old is None
                    old_status = old.get("status") if isinstance(old, dict) else None
                    changed = (old_status != status)
                    if changed:
                        result_summary["changed"] += 1
                    items[code] = {
                        "code": code,
                        "status": status,
                        "last_checked": when,
                        "last_changed": when if changed else (old.get("last_changed") if isinstance(old, dict) else when),
                        "channel": meta['chan_label'],
                        "target": meta['target'],
                    }
                    # Notify
                    do_notify = (first_time or changed) and (not isinstance(status, str) or 'query failed' not in status.lower())
                    if do_notify:
                        sent = False
                        if meta['chan'] == 'email' and config.email and meta['target']:
                            notif_label = '状态变更' if changed and old_status else '首次记录'
                            subject = _build_email_subject(status, code)
                            body = _build_email_body(code, status, when, changed=changed, old_status=old_status, notif_label=notif_label)
                            try:
                                # send_email will raise on failure; success returns True
                                sent = send_email(config.email, meta['target'], subject=subject, body=body)
                            except Exception as e:
                                sent = False
                                try:
                                    with open(log_path, 'a', encoding='utf-8') as lf:
                                        lf.write(f"[{_now_iso()}] notify Email code={code} to={meta['target']} error={str(e)}\n")
                                except Exception:
                                    pass
                            else:
                                try:
                                    with open(log_path, 'a', encoding='utf-8') as lf:
                                        lf.write(f"[{_now_iso()}] notify Email code={code} to={meta['target']} ok={sent}\n")
                                except Exception:
                                    pass
                        if sent:
                            result_summary["notified"] += 1

            async def worker(name: str):
                context = await browser.new_context()
                # basic stealth: unset webdriver and set languages/plugins
                try:
                    await context.add_init_script(
                        """
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
                        """
                    )
                except Exception:
                    pass
                # Block heavy resources similar to cz worker
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
                # Pre-warm: ensure input present and hide overlays once
                try:
                    from query_modules.cz import _ensure_ready, _maybe_hide_overlays
                    await _ensure_ready(page, nav_sem)
                    await _maybe_hide_overlays(page)
                except Exception:
                    pass
                while True:
                    try:
                        code = await queue.get()
                    except Exception:
                        break
                    if code is None:
                        queue.task_done()
                        break
                    status = 'Query Failed / 查询失败'
                    for attempt in range(1, 3):
                        try:
                            s, _tim = await _process_one(page, code, nav_sem)
                            # Do not re-normalize; _process_one already returns normalized status
                            status = s or 'Unknown / 未知'
                            break
                        except Exception as e:
                            try:
                                with open(log_path, 'a', encoding='utf-8') as lf:
                                    lf.write(f"[{_now_iso()}] code={code} attempt={attempt} error={str(e)}\n")
                            except Exception:
                                pass
                            if attempt < 2:
                                await asyncio.sleep(1.0)
                    # Log final status (no captures)
                    try:
                        with open(log_path, 'a', encoding='utf-8') as lf:
                            lf.write(f"[{_now_iso()}] result code={code} status={status}\n")
                    except Exception:
                        pass
                    await handle_result(code, status)
                    queue.task_done()
                try:
                    await context.close()
                except Exception:
                    pass

            if workers == 0:
                # No codes to process; skip spawning workers
                pass
            else:
                tasks = [asyncio.create_task(worker(f"mw{i+1}")) for i in range(workers)]
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

    # Write state.json
    out = {
        "generated_at": _now_iso(),
        "items": items,
    }
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


async def run_scheduler(env_path: str, once: bool = False):
    cfg = load_env_config(env_path)
    if not cfg.codes:
        print("No codes configured in env. Nothing to do.")
        return

    async def _loop():
        # next run per-code tracking
        next_run: Dict[str, float] = {}
        while True:
            start = asyncio.get_event_loop().time()
            await run_once(cfg)
            now = asyncio.get_event_loop().time()
            # Determine minimal sleep based on per-code freq; simple approach: take min(freq)
            min_freq = min(max(1, c.freq_minutes) for c in cfg.codes)
            sleep_s = max(5.0, min_freq * 60.0 - (now - start))
            await asyncio.sleep(sleep_s)

    if once:
        await run_once(cfg)
    else:
        await _loop()
