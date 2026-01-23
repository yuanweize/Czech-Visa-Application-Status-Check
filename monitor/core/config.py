from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import os, json


@dataclass
class CodeConfig:
    code: str
    query_type: str = "zov"  # "zov" (visa application number) | "oam" (reference number)
    # OAM-specific fields (only used when query_type="oam")
    oam_serial: Optional[str] = None    # e.g., "12345"
    oam_suffix: Optional[str] = None    # e.g., "XX" (optional)
    oam_type: Optional[str] = None      # e.g., "CC", "CD"
    oam_year: Optional[int] = None      # e.g., 2025
    # Common fields
    channel: Optional[str] = "email"  # can be None/empty to disable notifications
    target: Optional[str] = None
    freq_minutes: Optional[int] = None  # None means use global default
    note: Optional[str] = None  # Display note for this code


@dataclass
class MonitorConfig:
    headless: bool
    site_dir: str
    log_dir: str
    serve: bool
    site_port: int
    default_freq_minutes: int  # Global default frequency
    workers: int  # Number of concurrent workers for queries
    smtp_host: Optional[str]
    smtp_port: Optional[int]
    smtp_user: Optional[str]
    smtp_pass: Optional[str]
    smtp_from: Optional[str]
    email_max_per_minute: int  # Email rate limiting
    email_first_check_delay: int  # Delay for first-time check emails
    codes: List[CodeConfig]


def _parse_bool(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "t", "y"):
        return True
    if s in ("0", "false", "no", "off", "f", "n"):
        return False
    return default


import re

def _parse_oam_code(code: str) -> Optional[dict]:
    """Parse OAM code formats into components.
    
    Supported formats:
    - "OAM-12345-XX/CC/2025" -> {'serial': '12345', 'suffix': 'XX', 'type': 'CC', 'year': 2025}
    - "OAM-12345/CC/2025" -> {'serial': '12345', 'suffix': None, 'type': 'CC', 'year': 2025}
    - "12345-XX/CC/2025" -> {'serial': '12345', 'suffix': 'XX', 'type': 'CC', 'year': 2025}
    - "12345/CC/2025" -> {'serial': '12345', 'suffix': None, 'type': 'CC', 'year': 2025}
    """
    if not code:
        return None
    
    # Normalize: remove "OAM-" prefix if present
    code = code.strip()
    if code.upper().startswith("OAM-"):
        code = code[4:]
    
    # Pattern: {serial}[-{suffix}]/{type}/{year}
    # Examples: "12345-XX/CC/2025" or "12345/CC/2025"
    match = re.match(r'^(\d+)(?:-([A-Z]+))?/([A-Z]+)/(\d{4})$', code, re.IGNORECASE)
    if match:
        return {
            'serial': match.group(1),
            'suffix': match.group(2).upper() if match.group(2) else None,
            'type': match.group(3).upper(),
            'year': int(match.group(4))
        }
    
    return None


