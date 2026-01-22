"""
HTTP server module
HTTP服务器模块
"""
from __future__ import annotations

import threading
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Callable

# 尝试导入API服务器
try:
    from .api_handler import APIHandler, start_cleanup_thread
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


def start_http_server(
    site_dir: str, 
    port: int, 
    stop_event: threading.Event, 
    log_func: Callable[[str], None],
    config_path: str = '.env'
) -> None:
    """启动HTTP服务器
    
    Args:
        site_dir: 静态文件目录
        port: 端口号
        stop_event: 停止事件
        log_func: 日志记录函数
        config_path: 配置文件路径
    """
    if API_AVAILABLE:
        # 创建结合静态文件服务和API处理的处理器
        def create_handler(*args, **kwargs):
            return APIHandler(*args, config_path=config_path, site_dir=site_dir, **kwargs)
        
        server = ThreadingHTTPServer(("0.0.0.0", port), create_handler)
        log_func(f"HTTP server started with API - dir={site_dir} port={port}")
        
        # 启动用户管理的后台清理线程
        try:
            cleanup_thread = start_cleanup_thread(site_dir)
            log_func(f"Started background cleanup for user management")
        except Exception as e:
            log_func(f"Failed to start cleanup thread: {e}")
    else:
        # 回退到简单的静态文件服务
        handler = partial(SimpleHTTPRequestHandler, directory=site_dir)
        server = ThreadingHTTPServer(("0.0.0.0", port), handler)
        log_func(f"HTTP server started (static only) - dir={site_dir} port={port}")
    
    # 启动服务器线程
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    # 等待停止信号
    stop_event.wait()
    
    # 关闭服务器
    server.shutdown()
    server_thread.join(timeout=5)
    log_func(f"HTTP server stopped")


def create_server_thread(
    site_dir: str,
    port: int,
    log_func: Callable[[str], None],
    config_path: str = '.env'
) -> tuple[threading.Thread, threading.Event]:
    """创建HTTP服务器线程
    
    Args:
        site_dir: 静态文件目录
        port: 端口号  
        log_func: 日志记录函数
        config_path: 配置文件路径
        
    Returns:
        (服务器线程, 停止事件)
    """
    stop_event = threading.Event()
    
    server_thread = threading.Thread(
        target=start_http_server,
        args=(site_dir, port, stop_event, log_func, config_path),
        daemon=True
    )
    
    return server_thread, stop_event