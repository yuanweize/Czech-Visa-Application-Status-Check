from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from typing import Dict, Any

from playwright.async_api import async_playwright

from .config import load_env_config, MonitorConfig, CodeConfig
from .notify import send_email
from query_modules.cz import _process_one, _ensure_ready, _maybe_hide_overlays


def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


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


def _start_http_server(site_dir: str, port: int, stop_evt: threading.Event, log):
    handler = partial(SimpleHTTPRequestHandler, directory=site_dir)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    log(f"[{_now_iso()}] serve start dir={site_dir} port={port}")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    stop_evt.wait()
    server.shutdown()
    t.join()
    log(f"[{_now_iso()}] serve stop")


async def run_once(config: MonitorConfig) -> Dict[str, Any]:
    _ensure_dir(config.site_dir)
    _ensure_dir(config.log_dir)
    state_path = os.path.join(config.site_dir, "status.json")
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
        nav_sem = asyncio.Semaphore(1)  # sequential navigation only
        # Build metadata map once
        task_map: Dict[str, Dict[str, Any]] = {}
        for cc in config.codes:
            chan = (cc.channel or '').lower()
            task_map[cc.code] = {
                'code': cc.code,
                'chan': chan,
                'chan_label': 'Email' if chan == 'email' else '',
                'target': cc.target,
                'freq': max(1, int(cc.freq_minutes or 60)),
            }

        num_codes = len(task_map)
        try:
            with open(log_path, 'a', encoding='utf-8') as lf:
                lf.write(f"[{_now_iso()}] startup mode=sequential codes={num_codes} effective_workers=1 nav_cap=1\n")
        except Exception:
            pass

        # Create one context + page, reuse sequentially; recover if page dies
        async def _new_page():
            ctx = await browser.new_context()
            try:
                await ctx.add_init_script(
                    """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
                    """
                )
            except Exception:
                pass
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
                await ctx.route("**/*", _route_handler)
            except Exception:
                pass
            pg = await ctx.new_page()
            try:
                pg.set_default_timeout(15000)
                pg.set_default_navigation_timeout(20000)
            except Exception:
                pass
            try:
                await _ensure_ready(pg, nav_sem)
                await _maybe_hide_overlays(pg)
            except Exception:
                pass
            return ctx, pg

        context = None
        page = None
        try:
            context, page = await _new_page()
            # Iterate codes sequentially
            for code, meta in task_map.items():
                status = 'Query Failed / 查询失败'
                # Up to 3 attempts with recovery steps
                for attempt in range(1, 4):
                    try:
                        s, _tim = await _process_one(page, code, nav_sem)
                        status = s or 'Unknown / 未知'
                        break
                    except Exception as e:
                        # Log error
                        try:
                            with open(log_path, 'a', encoding='utf-8') as lf:
                                lf.write(f"[{_now_iso()}] code={code} attempt={attempt} error={str(e)}\n")
                        except Exception:
                            pass
                        # Recovery strategy per attempt
                        try:
                            if attempt == 1:
                                # Soft reload of base form + overlays
                                await _ensure_ready(page, nav_sem)
                                await _maybe_hide_overlays(page)
                            elif attempt == 2:
                                # Recreate page within same browser
                                if context:
                                    try:
                                        await context.close()
                                    except Exception:
                                        pass
                                context, page = await _new_page()
                            # small backoff
                            await asyncio.sleep(1.0 * attempt)
                        except Exception:
                            # If recovery itself fails, try to recreate on next loop
                            pass
                # Log final
                try:
                    with open(log_path, 'a', encoding='utf-8') as lf:
                        lf.write(f"[{_now_iso()}] result code={code} status={status}\n")
                except Exception:
                    pass

                # Handle result and maybe notify (sequential, no explicit lock needed)
                when = _now_iso()
                result_summary["checked"] += 1
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
                do_notify = (first_time or changed) and (not isinstance(status, str) or 'query failed' not in status.lower())
                if do_notify and meta['chan'] == 'email' and meta['target']:
                    notif_label = '状态变更' if changed and old_status else '首次记录'
                    subject = _build_email_subject(status, code)
                    body = _build_email_body(code, status, when, changed=changed, old_status=old_status, notif_label=notif_label)
                    sent = False
                    try:
                        ok, err = send_email(config, meta['target'], subject, body)
                        sent = ok
                    except Exception as e:
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
        finally:
            try:
                if context:
                    await context.close()
            except Exception:
                pass
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
    os.makedirs(cfg.log_dir, exist_ok=True)
    log_path = os.path.join(cfg.log_dir, f"monitor_{dt.datetime.now().strftime('%Y-%m-%d')}.log")

    def log(msg: str):
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")

    codes = cfg.codes
    if not codes:
        print("No codes configured in env. Nothing to do.")
        return

    stop_evt = threading.Event()
    server_thread = None
    if cfg.serve and not once:
        server_thread = threading.Thread(
            target=_start_http_server, args=(cfg.site_dir, cfg.site_port, stop_evt, log), daemon=True
        )
        server_thread.start()

    print(f"Monitor starting (sequential). SERVE={cfg.serve} SITE_DIR={cfg.site_dir} SITE_PORT={cfg.site_port}")
    log(f"[{_now_iso()}] startup mode=sequential codes={len(codes)}")

    # Persistent state across cycles
    site_json = os.path.join(cfg.site_dir, "status.json")
    os.makedirs(cfg.site_dir, exist_ok=True)
    try:
        with open(site_json, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {"generated_at": _now_iso(), "items": {}}

    # Graceful stop on signals
    stop_flag = False
    try:
        import signal

        def _sig_handler(signum, frame):
            nonlocal stop_flag
            stop_flag = True

        for sig in (getattr(signal, 'SIGINT', None), getattr(signal, 'SIGTERM', None)):
            if sig:
                try:
                    signal.signal(sig, _sig_handler)
                except Exception:
                    pass
    except Exception:
        pass

    async def run_cycle():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=cfg.headless, args=["--disable-gpu", "--no-sandbox"])
            context = await browser.new_context()
            page = await context.new_page()
            await _ensure_ready(page, None)
            await _maybe_hide_overlays(page)

            async def handle_one(code_cfg):
                nonlocal context, page
                code = code_cfg.code
                attempts = 0
                status = None
                while attempts < 3:
                    attempts += 1
                    try:
                        s, _tim = await _process_one(page, code, None)
                        status = s or status
                        break
                    except Exception as e:
                        log(f"[{_now_iso()}] code={code} attempt={attempts} error={str(e)}")
                        try:
                            await _ensure_ready(page, None)
                            await _maybe_hide_overlays(page)
                        except Exception:
                            pass
                        if attempts == 2:
                            try:
                                await context.close()
                                context = await browser.new_context()
                                page = await context.new_page()
                                await _ensure_ready(page, None)
                                await _maybe_hide_overlays(page)
                            except Exception:
                                pass
                        await asyncio.sleep(0.5 * attempts)
                if not status:
                    status = "Query Failed / 查询失败"

                old_item = state["items"].get(code, {})
                old_status = old_item.get("status")
                first_time = (old_status is None)
                changed = (old_status is not None and old_status != status)
                state["items"][code] = {
                    "code": code,
                    "status": status,
                    "last_checked": _now_iso(),
                    "last_changed": old_item.get("last_changed") if not changed else _now_iso(),
                    "channel": "Email" if (code_cfg.channel == "email") else "",
                    "target": code_cfg.target or "",
                }
                log(f"[{_now_iso()}] result code={code} status={status}")

                if status != "Query Failed / 查询失败" and code_cfg.channel == "email" and code_cfg.target:
                    subject = _build_email_subject(status, code)
                    notif_label = '状态变更' if (old_status and changed) else '首次记录'
                    when = _now_iso()
                    body = _build_email_body(code, status, when, changed=changed, old_status=old_status, notif_label=notif_label)
                    ok, err = send_email(cfg, code_cfg.target, subject, body)
                    if ok:
                        log(f"[{_now_iso()}] notify Email code={code} to={code_cfg.target} ok=True")
                    else:
                        log(f"[{_now_iso()}] notify Email code={code} to={code_cfg.target} error={err}")

            for c in codes:
                await handle_one(c)
            state["generated_at"] = _now_iso()
            with open(site_json, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            await browser.close()

    if once:
        await run_cycle()
    else:
        while not stop_flag:
            await run_cycle()
            if stop_flag:
                break
            mins = min([max(1, c.freq_minutes) for c in codes])
            total = mins * 60
            while total > 0 and not stop_flag:
                step = min(1.0, total)
                await asyncio.sleep(step)
                total -= step

    stop_evt.set()
    if server_thread:
        server_thread.join()