def load_env_config(env_path: str = ".env") -> MonitorConfig:
    """
    加载环境配置，检测重复代码并拒绝启动
    
    Args:
        env_path: 环境文件路径
    
    Returns:
        配置对象
        
    Raises:
        ValueError: 发现重复查询码时抛出异常
    """
    # Load from environment variables first, then from .env file
    env: dict = {}
    
    # First, load from environment variables
    for key in os.environ:
        env[key] = os.environ[key]
    
    # Then, load from .env file (will override environment variables)
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (IOError, OSError) as e:
            print(f"Warning: Failed to read {env_path}: {e}")
            # Continue with environment variables only
        else:
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
    site_dir = env.get("SITE_DIR") or "site"  # Fixed default to match actual structure
    log_dir = env.get("MONITOR_LOG_DIR") or env.get("LOG_DIR") or "logs/monitor"
    serve = _parse_bool(env.get("SERVE"), False)
    site_port = int(env.get("SITE_PORT") or 8000)
    default_freq_minutes = int(env.get("DEFAULT_FREQ_MINUTES") or 60)  # Global default frequency
    workers = int(env.get("WORKERS") or 1)  # Number of concurrent workers

    smtp_host = env.get("SMTP_HOST")
    smtp_port = int(env["SMTP_PORT"]) if env.get("SMTP_PORT") else None
    smtp_user = env.get("SMTP_USER")
    smtp_pass = env.get("SMTP_PASS")
    smtp_from = env.get("SMTP_FROM")

    # Email rate limiting configuration
    email_max_per_minute = int(env.get("EMAIL_MAX_PER_MINUTE") or 10)
    email_first_check_delay = int(env.get("EMAIL_FIRST_CHECK_DELAY") or 30)

    codes: List[CodeConfig] = []
    if env.get("CODES_JSON"):
        try:
            json_str = env["CODES_JSON"]
            arr = json.loads(json_str)
            for obj in arr:
                # Handle optional fields properly
                channel_val = obj.get("channel")
                if channel_val is not None:
                    channel_val = channel_val.strip()
                    if channel_val == "":
                        channel_val = None  # Empty string means disable notifications
                else:
                    channel_val = "email"  # Default to email if not specified
                
                # freq_minutes can be None to use global default
                freq_val = obj.get("freq_minutes")
                if freq_val is not None and freq_val != "":
                    freq_val = int(freq_val)
                else:
                    freq_val = None  # Use global default
                
                # Query type: "zov" (default) or "oam"
                query_type = obj.get("type", obj.get("query_type", "zov")).lower()
                
                # OAM-specific fields
                oam_serial = obj.get("oam_serial")
                oam_suffix = obj.get("oam_suffix")
                oam_type = obj.get("oam_type")
                oam_year = obj.get("oam_year")
                
                # Auto-parse OAM code format: "OAM-12345-XX/CC/2025" or "12345/CC/2025"
                code_str = obj["code"].strip()
                if query_type == "oam" and not oam_serial:
                    parsed = _parse_oam_code(code_str)
                    if parsed:
                        oam_serial = parsed.get("serial") or oam_serial
                        oam_suffix = parsed.get("suffix") or oam_suffix
                        oam_type = parsed.get("type") or oam_type
                        oam_year = parsed.get("year") or oam_year
                
                # Convert oam_year to int if needed
                if oam_year is not None:
                    oam_year = int(oam_year)
                    
                codes.append(CodeConfig(
                    code=code_str,
                    query_type=query_type,
                    oam_serial=oam_serial,
                    oam_suffix=oam_suffix,
                    oam_type=oam_type,
                    oam_year=oam_year,
                    channel=channel_val,
                    target=obj.get("target"),
                    freq_minutes=freq_val,
                    note=obj.get("note"),
                ))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Warning: Invalid CODES_JSON in {env_path}: {e}")
            print(f"CODES_JSON content: {repr(env.get('CODES_JSON', 'missing'))}")

    # Load numbered entries
    idx = 1
    while env.get(f"CODE_{idx}"):
        channel_val = env.get(f"CHANNEL_{idx}")
        if channel_val is not None:
            channel_val = channel_val.strip()
            if channel_val == "":
                channel_val = None
        else:
            channel_val = "email"
            
        freq_val = env.get(f"FREQ_MINUTES_{idx}")
        if freq_val is not None and freq_val != "":
            freq_val = int(freq_val)
        else:
            freq_val = None
            
        codes.append(CodeConfig(
            code=env[f"CODE_{idx}"].strip(),
            channel=channel_val,
            target=env.get(f"TARGET_{idx}"),
            freq_minutes=freq_val,
            note=env.get(f"NOTE_{idx}"),
        ))
        idx += 1

    # 检测重复查询码 - 直接拒绝启动
    if codes:
        code_set = set()
        duplicate_codes = []
        
        for code_config in codes:
            if code_config.code in code_set:
                duplicate_codes.append(code_config.code)
            else:
                code_set.add(code_config.code)
        
        if duplicate_codes:
            error_msg = f"❌ 配置错误：发现重复查询码 {duplicate_codes}\n" \
                       f"请检查配置文件 {env_path} 并删除重复的查询码。\n" \
                       f"系统拒绝启动以防止数据混乱。"
            print(error_msg)
            raise ValueError(f"Duplicate query codes found: {duplicate_codes}")

    return MonitorConfig(
        headless=headless,
        site_dir=site_dir,
        log_dir=log_dir,
        serve=serve,
        site_port=site_port,
        default_freq_minutes=default_freq_minutes,
        workers=workers,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_pass=smtp_pass,
        smtp_from=smtp_from,
        email_max_per_minute=email_max_per_minute,
        email_first_check_delay=email_first_check_delay,
        codes=codes,
    )
