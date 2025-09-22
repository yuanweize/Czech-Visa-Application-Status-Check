"""
SMTP Email Client with Connection Pooling
SMTP邮件客户端，支持连接池

This module provides SMTP email sending functionality with connection pooling
and supports both async/sync modes for different use cases.
"""

from __future__ import annotations

import smtplib, ssl, time, threading, asyncio
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional, Tuple

from ..core.config import MonitorConfig, load_env_config
from ..utils.logger import get_email_logger

# SMTP connection pool to prevent too many AUTH commands
class SMTPConnectionPool:
    def __init__(self):
        self._connection: Optional[smtplib.SMTP] = None
        self._last_used = 0
        self._lock = threading.Lock()
        self._max_idle_time = 300  # 5 minutes
        self._last_auth_time = 0
        self._min_auth_interval = 5  # Minimum 5 seconds between auth attempts to avoid rapid AUTH
        self._socket_timeout = 15  # seconds

    def get_connection(self, cfg: MonitorConfig) -> smtplib.SMTP:
        """Get an active SMTP connection, reusing existing one if possible"""
        logger = get_email_logger()
        
        with self._lock:
            current_time = time.time()
            
            # Check if we need to avoid too frequent auth attempts
            if (current_time - self._last_auth_time) < self._min_auth_interval:
                time.sleep(self._min_auth_interval - (current_time - self._last_auth_time))
                current_time = time.time()
            
            # Check if we can reuse existing connection
            connection_reused = False
            if (self._connection and 
                (current_time - self._last_used) < self._max_idle_time):
                try:
                    # Test connection with NOOP command
                    self._connection.noop()
                    self._last_used = current_time
                    connection_reused = True
                    
                    # Log successful connection reuse
                    log_id = logger.log_smtp_connection_attempt(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user or "")
                    logger.log_smtp_connection_result(log_id, True, connection_reused=True)
                    
                    return self._connection
                except (smtplib.SMTPException, OSError) as e:
                    # Connection is dead, close it
                    log_id = logger.log_smtp_connection_attempt(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user or "")
                    logger.log_smtp_connection_result(log_id, False, f"Connection test failed: {e}", connection_reused=True)
                    self.close()
            
            # Create new connection
            log_id = logger.log_smtp_connection_attempt(cfg.smtp_host, cfg.smtp_port, cfg.smtp_user or "")
            
            try:
                # Create context for SSL/TLS
                context = ssl.create_default_context()
                
                if cfg.smtp_port == 465:
                    # SSL connection
                    server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=self._socket_timeout)
                else:
                    # Regular connection with STARTTLS
                    server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=self._socket_timeout)
                    server.starttls(context=context)
                
                # Login if credentials provided
                if cfg.smtp_user and cfg.smtp_pass:
                    auth_log_id = logger.log_smtp_auth_attempt(cfg.smtp_host, cfg.smtp_user)
                    try:
                        server.login(cfg.smtp_user, cfg.smtp_pass)
                        self._last_auth_time = current_time
                        logger.log_smtp_auth_result(auth_log_id, True)
                    except Exception as auth_e:
                        logger.log_smtp_auth_result(auth_log_id, False, str(auth_e))
                        raise auth_e
                
                self._connection = server
                self._last_used = current_time
                
                # Log successful connection
                logger.log_smtp_connection_result(log_id, True)
                
                return server
                
            except Exception as e:
                self._connection = None
                error_msg = f"Failed to create SMTP connection: {e}"
                logger.log_smtp_connection_result(log_id, False, error_msg)
                raise Exception(error_msg)

    def close(self):
        """Close current SMTP connection"""
        with self._lock:
            if self._connection:
                try:
                    self._connection.quit()
                except (smtplib.SMTPException, OSError):
                    pass  # Connection might already be closed
                self._connection = None
                self._last_used = 0

# Global connection pool instance
_smtp_pool = SMTPConnectionPool()


