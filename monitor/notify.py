from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr
from .config import EmailConfig


def send_email(email: EmailConfig, to_addr: str, subject: str, body: str) -> bool:
    msg = MIMEText(body, "html", "utf-8")
    msg["From"] = formataddr(("Visa Monitor", email.from_addr))
    msg["To"] = to_addr
    msg["Subject"] = subject
    try:
        if int(email.smtp_port) == 465:
            # Implicit TLS
            with smtplib.SMTP_SSL(email.smtp_host, email.smtp_port, timeout=20) as server:
                if email.username and email.password:
                    server.login(email.username, email.password)
                server.sendmail(email.from_addr, [to_addr], msg.as_string())
            return True
        else:
            with smtplib.SMTP(email.smtp_host, email.smtp_port, timeout=20) as server:
                try:
                    server.starttls()
                except Exception:
                    pass
                if email.username and email.password:
                    server.login(email.username, email.password)
                server.sendmail(email.from_addr, [to_addr], msg.as_string())
            return True
    except Exception as e:
        # Propagate failure detail via exception so caller can log specifics
        raise
