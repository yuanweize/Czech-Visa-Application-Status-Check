from __future__ import annotations

import smtplib, ssl, time, threading
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

# SMTP connection pool to prevent too many AUTH commands
class SMTPConnectionPool:
    def __init__(self):
        self._connection: Optional[smtplib.SMTP] = None
        self._last_used = 0
        self._lock = threading.Lock()
        self._max_idle_time = 300  # 5 minutes
        self._last_auth_time = 0
        self._min_auth_interval = 10  # Minimum 10 seconds between auth attempts

    def get_connection(self, cfg):
        with self._lock:
            now = time.time()
            
            # Rate limit AUTH commands
            if now - self._last_auth_time < self._min_auth_interval:
                time.sleep(self._min_auth_interval - (now - self._last_auth_time))
                now = time.time()
            
            # Check if existing connection is still valid and not too old
            if (self._connection is not None and 
                now - self._last_used < self._max_idle_time):
                try:
                    # Test connection with a simple command
                    self._connection.noop()
                    self._last_used = now
                    return self._connection
                except Exception:
                    # Connection is dead, close it
                    try:
                        self._connection.quit()
                    except Exception:
                        pass
                    self._connection = None
            
            # Create new connection
            try:
                port = cfg.smtp_port or 465
                if port == 465:
                    conn = smtplib.SMTP_SSL(cfg.smtp_host, port, context=ssl.create_default_context())
                else:
                    conn = smtplib.SMTP(cfg.smtp_host, port)
                    conn.ehlo()
                    try:
                        conn.starttls(context=ssl.create_default_context())
                        conn.ehlo()
                    except Exception:
                        pass
                
                # Authenticate only if credentials are provided
                if cfg.smtp_user and cfg.smtp_pass:
                    conn.login(cfg.smtp_user, cfg.smtp_pass)
                    self._last_auth_time = now
                
                self._connection = conn
                self._last_used = now
                return conn
            except Exception as e:
                self._connection = None
                raise e

    def close(self):
        with self._lock:
            if self._connection:
                try:
                    self._connection.quit()
                except Exception:
                    pass
                self._connection = None

# Global connection pool
_smtp_pool = SMTPConnectionPool()

def send_email(cfg, to_addr: str, subject: str, html_body: str):
    # Validate configuration first
    if not cfg.smtp_host:
        return False, "SMTP host not configured"
    
    try:
        msg = MIMEText(html_body, "html", "utf-8")
        sender = cfg.smtp_from or "CZ Visa Monitor"
        if "@" in sender:
            msg["From"] = formataddr(("CZ Visa Monitor", sender))
        else:
            msg["From"] = "CZ Visa Monitor <noreply@example.com>"
        msg["To"] = to_addr
        msg["Subject"] = subject

        # Use connection pool to reuse SMTP connections
        conn = _smtp_pool.get_connection(cfg)
        conn.send_message(msg)
        
        return True, None
    except Exception as e:
        # On error, close the connection to force reconnection next time
        _smtp_pool.close()
        return False, str(e)
