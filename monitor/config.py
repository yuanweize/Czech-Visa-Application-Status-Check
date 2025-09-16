from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import os, json


@dataclass
class CodeConfig:
    code: str
    channel: str = "email"  # only 'email' supported
    target: Optional[str] = None
    freq_minutes: int = 60


@dataclass
class MonitorConfig:
    headless: bool
    site_dir: str
    log_dir: str
    serve: bool
    site_port: int
    smtp_host: Optional[str]
    smtp_port: Optional[int]
    smtp_user: Optional[str]
    smtp_pass: Optional[str]
    smtp_from: Optional[str]
    codes: List[CodeConfig]


def _parse_bool(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def load_env_config(env_path: str = ".env") -> MonitorConfig:
    # Lightweight .env parser (KEY=VALUE lines) with support for multi-line JSON values
    env: dict = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (IOError, OSError) as e:
            # File might be locked or temporarily unavailable during editing
            print(f"Warning: Failed to read {env_path}: {e}")
            # Return default config to avoid breaking the service
            return MonitorConfig(
                headless=True, site_dir="monitor_site", log_dir="logs/monitor",
                serve=False, site_port=8000, smtp_host=None, smtp_port=None,
                smtp_user=None, smtp_pass=None, smtp_from=None, codes=[]
            )
            
        buf_key = None
        buf_val: List[str] = []
        for line in lines:
            line = line.rstrip("\n")
            if not line or line.strip().startswith("#"):
                continue
            if buf_key:
                buf_val.append(line)
                if line.strip().endswith("]"):
                    env[buf_key] = "\n".join(buf_val)
                    buf_key, buf_val = None, []
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "CODES_JSON" and not v.endswith("]"):
                    buf_key = k
                    buf_val = [v]
                else:
                    env[k] = v

    headless = _parse_bool(env.get("HEADLESS"), True)
    site_dir = env.get("SITE_DIR") or "monitor_site"
    log_dir = env.get("MONITOR_LOG_DIR") or env.get("LOG_DIR") or "logs/monitor"
    serve = _parse_bool(env.get("SERVE"), False)
    site_port = int(env.get("SITE_PORT") or 8000)

    smtp_host = env.get("SMTP_HOST")
    smtp_port = int(env["SMTP_PORT"]) if env.get("SMTP_PORT") else None
    smtp_user = env.get("SMTP_USER")
    smtp_pass = env.get("SMTP_PASS")
    smtp_from = env.get("SMTP_FROM")

    codes: List[CodeConfig] = []
    if env.get("CODES_JSON"):
        try:
            json_str = env["CODES_JSON"]
            arr = json.loads(json_str)
            for obj in arr:
                # Handle empty channel values properly
                channel_val = obj.get("channel")
                if channel_val is not None:
                    channel_val = channel_val.strip().lower()
                else:
                    channel_val = "email"  # Only default if not explicitly set
                    
                codes.append(CodeConfig(
                    code=obj["code"].strip(),
                    channel=channel_val,
                    target=obj.get("target"),
                    freq_minutes=int(obj.get("freq_minutes") or 60),
                ))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Better error reporting for JSON issues
            print(f"Warning: Invalid CODES_JSON in {env_path}: {e}")
            print(f"CODES_JSON content: {repr(env.get('CODES_JSON', 'missing'))}")
            # Don't raise, just continue with empty codes to avoid breaking the service
            pass

    idx = 1
    while env.get(f"CODE_{idx}"):
        # Handle empty channel values properly - don't default to "email"
        channel_val = env.get(f"CHANNEL_{idx}")
        if channel_val is not None:
            channel_val = channel_val.strip().lower()
        else:
            channel_val = "email"  # Only default if not explicitly set
            
        codes.append(CodeConfig(
            code=env[f"CODE_{idx}"].strip(),
            channel=channel_val,
            target=env.get(f"TARGET_{idx}"),
            freq_minutes=int(env.get(f"FREQ_MINUTES_{idx}") or 60),
        ))
        idx += 1

    return MonitorConfig(
        headless=headless,
        site_dir=site_dir,
        log_dir=log_dir,
        serve=serve,
        site_port=site_port,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        smtp_from=smtp_from,
        codes=codes,
    )
