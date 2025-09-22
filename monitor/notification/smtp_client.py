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
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from queue import Queue, Empty
import logging

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


@dataclass
class EmailTask:
    """Email task for queue processing"""
    to_email: str
    subject: str
    html_body: str
    smtp_config: dict
    env_path: str = ".env"
    priority: int = 0  # 0 = normal, 1 = high (for immediate notifications)
    created_at: float = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()


class EmailRateLimiter:
    """Email rate limiter to prevent SMTP server overload"""
    
    def __init__(self, max_emails_per_minute: int = 10, max_burst: int = 3):
        self.max_emails_per_minute = max_emails_per_minute
        self.max_burst = max_burst
        self.email_times = []
        self.lock = threading.Lock()
        
    def can_send_email(self) -> bool:
        """Check if we can send an email now"""
        with self.lock:
            current_time = time.time()
            # Remove emails older than 1 minute
            self.email_times = [t for t in self.email_times if current_time - t < 60]
            
            # Check if we're under the limit
            return len(self.email_times) < self.max_emails_per_minute
    
    def record_email_sent(self):
        """Record that an email was sent"""
        with self.lock:
            self.email_times.append(time.time())
    
    def wait_time_for_next_email(self) -> float:
        """Calculate how long to wait before sending next email"""
        with self.lock:
            if len(self.email_times) < self.max_emails_per_minute:
                return 0
            
            # Find the oldest email time within the minute window
            current_time = time.time()
            oldest_in_window = min(t for t in self.email_times if current_time - t < 60)
            return max(0, 60 - (current_time - oldest_in_window) + 1)


class EmailQueue:
    """Asynchronous email queue with rate limiting"""
    
    def __init__(self, max_emails_per_minute: int = 10):
        self.queue = Queue()
        self.rate_limiter = EmailRateLimiter(max_emails_per_minute)
        self.worker_thread = None
        self.stop_event = threading.Event()
        self.logger = get_email_logger()
        self.stats = {
            'queued': 0,
            'sent': 0,
            'failed': 0
        }
        
    def start_worker(self):
        """Start the background email worker thread"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_event.clear()
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            
    def stop_worker(self):
        """Stop the background email worker thread"""
        self.stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
    
    def queue_email(self, task: EmailTask):
        """Add an email to the queue"""
        self.queue.put(task)
        self.stats['queued'] += 1
        
    def _worker_loop(self):
        """Background worker loop to process email queue"""
        while not self.stop_event.is_set():
            try:
                # Wait for rate limiter
                wait_time = self.rate_limiter.wait_time_for_next_email()
                if wait_time > 0:
                    if self.stop_event.wait(wait_time):
                        break
                
                # Get next email task
                try:
                    task = self.queue.get(timeout=1)
                except Empty:
                    continue
                
                # Send the email
                try:
                    cfg = _dict_to_config(task.smtp_config, task.env_path)
                    success, error = send_email(cfg, task.to_email, task.subject, task.html_body)
                    
                    if success:
                        self.rate_limiter.record_email_sent()
                        self.stats['sent'] += 1
                        self.logger.log_notification_email_result(
                            f"queue_{int(task.created_at)}", True, 
                            smtp_response="Email sent via queue"
                        )
                    else:
                        self.stats['failed'] += 1
                        self.logger.log_notification_email_result(
                            f"queue_{int(task.created_at)}", False, error=error
                        )
                        
                except Exception as e:
                    self.stats['failed'] += 1
                    self.logger.log_notification_email_result(
                        f"queue_{int(task.created_at)}", False, error=str(e)
                    )
                
                finally:
                    self.queue.task_done()
                    
            except Exception as e:
                # Log unexpected errors but keep the worker running
                logging.error(f"Email queue worker error: {e}")
                time.sleep(1)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            **self.stats,
            'queue_size': self.queue.qsize(),
            'rate_limit_wait': self.rate_limiter.wait_time_for_next_email()
        }


# Global email queue instance
_email_queue = EmailQueue(max_emails_per_minute=10)  # Default limit, can be configured


def send_email(cfg, to_addr: str, subject: str, html_body: str):
    """Send email with detailed logging"""
    logger = get_email_logger()
    
    # Validate configuration first
    if not cfg.smtp_host:
        return False, "SMTP host not configured"
    
    # Validate SMTP_FROM configuration
    if not cfg.smtp_from or "@" not in cfg.smtp_from:
        return False, "SMTP_FROM must be configured with a valid email address (e.g., user@domain.com)"
    
    try:
        msg = MIMEText(html_body, "html", "utf-8")
        
        # Set From header using the configured email address
        msg["From"] = formataddr(("CZ Visa Monitor", cfg.smtp_from))
        msg["To"] = to_addr
        msg["Subject"] = subject

        # Use connection pool to reuse SMTP connections
        conn = _smtp_pool.get_connection(cfg)
        
        # Send the email and capture any response
        smtp_response = None
        try:
            # Use sendmail for explicit control over from/to addresses
            send_result = conn.sendmail(cfg.smtp_from, [to_addr], msg.as_string())
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
    cfg.smtp_from = smtp_config.get('from', cfg.smtp_from)  # No fallback, let validation catch it
    
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


async def send_email_queued(to_email: str, subject: str, html_body: str, smtp_config: dict, 
                           env_path: str = ".env", priority: int = 0) -> Tuple[bool, Optional[str]]:
    """
    Queue an email for sending with rate limiting (async version)
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        smtp_config: SMTP configuration dict with keys: host, port, user, pass, from
        env_path: Path to .env file for loading base configuration
        priority: 0 = normal, 1 = high priority
        
    Returns:
        Tuple of (success: bool, message: str or None) - success indicates if queued successfully
    """
    try:
        # Start the queue worker if not already running
        _email_queue.start_worker()
        
        # Create and queue the email task
        task = EmailTask(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            smtp_config=smtp_config,
            env_path=env_path,
            priority=priority
        )
        
        _email_queue.queue_email(task)
        
        return True, f"Email queued for {to_email}"
        
    except Exception as e:
        return False, f"Failed to queue email: {str(e)}"


def send_email_queued_sync(to_email: str, subject: str, html_body: str, smtp_config: dict, 
                          env_path: str = ".env", priority: int = 0) -> Tuple[bool, Optional[str]]:
    """
    Queue an email for sending with rate limiting (sync wrapper)
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        html_body: HTML email body
        smtp_config: SMTP configuration dict with keys: host, port, user, pass, from
        env_path: Path to .env file for loading base configuration
        priority: 0 = normal, 1 = high priority
        
    Returns:
        Tuple of (success: bool, message: str or None) - success indicates if queued successfully
    """
    try:
        return asyncio.run(send_email_queued(to_email, subject, html_body, smtp_config, env_path, priority))
    except RuntimeError:
        # If we're already in an async context, create new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send_email_queued(to_email, subject, html_body, smtp_config, env_path, priority))
        finally:
            loop.close()


def configure_email_queue(max_emails_per_minute: int = 10):
    """Configure the email queue rate limiting"""
    global _email_queue
    _email_queue.rate_limiter.max_emails_per_minute = max_emails_per_minute


def get_email_queue_stats() -> Dict[str, Any]:
    """Get email queue statistics"""
    return _email_queue.get_stats()


def stop_email_queue():
    """Stop the email queue worker (for graceful shutdown)"""
    _email_queue.stop_worker()


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