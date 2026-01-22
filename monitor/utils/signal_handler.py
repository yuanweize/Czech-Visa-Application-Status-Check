"""
Signal handling module
信号处理模块
"""
from __future__ import annotations

import signal
import threading
from typing import Callable, Optional


class SignalHandler:
    """信号处理器，用于优雅关闭"""
    
    def __init__(self):
        self.shutdown_callbacks = []
        self.shutdown_event = threading.Event()
        self._original_handlers = {}
    
    def add_shutdown_callback(self, callback: Callable[[], None]) -> None:
        """添加关闭时的回调函数"""
        self.shutdown_callbacks.append(callback)
    
    def setup_signal_handlers(self) -> None:
        """设置信号处理器"""
        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            print(f"\nReceived {signal_name} signal, shutting down gracefully...")
            
            # 调用所有关闭回调
            for callback in self.shutdown_callbacks:
                try:
                    callback()
                except Exception as e:
                    print(f"Error in shutdown callback: {e}")
            
            # 设置关闭事件
            self.shutdown_event.set()
        
        # 保存原始处理器
        for sig in [signal.SIGINT, signal.SIGTERM]:
            try:
                self._original_handlers[sig] = signal.signal(sig, signal_handler)
            except (ValueError, OSError):
                # 某些信号在某些平台上不可用
                pass
    
    def restore_signal_handlers(self) -> None:
        """恢复原始信号处理器"""
        for sig, handler in self._original_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass
    
    def wait_for_shutdown(self, timeout: Optional[float] = None) -> bool:
        """等待关闭信号
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            如果收到关闭信号返回True，超时返回False
        """
        return self.shutdown_event.wait(timeout)


def create_signal_handler() -> SignalHandler:
    """创建并设置信号处理器
    
    Returns:
        配置好的SignalHandler实例
    """
    handler = SignalHandler()
    handler.setup_signal_handlers()
    return handler