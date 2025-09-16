from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
import json
import urllib.request
import urllib.parse
from typing import Optional

from .config import TelegramConfig, EmailConfig


def send_telegram(tg: TelegramConfig, text: str, chat_id_override: Optional[str] = None) -> bool:
    chat_id = chat_id_override or tg.chat_id
    try:
        base = f"https://api.telegram.org/bot{tg.bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(base, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return False
            return True
    except Exception:
        return False


def send_email(email: EmailConfig, to_addr: str, subject: str, body: str) -> bool:
    msg = MIMEText(body, "html", "utf-8")
    msg["From"] = formataddr(("Visa Monitor", email.from_addr))
    msg["To"] = to_addr
    msg["Subject"] = subject
    try:
        with smtplib.SMTP(email.smtp_host, email.smtp_port, timeout=20) as server:
            try:
                server.starttls()
            except Exception:
                pass
            if email.username and email.password:
                server.login(email.username, email.password)
            server.sendmail(email.from_addr, [to_addr], msg.as_string())
        return True
    except Exception:
        return False
