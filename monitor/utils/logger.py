"""
Logging utilities module
日志管理工具模块

Enhanced with structured logging and email operation tracking
"""
from __future__ import annotations

import os
import json
import datetime as dt
from pathlib import Path
from typing import Callable, Optional, Dict, Any


class RotatingLogger:
    """支持轮转的日志记录器 - 增强版本支持结构化日志"""
    
    def __init__(self, log_path: str, max_size_mb: float = 2.0, backup_lines: int = 1000, 
                 stats_file: Optional[str] = None):
        """
        Args:
            log_path: 日志文件路径
            max_size_mb: 最大文件大小(MB)
            backup_lines: 轮转时保留的行数
            stats_file: 统计文件路径（可选）
        """
        self.log_path = Path(log_path)
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.backup_lines = backup_lines
        self.stats_file = Path(stats_file) if stats_file else None
        
        # 确保日志目录存在
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.stats_file:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log(self, message: str) -> None:
        """记录普通日志消息"""
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
    
    def log_structured(self, log_entry: Dict[str, Any]) -> None:
        """记录结构化日志条目"""
        try:
            # 检查文件大小并轮转
            self._rotate_if_needed()
            
            # 添加时间戳如果没有
            if 'timestamp' not in log_entry:
                log_entry['timestamp'] = dt.datetime.now().isoformat()
            
            # 写入结构化日志
            timestamp_str = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp_str}] {json.dumps(log_entry, ensure_ascii=False)}\n"
            
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(log_line)
                
            # 同时输出到控制台（简化版）
            log_type = log_entry.get('type', 'unknown')
            action = log_entry.get('action', 'unknown')
            log_id = log_entry.get('log_id', 'N/A')
            print(f"[{timestamp_str}] STRUCTURED_LOG: {log_type}.{action} - {log_id}")
                
        except Exception as e:
            # 日志失败时回退到print
            print(f"Structured logging error: {e} - Entry: {log_entry}")
    
    def update_stats(self, category: str, success: bool) -> None:
        """更新统计信息"""
        if not self.stats_file:
            return
            
        try:
            stats = {}
            if self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    stats = json.load(f)
            
            # 初始化统计结构
            if category not in stats:
                stats[category] = {"total": 0, "success": 0, "failed": 0}
            
            # 更新统计
            stats[category]["total"] += 1
            if success:
                stats[category]["success"] += 1
            else:
                stats[category]["failed"] += 1
            
            # 更新最后操作时间
            stats["last_updated"] = dt.datetime.now().isoformat()
            
            # 写入统计文件
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Stats update error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.stats_file or not self.stats_file.exists():
            return {}
            
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Stats read error: {e}")
            return {}
    
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


