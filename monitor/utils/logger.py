"""
Logging utilities module
日志管理工具模块
"""
from __future__ import annotations

import os
import datetime as dt
from pathlib import Path
from typing import Callable


class RotatingLogger:
    """支持轮转的日志记录器"""
    
    def __init__(self, log_path: str, max_size_mb: float = 2.0, backup_lines: int = 1000):
        """
        Args:
            log_path: 日志文件路径
            max_size_mb: 最大文件大小(MB)
            backup_lines: 轮转时保留的行数
        """
        self.log_path = Path(log_path)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.backup_lines = backup_lines
        
        # 确保日志目录存在
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log(self, message: str) -> None:
        """记录日志消息"""
        try:
            # 检查文件大小并轮转
            self._rotate_if_needed()
            
            # 写入日志
            timestamp = dt.datetime.now().isoformat(sep=' ', timespec='seconds')
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {message.rstrip()}\n")
                
        except Exception as e:
            # 日志失败时回退到print
            print(f"Logging error: {e} - Message: {message}")
    
    def _rotate_if_needed(self) -> None:
        """如果需要则轮转日志文件"""
        if not self.log_path.exists():
            return
            
        if self.log_path.stat().st_size <= self.max_size_bytes:
            return
            
        try:
            # 创建备份文件路径
            backup_path = self.log_path.with_suffix('.backup.log')
            
            # 删除旧备份
            if backup_path.exists():
                backup_path.unlink()
            
            # 移动当前日志为备份
            self.log_path.rename(backup_path)
            
            # 从备份中保留最近的行
            try:
                with open(backup_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 保留最后N行
                recent_lines = lines[-self.backup_lines:] if len(lines) > self.backup_lines else lines
                
                # 写入新日志文件
                with open(self.log_path, 'w', encoding='utf-8') as f:
                    f.writelines(recent_lines)
                
                # 删除备份文件
                backup_path.unlink()
                
            except Exception:
                # 如果处理失败，创建空日志文件
                self.log_path.touch()
                
        except Exception:
            # 轮转失败时创建新文件
            try:
                self.log_path.touch()
            except Exception:
                pass


def create_logger(log_dir: str, name_prefix: str = "monitor") -> RotatingLogger:
    """创建日志记录器
    
    Args:
        log_dir: 日志目录
        name_prefix: 日志文件名前缀
        
    Returns:
        RotatingLogger 实例
    """
    today = dt.datetime.now().strftime('%Y-%m-%d')
    log_path = os.path.join(log_dir, f"{name_prefix}_{today}.log")
    return RotatingLogger(log_path)


def now_iso() -> str:
    """获取当前时间的ISO格式字符串"""
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")