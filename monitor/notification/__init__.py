"""
Notification Module
通知模块

This module provides comprehensive email notification functionality including:
- Status change notifications (status_notifications.py)  
- SMTP client with connection pooling (smtp_client.py)
- User management emails and templates (user_management.py)
"""

from .status_notifications import build_email_subject, build_email_body, should_send_notification
from .smtp_client import (
    send_email, send_email_async,
    send_email_queued, send_email_queued_sync,
    send_email_immediate, send_email_immediate_sync,
    configure_email_queue, get_email_queue_stats, stop_email_queue
)
from .user_management import (
    build_verification_email,
    build_management_code_email,
    send_verification_email,
    send_management_code_email,
    build_success_page,
    build_error_page
)
from ..utils.logger import get_email_logger, EmailOperationLogger

__all__ = [
    # Status notifications
    'build_email_subject', 'build_email_body', 'should_send_notification',
    # SMTP client functions  
    'send_email', 'send_email_async',
    # Queued email functions
    'send_email_queued', 'send_email_queued_sync',
    'configure_email_queue', 'get_email_queue_stats', 'stop_email_queue',
    # Immediate email functions (for verification codes)
    'send_email_immediate', 'send_email_immediate_sync',
    # User management functions
    'build_verification_email', 'build_management_code_email',
    'send_verification_email', 'send_management_code_email',
    # HTML page generation functions
    'build_success_page', 'build_error_page',
    # Email logger
    'get_email_logger', 'EmailOperationLogger'
]