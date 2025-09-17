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
from pathlib import Path

from playwright.async_api import async_playwright

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

from .config import load_env_config, MonitorConfig, CodeConfig
from .notify import send_email
from query_modules.cz import _process_one, _ensure_ready, _maybe_hide_overlays

# Import API handler for user management
try:
    from .api_server import APIHandler, start_cleanup_thread
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


def _now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class EnvFileWatcher:
    """Watches .env file for changes and triggers configuration reload."""
    
    def __init__(self, env_path: str, reload_callback):
        self.env_path = Path(env_path).resolve()
        self.reload_callback = reload_callback
        self.observer = None
        self.last_reload = 0
        self.reload_debounce = 2  # seconds
        
    def start(self):
        if not WATCHDOG_AVAILABLE:
            print("Warning: watchdog not available, .env hot reloading disabled")
            return False
            
        class EnvChangeHandler(FileSystemEventHandler):
            def __init__(self, watcher):
                self.watcher = watcher
                
            def on_modified(self, event):
                if event.is_directory:
                    return
                if Path(event.src_path).resolve() == self.watcher.env_path:
                    self.watcher._trigger_reload()
                    
        try:
            self.observer = Observer()
            handler = EnvChangeHandler(self)
            # Watch the directory containing the .env file
            watch_dir = self.env_path.parent
            self.observer.schedule(handler, str(watch_dir), recursive=False)
            self.observer.start()
            print(f"Started watching {self.env_path} for changes")
            return True
        except Exception as e:
            print(f"Failed to start .env file watcher: {e}")
            return False
            
    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            print("Stopped .env file watcher")
            
    def _trigger_reload(self):
        current_time = time.time()
        if current_time - self.last_reload < self.reload_debounce:
            return  # Debounce rapid changes
            
        self.last_reload = current_time
        print(f"[{_now_iso()}] .env file changed, reloading configuration...")
        try:
            self.reload_callback()
        except Exception as e:
            print(f"[{_now_iso()}] Error reloading configuration: {e}")


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
                    <div style=\"margin-top:6px;\">
                        查看实时状态：<a href=\"https://visa.eurun.top/\" target=\"_blank\" rel=\"noopener\" style=\"color:#0b5ed7; text-decoration:none;\">https://visa.eurun.top/</a>
                    </div>
                </div>
            </div>
        </div>
        """


def _ensure_dir(p: str):
    try:
        os.makedirs(p, exist_ok=True)
    except Exception:
        pass


def _start_http_server(site_dir: str, port: int, stop_evt: threading.Event, log, config_path: str = '.env'):
    """Start HTTP server with static file serving and API handling"""
    if API_AVAILABLE:
        # Create handler that combines static file serving with API handling
        def create_handler(*args, **kwargs):
            return APIHandler(*args, config_path=config_path, site_dir=site_dir, **kwargs)
        
        server = ThreadingHTTPServer(("0.0.0.0", port), create_handler)
        log(f"[{_now_iso()}] serve start with API dir={site_dir} port={port}")
        
        # Start background cleanup for user management
        cleanup_thread = start_cleanup_thread(site_dir)
        log(f"[{_now_iso()}] started background cleanup for user management")
    else:
        # Fallback to simple static file serving
        handler = partial(SimpleHTTPRequestHandler, directory=site_dir)
        server = ThreadingHTTPServer(("0.0.0.0", port), handler)
        log(f"[{_now_iso()}] serve start (static only) dir={site_dir} port={port}")
    
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
            # Check if email is properly configured
            email_configured = (chan == 'email' and 
                              cc.target and 
                              config.smtp_host and 
                              config.smtp_user and 
                              config.smtp_pass)
            task_map[cc.code] = {
                'code': cc.code,
                'chan': chan,
                'chan_label': 'Email' if email_configured else '',
                'target': cc.target,
                'freq': max(1, int(cc.freq_minutes or config.default_freq_minutes)),
                'note': cc.note,  # Include note in task data
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
        """Enhanced logging with rotation to keep logs under 2MB."""
        try:
            # Check log file size and rotate if needed
            if os.path.exists(log_path) and os.path.getsize(log_path) > 2 * 1024 * 1024:  # 2MB
                # Create backup and truncate
                backup_path = log_path.replace('.log', '_backup.log')
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(log_path, backup_path)
                # Keep only recent entries from backup
                try:
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    # Keep last 1000 lines
                    recent_lines = lines[-1000:] if len(lines) > 1000 else lines
                    with open(log_path, 'w', encoding='utf-8') as f:
                        f.writelines(recent_lines)
                    os.remove(backup_path)
                except Exception:
                    # If rotation fails, just create new file
                    open(log_path, 'w').close()
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg.rstrip() + "\n")
        except Exception as e:
            # Fallback to print if logging fails
            print(f"Logging error: {e} - Message: {msg}")

    codes = cfg.codes
    if not codes:
        print("No codes configured in env. Nothing to do.")
        return

    # Configuration reload flag and lock
    config_reload_flag = threading.Event()
    config_lock = threading.Lock()
    new_codes_to_check = []  # New codes that need immediate checking
    
    def reload_config():
        """Reload configuration from .env file with differential updates."""
        nonlocal cfg, codes, new_codes_to_check
        with config_lock:
            try:
                # Add small delay and retry logic to handle file editing race conditions
                import time
                for attempt in range(3):
                    try:
                        new_cfg = load_env_config(env_path)
                        # Sanity check: if we get 0 codes but had codes before, 
                        # the file might be temporarily corrupted during editing
                        if len(new_cfg.codes) == 0 and len(codes) > 0:
                            if attempt < 2:  # Retry on first two attempts
                                log(f"[{_now_iso()}] Warning: Got 0 codes during reload (attempt {attempt+1}), retrying...")
                                time.sleep(0.5)  # Wait 500ms before retry
                                continue
                            else:
                                log(f"[{_now_iso()}] Warning: Still got 0 codes after retries, proceeding anyway")
                        break
                    except Exception as e:
                        if attempt < 2:
                            log(f"[{_now_iso()}] Config reload attempt {attempt+1} failed: {e}, retrying...")
                            time.sleep(0.5)
                            continue
                        else:
                            raise e
                
                old_codes = {c.code: c for c in codes}
                new_codes = {c.code: c for c in new_cfg.codes}
                
                # Find changes
                added_codes = set(new_codes.keys()) - set(old_codes.keys())
                removed_codes = set(old_codes.keys()) - set(new_codes.keys())
                modified_codes = []
                for code in set(old_codes.keys()) & set(new_codes.keys()):
                    old_c, new_c = old_codes[code], new_codes[code]
                    if (old_c.channel != new_c.channel or 
                        old_c.target != new_c.target or 
                        old_c.freq_minutes != new_c.freq_minutes):
                        modified_codes.append(code)
                
                # Update global config and codes
                cfg = new_cfg
                codes = new_cfg.codes
                
                # Store new codes for immediate processing
                new_codes_to_check = list(added_codes)
                
                # Handle changes in status.json
                if removed_codes or modified_codes:
                    try:
                        site_json_path = os.path.join(cfg.site_dir, "status.json")
                        if os.path.exists(site_json_path):
                            with open(site_json_path, "r", encoding="utf-8") as f:
                                status_data = json.load(f)
                            
                            # Remove deleted codes
                            for code in removed_codes:
                                status_data["items"].pop(code, None)
                            
                            # Update modified codes' channel and target info
                            for code in modified_codes:
                                if code in status_data["items"] and code in new_codes:
                                    new_code_cfg = new_codes[code]
                                    # Check if email is properly configured
                                    email_configured = (new_code_cfg.channel == "email" and 
                                                      new_code_cfg.target and 
                                                      cfg.smtp_host and 
                                                      cfg.smtp_user and 
                                                      cfg.smtp_pass)
                                    
                                    # Update channel and target in status.json
                                    status_data["items"][code]["channel"] = "Email" if email_configured else ""
                                    status_data["items"][code]["target"] = new_code_cfg.target or ""
                            
                            status_data["generated_at"] = _now_iso()
                            with open(site_json_path, "w", encoding="utf-8") as f:
                                json.dump(status_data, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        log(f"[{_now_iso()}] Error updating status.json: {e}")
                
                # Log changes
                change_summary = []
                if added_codes:
                    change_summary.append(f"added {len(added_codes)}")
                if removed_codes:
                    change_summary.append(f"removed {len(removed_codes)}")
                if modified_codes:
                    change_summary.append(f"modified {len(modified_codes)}")
                
                changes_str = ", ".join(change_summary) if change_summary else "no changes"
                log(f"[{_now_iso()}] Configuration reloaded: {len(old_codes)} -> {len(new_codes)} codes ({changes_str})")
                print(f"Configuration reloaded: {len(old_codes)} -> {len(new_codes)} codes ({changes_str})")
                
                if added_codes or removed_codes or modified_codes:
                    config_reload_flag.set()
                    
            except Exception as e:
                log(f"[{_now_iso()}] Error reloading configuration: {e}")
                print(f"Error reloading configuration: {e}")

    # Setup .env file watcher for hot reloading
    env_watcher = None
    if not once:  # Only enable hot reloading in daemon mode
        env_watcher = EnvFileWatcher(env_path, reload_config)
        env_watcher.start()

    stop_evt = threading.Event()
    server_thread = None
    if cfg.serve and not once:
        server_thread = threading.Thread(
            target=_start_http_server, 
            args=(cfg.site_dir, cfg.site_port, stop_evt, log, env_path), 
            daemon=True
        )
        server_thread.start()

    print(f"Monitor starting (sequential). SERVE={cfg.serve} SITE_DIR={cfg.site_dir} SITE_PORT={cfg.site_port}")
    log(f"[{_now_iso()}] startup mode=sequential codes={len(codes)}")
    if env_watcher and WATCHDOG_AVAILABLE:
        log(f"[{_now_iso()}] .env hot reloading enabled")

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
        # Get current config safely
        with config_lock:
            current_cfg = cfg
            current_codes = codes[:]
            
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=current_cfg.headless, args=["--disable-gpu", "--no-sandbox"])
            context = await browser.new_context()
            page = await context.new_page()
            await _ensure_ready(page, None)
            await _maybe_hide_overlays(page)

            async def handle_one(code_cfg):
                nonlocal context, page
                code = code_cfg.code
                log(f"[{_now_iso()}] Processing code={code} (channel={code_cfg.channel}, target={code_cfg.target})")
                attempts = 0
                status = None
                while attempts < 3:
                    attempts += 1
                    try:
                        log(f"[{_now_iso()}] code={code} attempt={attempts}/3 starting query")
                        s, _tim = await _process_one(page, code, None)
                        status = s or status
                        if status:
                            log(f"[{_now_iso()}] code={code} attempt={attempts}/3 success: {status}")
                        break
                    except Exception as e:
                        log(f"[{_now_iso()}] code={code} attempt={attempts}/3 error={str(e)}")
                        try:
                            await _ensure_ready(page, None)
                            await _maybe_hide_overlays(page)
                        except Exception:
                            pass
                        if attempts == 2:
                            log(f"[{_now_iso()}] code={code} max attempts reached, recreating browser context")
                            try:
                                await context.close()
                                context = await browser.new_context()
                                page = await context.new_page()
                                await _ensure_ready(page, None)
                                await _maybe_hide_overlays(page)
                            except Exception as ctx_e:
                                log(f"[{_now_iso()}] code={code} context recreation failed: {ctx_e}")
                        await asyncio.sleep(0.5 * attempts)
                if not status:
                    status = "Query Failed / 查询失败"
                    log(f"[{_now_iso()}] code={code} all attempts failed, marking as Query Failed")

                old_item = state["items"].get(code, {})
                old_status = old_item.get("status")
                first_time = (old_status is None)
                changed = (old_status is not None and old_status != status)
                
                # Determine if email notification is properly configured
                email_configured = (code_cfg.channel == "email" and 
                                  code_cfg.target and 
                                  current_cfg.smtp_host and 
                                  current_cfg.smtp_user and 
                                  current_cfg.smtp_pass)
                
                # Calculate next check time
                freq_minutes = code_cfg.freq_minutes or current_cfg.default_freq_minutes
                next_check = dt.datetime.now() + dt.timedelta(minutes=freq_minutes)
                
                state["items"][code] = {
                    "code": code,
                    "status": status,
                    "last_checked": _now_iso(),
                    "last_changed": old_item.get("last_changed") if not changed else _now_iso(),
                    "next_check": next_check.isoformat(),
                    "channel": "Email" if email_configured else "",
                    "target": code_cfg.target or "",
                    "freq_minutes": freq_minutes,
                    "note": code_cfg.note,
                }
                log(f"[{_now_iso()}] result code={code} status={status}")

                # Notify only on first-time record or when status actually changes (and not for Query Failed)
                if (first_time or changed) and status != "Query Failed / 查询失败" and email_configured:
                    log(f"[{_now_iso()}] code={code} triggering notification (first_time={first_time}, changed={changed})")
                    subject = _build_email_subject(status, code)
                    notif_label = '状态变更' if (old_status and changed) else '首次记录'
                    when = _now_iso()
                    body = _build_email_body(code, status, when, changed=changed, old_status=old_status, notif_label=notif_label)
                    log(f"[{_now_iso()}] code={code} sending email to={code_cfg.target}")
                    ok, err = send_email(current_cfg, code_cfg.target, subject, body)
                    if ok:
                        log(f"[{_now_iso()}] notify Email code={code} to={code_cfg.target} ok=True")
                    else:
                        log(f"[{_now_iso()}] notify Email code={code} to={code_cfg.target} error={err}")
                elif not email_configured and code_cfg.channel == "email":
                    log(f"[{_now_iso()}] code={code} email notification skipped (email not properly configured)")
                else:
                    log(f"[{_now_iso()}] code={code} notification skipped (no change or query failed)")

            for c in current_codes:
                await handle_one(c)
            
            # Log cycle summary
            processed_count = len(current_codes)
            log(f"[{_now_iso()}] Cycle summary: processed {processed_count} codes, updating status.json")
            
            state["generated_at"] = _now_iso()
            with open(site_json, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            await browser.close()
            log(f"[{_now_iso()}] Browser closed, cycle complete")

    try:
        if once:
            await run_cycle()
        else:
            while not stop_flag:
                cycle_start = _now_iso()
                log(f"[{cycle_start}] Starting monitoring cycle")
                
                # Check for configuration reload
                if config_reload_flag.is_set():
                    config_reload_flag.clear()
                    log(f"[{_now_iso()}] Processing configuration reload")
                    # Update site_json path in case SITE_DIR changed
                    with config_lock:
                        site_json = os.path.join(cfg.site_dir, "status.json")
                        os.makedirs(cfg.site_dir, exist_ok=True)
                
                # Get current codes for this cycle
                with config_lock:
                    current_codes = codes[:]
                    # Check for newly added codes that need immediate processing
                    has_new_codes = len(new_codes_to_check) > 0
                    if has_new_codes:
                        new_codes_to_check.clear()  # Clear the list
                
                if current_codes:
                    log(f"[{_now_iso()}] Processing {len(current_codes)} codes")
                    await run_cycle()
                    cycle_end = _now_iso()
                    log(f"[{cycle_end}] Cycle completed, processed {len(current_codes)} codes")
                else:
                    log(f"[{_now_iso()}] No codes configured, waiting for configuration...")
                
                if stop_flag:
                    break
                    
                # Calculate sleep time
                with config_lock:
                    current_codes = codes[:]
                    current_config = cfg
                    
                if current_codes:
                    mins = min([max(1, c.freq_minutes or current_config.default_freq_minutes) for c in current_codes])
                    total = mins * 60
                    log(f"[{_now_iso()}] Sleeping for {mins} minutes until next cycle")
                    while total > 0 and not stop_flag:
                        step = min(1.0, total)
                        await asyncio.sleep(step)
                        total -= step
                        # Check for config reload during sleep
                        if config_reload_flag.is_set():
                            log(f"[{_now_iso()}] Config reload detected during sleep, breaking early")
                            break
                        # Check for new codes that need immediate processing
                        with config_lock:
                            if len(new_codes_to_check) > 0:
                                log(f"[{_now_iso()}] New codes detected during sleep, breaking early for immediate processing")
                                break
                else:
                    # No codes configured, wait and check for reload
                    log(f"[{_now_iso()}] No codes configured, sleeping 60s and rechecking")
                    await asyncio.sleep(60)
    finally:
        # Cleanup
        if env_watcher:
            env_watcher.stop()
        stop_evt.set()
        if server_thread:
            server_thread.join()
        
        # Close SMTP connection pool
        try:
            from .notify import _smtp_pool
            _smtp_pool.close()
        except Exception:
            pass
