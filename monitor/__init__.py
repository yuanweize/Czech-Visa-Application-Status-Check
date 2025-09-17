"""
Czech Visa Application Status Monitor
捷克签证申请状态监控系统

This package provides a modular monitoring system for Czech visa application status checks.
The system is designed with a priority queue-based scheduler for efficient and intelligent monitoring.

Main Components:
- core: Core business logic including scheduler and configuration
- utils: Utility modules for logging, environment monitoring, signal handling
- notification: Email notification system  
- server: HTTP server and API handling

Usage:
    from monitor import run_priority_scheduler, PriorityScheduler
    
    # Run the scheduler
    await run_priority_scheduler()
    
    # Or create a custom scheduler instance
    from monitor.core import load_env_config
    config = load_env_config()
    scheduler = PriorityScheduler(config)
"""

# Import main classes and functions for easy access
from .core import (
    PriorityScheduler, 
    ScheduledTask, 
    BrowserManager, 
    run_priority_scheduler,
    MonitorConfig, 
    CodeConfig, 
    load_env_config
)

from .utils import (
    create_logger, 
    create_env_watcher, 
    create_signal_handler,
    install, uninstall, start, stop, restart, reload, status
)

from .notification import (
    build_email_subject, 
    build_email_body, 
    should_send_notification, 
    send_email,
    send_email_sync,
    send_email_async,
    send_verification_email,
    send_management_code_email
)

from .server import (
    start_http_server, 
    create_server_thread,
    APIHandler, 
    start_cleanup_thread
)

# Package metadata
__version__ = "2.0.0"
__author__ = "Czech Visa Monitor Team"
__description__ = "Modular Czech visa application status monitoring system"

# Main exports
__all__ = [
    # Core scheduler
    'PriorityScheduler',
    'ScheduledTask', 
    'BrowserManager',
    'run_priority_scheduler',
    
    # Configuration
    'MonitorConfig',
    'CodeConfig',
    'load_env_config',
    
    # Utilities
    'create_logger',
    'create_env_watcher', 
    'create_signal_handler',
    'install', 'uninstall', 'start', 'stop', 'restart', 'reload', 'status',
    
    # Notifications
    'build_email_subject',
    'build_email_body',
    'should_send_notification',
    'send_email',
    'send_email_sync',
    'send_email_async',
    'send_verification_email',
    'send_management_code_email',
    
    # Server
    'start_http_server',
    'create_server_thread', 
    'APIHandler',
    'start_cleanup_thread'
]