def send_email(cfg, to_addr: str, subject: str, html_body: str):
    """Send email with detailed logging"""
    logger = get_email_logger()
    
    # Validate configuration first
    if not cfg.smtp_host:
        return False, "SMTP host not configured"
    
    try:
        msg = MIMEText(html_body, "html", "utf-8")
        
        # Set From header properly according to RFC 5322
        if cfg.smtp_from and "@" in cfg.smtp_from:
            # Use the configured email address with display name
            msg["From"] = formataddr(("CZ Visa Monitor", cfg.smtp_from))
        else:
            # Fallback to default
            msg["From"] = "CZ Visa Monitor <noreply@example.com>"
            
        msg["To"] = to_addr
        msg["Subject"] = subject

        # Use connection pool to reuse SMTP connections
        conn = _smtp_pool.get_connection(cfg)
        
        # Send the email and capture any response
        smtp_response = None
        try:
            # Extract from address for explicit sendmail usage  
            from_addr = cfg.smtp_from if cfg.smtp_from and "@" in cfg.smtp_from else "noreply@example.com"
            
            # Use sendmail for explicit control over from/to addresses
            send_result = conn.sendmail(from_addr, [to_addr], msg.as_string())
            # sendmail returns a dict of failed recipients, empty dict means success
            if isinstance(send_result, dict) and len(send_result) == 0:
                smtp_response = "Message sent successfully"
            else:
                smtp_response = f"Send result: {send_result}"
        except Exception as send_e:
            raise send_e
        
        return True, smtp_response
        
    except Exception as e:
        # On error, close the connection to force reconnection next time
        _smtp_pool.close()
        return False, str(e)


def _dict_to_config(smtp_config: dict, env_path: str = ".env") -> MonitorConfig:
    """
    Convert SMTP config dict to MonitorConfig object for compatibility
    
    Args:
        smtp_config: SMTP configuration dict with keys: host, port, user, pass, from
        env_path: Path to .env file for loading base configuration (supports hot reload)
        
    Returns:
        MonitorConfig object with SMTP settings from environment + overrides
    """
    # Load base configuration from environment variables
    cfg = load_env_config(env_path)
    
    # Override SMTP settings with provided values
    cfg.smtp_host = smtp_config['host']
    cfg.smtp_port = smtp_config.get('port', cfg.smtp_port or 465)
    cfg.smtp_user = smtp_config.get('user', cfg.smtp_user)
    cfg.smtp_pass = smtp_config.get('pass', cfg.smtp_pass)
    cfg.smtp_from = smtp_config.get('from', cfg.smtp_from or 'CZ Visa Monitor')
    
    return cfg


async def send_email_async(to_email: str, subject: str, html_body: str, smtp_config: dict, env_path: str = ".env") -> Tuple[bool, Optional[str]]:
    """
    Send email using SMTP configuration (async version)
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        smtp_config: SMTP configuration dict with keys: host, port, user, pass, from
        env_path: Path to .env file for loading base configuration (supports hot reload)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    try:
        # Run the synchronous email sending in a thread pool
        cfg = _dict_to_config(smtp_config, env_path)
        loop = asyncio.get_event_loop()
        
        # Use run_in_executor to make the blocking operation async
        def _send_sync():
            return send_email(cfg, to_email, subject, html_body)
        
        result = await loop.run_in_executor(None, _send_sync)
        if isinstance(result, tuple):
            return result
        return True, None
    except Exception as e:
        return False, str(e)


def send_email_sync(to_email: str, subject: str, html_body: str, smtp_config: dict, env_path: str = ".env") -> Tuple[bool, Optional[str]]:
    """
    Send email using SMTP configuration (sync wrapper)
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        smtp_config: SMTP configuration dict with keys: host, port, user, pass, from
        env_path: Path to .env file for loading base configuration (supports hot reload)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    # Simple sync wrapper that runs the async version
    try:
        return asyncio.run(send_email_async(to_email, subject, html_body, smtp_config, env_path))
    except RuntimeError:
        # If we're already in an async context, create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send_email_async(to_email, subject, html_body, smtp_config, env_path))
        finally:
            loop.close()