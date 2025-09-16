from __future__ import annotations

import smtplib, ssl
from email.mime.text import MIMEText
from email.utils import formataddr


def send_email(cfg, to_addr: str, subject: str, html_body: str):
    try:
        msg = MIMEText(html_body, "html", "utf-8")
        sender = cfg.smtp_from or "CZ Visa Monitor"
        if "@" in sender:
            msg["From"] = formataddr(("CZ Visa Monitor", sender))
        else:
            msg["From"] = "CZ Visa Monitor <noreply@example.com>"
        msg["To"] = to_addr
        msg["Subject"] = subject

        port = cfg.smtp_port or 465
        if port == 465:
            with smtplib.SMTP_SSL(cfg.smtp_host, port, context=ssl.create_default_context()) as s:
                if cfg.smtp_user and cfg.smtp_pass:
                    s.login(cfg.smtp_user, cfg.smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.smtp_host, port) as s:
                s.ehlo()
                try:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                except Exception:
                    pass
                if cfg.smtp_user and cfg.smtp_pass:
                    s.login(cfg.smtp_user, cfg.smtp_pass)
                s.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)
