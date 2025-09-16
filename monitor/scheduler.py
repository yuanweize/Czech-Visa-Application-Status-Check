from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from typing import Dict, Any

from playwright.async_api import async_playwright

from .config import load_env_config, MonitorConfig, CodeConfig
from .notify import send_telegram, send_email
from query_modules.cz import query_code_with_browser, _normalize_status


STATE_FILE = "status.json"


def _now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _format_notify(code: str, status: str, when: str) -> str:
    return (
        f"<b>CZ Visa Status</b>\n"
        f"Code: <code>{code}</code>\n"
        f"Status: <b>{status}</b>\n"
        f"Time: {when}"
    )


async def run_once(config: MonitorConfig) -> Dict[str, Any]:
    os.makedirs(config.site_dir, exist_ok=True)
    state_path = os.path.join(config.site_dir, STATE_FILE)
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
        browser = await p.chromium.launch(headless=config.headless)
        try:
            # Sequential by default to be gentle; small concurrency could be added if needed
            for cc in config.codes:
                code = cc.code
                status, timings = await query_code_with_browser(browser, code)
                status = _normalize_status(status or "")
                when = _now_iso()
                result_summary["checked"] += 1
                old = items.get(code)
                first_time = old is None
                old_status = old.get("status") if isinstance(old, dict) else None
                changed = (old_status != status)
                if changed:
                    result_summary["changed"] += 1
                # Persist
                items[code] = {
                    "code": code,
                    "status": status,
                    "last_checked": when,
                    "last_changed": when if changed else (old.get("last_changed") if isinstance(old, dict) else when),
                    "channel": cc.channel,
                    "target": cc.target,
                }
                # Notify if first time OR changed
                do_notify = first_time or changed
                if do_notify:
                    sent = False
                    if cc.channel == "tg" and config.telegram:
                        sent = send_telegram(config.telegram, _format_notify(code, status, when), chat_id_override=cc.target)
                    elif cc.channel == "email" and config.email and cc.target:
                        sent = send_email(config.email, cc.target, subject=f"CZ Visa Status for {code}", body=_format_notify(code, status, when))
                    if sent:
                        result_summary["notified"] += 1
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
