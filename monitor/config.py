from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_addr: str


@dataclass
class CodeConfig:
    code: str
    channel: str  # 'email' or '' (other values are ignored)
    target: Optional[str]  # email address for email channel
    freq_minutes: int


@dataclass
class MonitorConfig:
    email: Optional[EmailConfig]
    headless: bool
    site_dir: str
    log_dir: str
    codes: List[CodeConfig]


BOOL_TRUE = {"1", "true", "t", "yes", "y", "on"}


def _bool(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in BOOL_TRUE:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def load_env_config(env_path: str = ".env") -> MonitorConfig:
    # Lightweight .env parser (KEY=VALUE lines) with support for multi-line JSON values
    data: Dict[str, str] = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        i = 0
        n = len(lines)
        while i < n:
            raw = lines[i]
            i += 1
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip()
            # Handle multi-line JSON values (e.g., CODES_JSON=[ ... ])
            if key.upper() == "CODES_JSON":
                # If starts with [ or { and not obviously closed on this line, accumulate
                if (val.startswith("[") and not val.rstrip().endswith("]")) or (val.startswith("{") and not val.rstrip().endswith("}")):
                    buf = [val]
                    # simple bracket balance for [] and {}
                    br_sq = val.count("[") - val.count("]")
                    br_br = val.count("{") - val.count("}")
                    while i < n and (br_sq != 0 or br_br != 0):
                        nxt = lines[i]
                        i += 1
                        buf.append(nxt.rstrip("\n"))
                        br_sq += nxt.count("[") - nxt.count("]")
                        br_br += nxt.count("{") - nxt.count("}")
                    val = "\n".join(buf)
                data[key] = val.strip().strip('"').strip("'")
            else:
                data[key] = val.strip().strip('"').strip("'")

    email: Optional[EmailConfig] = None
    if data.get("SMTP_HOST") and data.get("SMTP_PORT") and data.get("SMTP_USER") and data.get("SMTP_PASS") and data.get("SMTP_FROM"):
        try:
            port = int(data.get("SMTP_PORT", "587"))
        except Exception:
            port = 587
        email = EmailConfig(
            smtp_host=data["SMTP_HOST"],
            smtp_port=port,
            username=data["SMTP_USER"],
            password=data["SMTP_PASS"],
            from_addr=data["SMTP_FROM"],
        )

    headless = _bool(data.get("HEADLESS"), True)
    site_dir = data.get("SITE_DIR", os.path.join("reports", "monitor_site"))
    log_dir = data.get("MONITOR_LOG_DIR") or data.get("LOG_DIR") or os.path.join("logs", "monitor")
    # Deprecated: MONITOR_WORKERS removed; monitor runs sequentially by design.

    codes: List[CodeConfig] = []
    # Codes list: either JSON array in CODES_JSON or numbered entries CODE_1=... CHANNEL_1=...
    codes_json = data.get("CODES_JSON")
    if codes_json:
        try:
            arr = json.loads(codes_json)
            if isinstance(arr, list):
                for item in arr:
                    code = str(item.get("code", "")).strip()
                    if not code:
                        continue
                    channel = str(item.get("channel", "")).strip().lower()
                    target = item.get("target")
                    freq = int(item.get("freq_minutes", 60) or 60)
                    codes.append(CodeConfig(code=code, channel=channel, target=target, freq_minutes=freq))
        except Exception:
            # fall back to numbered entries silently
            pass
    else:
        i = 1
        while True:
            code = data.get(f"CODE_{i}")
            if not code:
                break
            channel = (data.get(f"CHANNEL_{i}") or "").strip().lower()
            target = data.get(f"TARGET_{i}")
            try:
                freq = int(data.get(f"FREQ_MINUTES_{i}") or 60)
            except Exception:
                freq = 60
            codes.append(CodeConfig(code=code.strip(), channel=channel, target=target, freq_minutes=freq))
            i += 1

    if not codes:
        # Provide a helpful hint path for users
        # (Do not raise; the scheduler will print 'No codes configured')
        try:
            import sys
            print("[monitor] No codes parsed from env. Check CODES_JSON or CODE_1 entries.", file=sys.stderr)
        except Exception:
            pass
    return MonitorConfig(email=email, headless=headless, site_dir=site_dir, log_dir=log_dir, codes=codes)
