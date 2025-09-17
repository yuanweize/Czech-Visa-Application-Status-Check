"""
Notification Module
通知模块

This module provides comprehensive email notification functionality including:
- Status change notifications (status_notifications.py)  
- SMTP client with connection pooling (smtp_client.py)
- User management emails and templates (user_management.py)
"""

from .status_notifications import build_email_subject, build_email_body, should_send_notification
from .smtp_client import send_email, send_email_sync, send_email_async
from .user_management import (
    build_verification_email,
    build_management_code_email,
    send_verification_email,
    send_management_code_email
)

__all__ = [
    # Status notifications
    'build_email_subject', 'build_email_body', 'should_send_notification',
    # SMTP client functions  
    'send_email', 'send_email_sync', 'send_email_async',
    # User management functions
    'build_verification_email', 'build_management_code_email',
    'send_verification_email', 'send_management_code_email'
]