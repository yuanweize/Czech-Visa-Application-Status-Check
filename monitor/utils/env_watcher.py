"""
Environment file watcher module
监控 .env 文件变化并触发配置重载
"""
from __future__ import annotations

import time
import threading
from pathlib import Path
from typing import Callable, Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False


class EnvFileWatcher:
    """监控 .env 文件变化并触发配置重载"""
    
    def __init__(self, env_path: str, reload_callback: Callable[[], None]):
        self.env_path = Path(env_path).resolve()
        self.reload_callback = reload_callback
        self.observer = None
        
    def start(self):
        """开始监控 .env 文件"""
        if not WATCHDOG_AVAILABLE:
            return
            
        watch_dir = self.env_path.parent
        if not watch_dir.exists():
            return
            
        class EnvChangeHandler(FileSystemEventHandler):
            def __init__(self, watcher):
                self.watcher = watcher
                
            def on_modified(self, event):
                if event.is_directory:
                    return
                    
                # 检查是否是我们关心的 .env 文件
                if Path(event.src_path).resolve() == self.watcher.env_path:
                    # 延迟触发以避免频繁重载
                    threading.Timer(0.5, self.watcher._trigger_reload).start()
        
        try:
            self.observer = Observer()
            handler = EnvChangeHandler(self)
            self.observer.schedule(handler, str(watch_dir), recursive=False)
            self.observer.start()
        except Exception:
            # 如果监控失败，静默忽略
            pass
    
    def stop(self):
        """停止监控"""
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=5)
            except Exception:
                pass
    
    def _trigger_reload(self):
        """触发配置重载"""
        try:
            # 检查文件是否存在且可读
            if self.env_path.exists() and self.env_path.is_file():
                # 添加小延迟确保文件写入完成
                time.sleep(0.1)
                self.reload_callback()
        except Exception:
            # 重载失败时静默忽略
            pass


def create_env_watcher(env_path: str, reload_callback: Callable[[], None]) -> Optional[EnvFileWatcher]:
    """创建环境文件监控器
    
    Args:
        env_path: .env 文件路径
        reload_callback: 重载时调用的回调函数
        
    Returns:
        EnvFileWatcher 实例，如果 watchdog 不可用则返回 None
    """
    if not WATCHDOG_AVAILABLE:
        return None
        
    watcher = EnvFileWatcher(env_path, reload_callback)
    watcher.start()
    return watcher