class EmailOperationLogger:
    """邮件操作专用日志记录器 - 基于RotatingLogger"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 使用RotatingLogger作为底层实现
        email_log_path = self.log_dir / "email_operations.log"
        email_stats_path = self.log_dir / "email_stats.json"
        
        self.logger = RotatingLogger(
            str(email_log_path), 
            max_size_mb=5.0, 
            backup_lines=2000,
            stats_file=str(email_stats_path)
        )
    
    def _generate_log_id(self, prefix: str) -> str:
        """生成日志ID"""
        return f"{prefix}_{dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    
    def log_verification_email_attempt(self, email: str, code: str, verification_url: str, 
                                     smtp_config: Dict[str, Any]) -> str:
        """记录验证邮件发送尝试"""
        log_id = self._generate_log_id("verify")
        
        log_entry = {
            "log_id": log_id,
            "type": "verification_email",
            "action": "attempt",
            "email": email,
            "code": code,
            "verification_url": verification_url,
            "smtp_host": smtp_config.get('host', 'unknown'),
            "smtp_port": smtp_config.get('port', 'unknown'),
            "smtp_user": smtp_config.get('user', 'unknown'),
            "smtp_from": smtp_config.get('from', 'unknown'),
        }
        
        self.logger.log_structured(log_entry)
        return log_id
    
    def log_verification_email_result(self, log_id: str, success: bool, error: Optional[str] = None,
                                    smtp_response: Optional[str] = None):
        """记录验证邮件发送结果"""
        log_entry = {
            "log_id": log_id,
            "type": "verification_email",
            "action": "result",
            "success": success,
            "error": error,
            "smtp_response": smtp_response,
        }
        
        self.logger.log_structured(log_entry)
        self.logger.update_stats("verification_email", success)
    
    def log_management_email_attempt(self, email: str, verification_code: str, 
                                   smtp_config: Dict[str, Any]) -> str:
        """记录管理码邮件发送尝试"""
        log_id = self._generate_log_id("manage")
        
        log_entry = {
            "log_id": log_id,
            "type": "management_email",
            "action": "attempt",
            "email": email,
            "verification_code": verification_code,
            "smtp_host": smtp_config.get('host', 'unknown'),
            "smtp_port": smtp_config.get('port', 'unknown'),
            "smtp_user": smtp_config.get('user', 'unknown'),
            "smtp_from": smtp_config.get('from', 'unknown'),
        }
        
        self.logger.log_structured(log_entry)
        return log_id
    
    def log_management_email_result(self, log_id: str, success: bool, error: Optional[str] = None,
                                  smtp_response: Optional[str] = None):
        """记录管理码邮件发送结果"""
        log_entry = {
            "log_id": log_id,
            "type": "management_email",
            "action": "result",
            "success": success,
            "error": error,
            "smtp_response": smtp_response,
        }
        
        self.logger.log_structured(log_entry)
        self.logger.update_stats("management_email", success)
    
    def log_notification_email_attempt(self, email: str, code: str, old_status: str, 
                                     new_status: str, is_first_check: bool,
                                     smtp_config: Dict[str, Any]) -> str:
        """记录通知邮件发送尝试"""
        log_id = self._generate_log_id("notify")
        
        log_entry = {
            "log_id": log_id,
            "type": "notification_email",
            "action": "attempt",
            "email": email,
            "code": code,
            "old_status": old_status,
            "new_status": new_status,
            "is_first_check": is_first_check,
            "smtp_host": smtp_config.get('host', 'unknown'),
            "smtp_port": smtp_config.get('port', 'unknown'),
            "smtp_user": smtp_config.get('user', 'unknown'),
            "smtp_from": smtp_config.get('from', 'unknown'),
        }
        
        self.logger.log_structured(log_entry)
        return log_id
    
    def log_notification_email_result(self, log_id: str, success: bool, error: Optional[str] = None,
                                    smtp_response: Optional[str] = None):
        """记录通知邮件发送结果"""
        log_entry = {
            "log_id": log_id,
            "type": "notification_email",
            "action": "result",
            "success": success,
            "error": error,
            "smtp_response": smtp_response,
        }
        
        self.logger.log_structured(log_entry)
        self.logger.update_stats("notification_email", success)
    
    def log_smtp_connection_attempt(self, smtp_host: str, smtp_port: int, smtp_user: str) -> str:
        """记录SMTP连接尝试"""
        log_id = self._generate_log_id("smtp")
        
        log_entry = {
            "log_id": log_id,
            "type": "smtp_connection",
            "action": "attempt",
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_user": smtp_user,
        }
        
        self.logger.log_structured(log_entry)
        return log_id
    
    def log_smtp_connection_result(self, log_id: str, success: bool, error: Optional[str] = None,
                                 connection_reused: bool = False):
        """记录SMTP连接结果"""
        log_entry = {
            "log_id": log_id,
            "type": "smtp_connection",
            "action": "result",
            "success": success,
            "error": error,
            "connection_reused": connection_reused,
        }
        
        self.logger.log_structured(log_entry)
        self.logger.update_stats("smtp_connection", success)
    
    def log_smtp_auth_attempt(self, smtp_host: str, smtp_user: str) -> str:
        """记录SMTP认证尝试"""
        log_id = self._generate_log_id("auth")
        
        log_entry = {
            "log_id": log_id,
            "type": "smtp_auth",
            "action": "attempt",
            "smtp_host": smtp_host,
            "smtp_user": smtp_user,
        }
        
        self.logger.log_structured(log_entry)
        return log_id
    
    def log_smtp_auth_result(self, log_id: str, success: bool, error: Optional[str] = None):
        """记录SMTP认证结果"""
        log_entry = {
            "log_id": log_id,
            "type": "smtp_auth",
            "action": "result",
            "success": success,
            "error": error,
        }
        
        self.logger.log_structured(log_entry)
        self.logger.update_stats("smtp_auth", success)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取邮件发送统计"""
        return self.logger.get_stats()


# 全局邮件日志记录器实例
_email_logger = None


def get_email_logger(log_dir: str = "logs") -> EmailOperationLogger:
    """获取全局邮件日志记录器实例"""
    global _email_logger
    if _email_logger is None:
        _email_logger = EmailOperationLogger(log_dir)
    return _email_logger


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