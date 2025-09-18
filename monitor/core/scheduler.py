"""
高效的基于优先队列的签证查询调度器
Priority Queue-based Visa Query Scheduler

特性:
- 基于时间的小顶堆优先队列
- 浏览器会话复用与智能管理
- 并发处理与负载均衡
- 错误恢复与重新调度
- 持久化队列状态
"""

from __future__ import annotations

import asyncio
import heapq
import json
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from pathlib import Path


from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from .config import MonitorConfig, CodeConfig, load_env_config
from ..utils import create_logger, create_env_watcher, create_signal_handler
from ..server import create_server_thread
from ..notification import build_email_subject, build_email_body, should_send_notification

try:
    from ..notification import send_email_async
    from ..utils.logger import get_email_logger
    EMAIL_AVAILABLE = True
except ImportError:
    EMAIL_AVAILABLE = False

# 尝试导入API服务器
try:
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False


@dataclass
class ScheduledTask:
    """调度任务"""
    next_check: datetime
    code_config: CodeConfig
    priority: int = 0  # 0=normal, 1=high priority (new codes)
    retry_count: int = 0
    last_error: Optional[str] = None
    
    def __lt__(self, other):
        # 小顶堆比较: 优先级高的在前，时间早的在前
        if self.priority != other.priority:
            return self.priority > other.priority  # 数字大的优先级高
        return self.next_check < other.next_check


class BrowserManager:
    """浏览器会话管理器 - 汽车启停式复用"""
    
    def __init__(self, idle_timeout: int = 300):  # 5分钟空闲超时
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.last_used = datetime.now()
        self.idle_timeout = idle_timeout
        self.lock = asyncio.Lock()
        self.is_busy = False
        
    async def get_browser(self) -> Browser:
        """获取浏览器实例"""
        async with self.lock:
            now = datetime.now()
            
            # 检查是否需要重新创建
            if (self.browser is None or 
                (now - self.last_used).total_seconds() > self.idle_timeout):
                await self._recreate_browser()
            
            self.last_used = now
            self.is_busy = True
            return self.browser
    
    def update_last_used(self):
        """更新最后使用时间"""
        self.last_used = datetime.now()
        self.is_busy = False
    
    async def _recreate_browser(self):
        """重新创建浏览器"""
        # 关闭旧的
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
        
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
        
        # 创建新的
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
    
    async def cleanup(self):
        """清理资源"""
        if self.browser:
            try:
                await self.browser.close()
            except:
                pass
        
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
    
    def should_keep_alive(self) -> bool:
        """判断是否应该保持浏览器活跃"""
        if self.is_busy:
            return True
        
        idle_time = (datetime.now() - self.last_used).total_seconds()
        return idle_time < self.idle_timeout



class PriorityScheduler:
    """基于优先队列的智能调度器"""
    
    def __init__(self, config: MonitorConfig, env_path: str = ".env"):
        self.config = config
        self.env_path = env_path  # 保存env_path用于配置重载
        self.task_queue: List[ScheduledTask] = []
        self.browser_manager = BrowserManager()
        
        self.running = False
        self.stop_event = asyncio.Event()
        
        # 负载控制
        self.max_concurrent = 3  # 最大并发数
        self.min_interval = 60   # 最小间隔（秒）
        self.batch_window = 30   # 批处理窗口（秒）
        
        # 统计信息
        self.stats = {
            'processed': 0,
            'errors': 0,
            'browser_recreates': 0
        }
        
        # 创建日志记录器
        self.logger = create_logger(config.log_dir, "priority_scheduler")
        
        # 初始化状态数据 - 确保status.json存在
        self.status_data = self.load_status_data()
        
        # 配置重载相关
        self.config_lock = threading.Lock()
        self.env_watcher = None
        self.new_codes_to_check = []
        
        # 信号处理器
        self.signal_handler = create_signal_handler()
        self.signal_handler.add_shutdown_callback(self.graceful_shutdown)
        
    def _now_iso(self) -> str:
        """当前时间ISO格式"""
        return datetime.now().isoformat()
    
    def _log(self, message: str):
        """日志记录"""
        self.logger.log(message)
        # 同时输出到控制台以便实时查看
        timestamp = self._now_iso()
        print(f"[{timestamp}] {message}")
        
        # 写入日志文件
        log_path = os.path.join(self.config.log_dir, f"priority_scheduler_{datetime.now().date().isoformat()}.log")
        os.makedirs(self.config.log_dir, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    
    def load_status_data(self) -> Dict[str, Any]:
        """加载状态数据"""
        status_path = os.path.join(self.config.site_dir, "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
            except Exception as e:
                self._log(f"Error loading status data: {e}")
        
        # 创建默认结构并立即保存
        default_data = {
            "generated_at": self._now_iso(),
            "items": {},
            "user_management": {
                "verification_codes": {},
                "pending_additions": {},
                "sessions": {}
            }
        }
        
        # 立即保存默认结构
        self.save_status_data(default_data)
        self._log("Created initial status.json with default structure")
        
        return default_data
    
    def save_status_data(self, data: Dict[str, Any]):
        """保存状态数据"""
        status_path = os.path.join(self.config.site_dir, "status.json")
        os.makedirs(self.config.site_dir, exist_ok=True)
        
        try:
            with open(status_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"Error saving status data: {e}")
    
    def _initialize_codes_to_status(self, codes_to_add):
        """将新的codes初始化到status.json中"""
        try:
            current_time = self._now_iso()
            
            # 确保items字典存在
            if 'items' not in self.status_data:
                self.status_data['items'] = {}
            
            # 为每个新代码创建初始条目
            for code in codes_to_add:
                # 查找对应的配置
                code_config = None
                for cfg in self.config.codes:
                    if cfg.code == code:
                        code_config = cfg
                        break
                
                if code_config:
                    # 检查邮件是否正确配置
                    email_configured = (
                        code_config.channel == "email" and 
                        code_config.target and 
                        self.config.smtp_host and 
                        self.config.smtp_user and 
                        self.config.smtp_pass
                    )
                    
                    self.status_data['items'][code] = {
                        "code": code,
                        "status": "Pending/等待查询",  # 初始状态设置为等待查询
                        "last_checked": None,
                        "last_changed": None,
                        "next_check": current_time,  # 立即进行首次查询
                        "first_check": True,
                        "channel": "Email" if email_configured else "",
                        "target": code_config.target or "",
                        "freq_minutes": code_config.freq_minutes,
                        "note": getattr(code_config, 'note', '') or ""
                    }
                    self._log(f"Initialized code {code} in status.json")
            
            # 更新生成时间并保存
            self.status_data["generated_at"] = current_time
            self.save_status_data(self.status_data)
            
        except Exception as e:
            self._log(f"Error initializing codes to status: {e}")
    
    def rebuild_queue_from_status(self):
        """从状态文件重建队列（程序重启恢复）"""
        self.status_data = self.load_status_data()
        current_time = datetime.now()
        skipped_granted = 0
        
        # 检查是否需要初始化codes到status.json
        status_items = self.status_data.get('items', {})
        config_codes = {cfg.code for cfg in self.config.codes}
        existing_codes = set(status_items.keys())
        
        # 如果status.json中没有任何来自配置的codes，或者有新的codes，则初始化
        missing_codes = config_codes - existing_codes
        if missing_codes:
            self._log(f"Initializing {len(missing_codes)} new codes to status.json: {missing_codes}")
            self._initialize_codes_to_status(missing_codes)
            # 重新加载状态数据
            self.status_data = self.load_status_data()
            status_items = self.status_data.get('items', {})
        
        for code_config in self.config.codes:
            code = code_config.code
            item = status_items.get(code)
            
            # 检查是否为已通过状态，如果是则跳过
            if item and item.get('status'):
                status = item.get('status', '')
                if 'Granted' in status or '已通过' in status:
                    skipped_granted += 1
                    self._log(f"Skipping granted code from queue: {code} (status: {status})")
                    continue
            
            if item and item.get('next_check'):
                try:
                    next_check = datetime.fromisoformat(item['next_check'])
                    # 如果已经过期，设为立即检查
                    if next_check <= current_time:
                        next_check = current_time
                except:
                    # 无效时间，设为立即检查
                    next_check = current_time
            else:
                # 新代码，立即检查
                next_check = current_time
                
            task = ScheduledTask(
                next_check=next_check,
                code_config=code_config,
                priority=1 if next_check <= current_time else 0
            )
            heapq.heappush(self.task_queue, task)
        
        self._log(f"Rebuilt queue with {len(self.task_queue)} tasks (skipped {skipped_granted} granted codes)")
    
    def add_new_code(self, code_config: CodeConfig):
        """添加新代码（高优先级，立即检查）"""
        task = ScheduledTask(
            next_check=datetime.now(),
            code_config=code_config,
            priority=1  # 高优先级
        )
        heapq.heappush(self.task_queue, task)
        self._log(f"Added new high-priority code: {code_config.code}")
    
    def get_next_tasks(self) -> List[ScheduledTask]:
        """获取下一批要执行的任务"""
        if not self.task_queue:
            return []
        
        current_time = datetime.now()
        ready_tasks = []
        
        # 收集所有到期的任务
        while self.task_queue and self.task_queue[0].next_check <= current_time:
            task = heapq.heappop(self.task_queue)
            ready_tasks.append(task)
        
        # 检查批处理窗口内的任务
        cutoff_time = current_time + timedelta(seconds=self.batch_window)
        additional_tasks = []
        
        while (self.task_queue and 
               self.task_queue[0].next_check <= cutoff_time and
               len(ready_tasks) + len(additional_tasks) < self.max_concurrent):
            task = heapq.heappop(self.task_queue)
            additional_tasks.append(task)
        
        if additional_tasks:
            self._log(f"Batching {len(additional_tasks)} additional tasks within {self.batch_window}s window")
            ready_tasks.extend(additional_tasks)
        
        return ready_tasks
    
    def reschedule_task(self, task: ScheduledTask, success: bool = True):
        """重新调度任务"""
        # 检查当前状态是否为已通过，如果是则不再调度
        code = task.code_config.code
        current_item = self.status_data.get('items', {}).get(code)
        if current_item and current_item.get('status'):
            status = current_item.get('status', '')
            if 'Granted' in status or '已通过' in status:
                self._log(f"Code {code} is granted, not rescheduling for future checks")
                return
        
        if success:
            # 成功：计算下次检查时间
            freq_minutes = task.code_config.freq_minutes or self.config.default_freq_minutes
            next_check = datetime.now() + timedelta(minutes=freq_minutes)
            task.retry_count = 0
            task.last_error = None
        else:
            # 失败：指数退避重试
            task.retry_count += 1
            if task.retry_count <= 3:
                # 重试延迟: 1分钟, 2分钟, 4分钟
                delay_minutes = 2 ** (task.retry_count - 1)
                next_check = datetime.now() + timedelta(minutes=delay_minutes)
                self._log(f"Rescheduling failed task {task.code_config.code} for retry {task.retry_count} in {delay_minutes}min")
            else:
                # 超过重试次数，按正常频率调度
                freq_minutes = task.code_config.freq_minutes or self.config.default_freq_minutes
                next_check = datetime.now() + timedelta(minutes=freq_minutes)
                task.retry_count = 0
                self._log(f"Max retries reached for {task.code_config.code}, rescheduling normally")
        
        task.next_check = next_check
        task.priority = 0  # 重置为正常优先级
        heapq.heappush(self.task_queue, task)
    
    async def process_task(self, task: ScheduledTask) -> bool:
        """处理单个任务"""
        code = task.code_config.code
        self._log(f"Processing task: {code}")
        
        try:
            # 获取浏览器实例
            browser = await self.browser_manager.get_browser()
            
            # 动态导入cz模块 - 需要回到项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            sys.path.append(project_root)
            from query_modules.cz import query_code_with_browser
            
            # 调用查询模块
            status, timings = await query_code_with_browser(browser, code)
            
            # 更新浏览器最后使用时间
            self.browser_manager.update_last_used()
            
            # 创建result字典
            result = {
                'status': status,
                'timings': timings,
                'code': code,
                'timestamp': datetime.now().isoformat()
            }
            
            # 更新状态数据
            await self.update_status(task, result)
            
            # 发送通知（如果需要）
            await self.send_notification(task, result)
            
            self.stats['processed'] += 1
            self._log(f"Task completed successfully: {code} -> {status}")
            
            return True
            
        except Exception as e:
            self.stats['errors'] += 1
            task.last_error = str(e)
            self._log(f"Task failed: {code} -> {e}")
            return False
    
    async def update_status(self, task: ScheduledTask, result: Optional[Dict[str, Any]]):
        """更新状态数据"""
        code = task.code_config.code
        now = self._now_iso()
        
        # 获取旧状态
        old_item = self.status_data.get('items', {}).get(code, {})
        old_status = old_item.get('status')
        
        # 确定新状态
        if result and result.get('status'):
            new_status = result['status']
        else:
            new_status = "Query Failed / 查询失败"
        
        # 判断是否发生变化和是否首次查询
        changed = old_status != new_status
        is_first_check = old_item.get('first_check', False)
        
        # 计算下次检查时间
        freq_minutes = task.code_config.freq_minutes or self.config.default_freq_minutes
        
        # 如果状态为已通过，则不设置下次检查时间
        if 'Granted' in new_status or '已通过' in new_status:
            next_check_iso = None
            self._log(f"Code {code} is granted, no future checks scheduled")
        else:
            next_check = datetime.now() + timedelta(minutes=freq_minutes)
            next_check_iso = next_check.isoformat()
        
        # 更新状态
        updated_item = {
            "code": code,
            "status": new_status,
            "last_checked": now,
            "last_changed": old_item.get("last_changed") if not changed else now,
            "channel": "Email" if self._is_email_configured(task.code_config) else "",
            "target": task.code_config.target or "",
            "freq_minutes": freq_minutes,
            "note": task.code_config.note,
            "added_by": old_item.get("added_by"),
            "added_at": old_item.get("added_at")
        }
        
        # 只有非已通过状态才设置next_check
        if next_check_iso:
            updated_item["next_check"] = next_check_iso
        
        # Remove first_check flag after first successful query
        if is_first_check and new_status != "Query Failed / 查询失败":
            # First successful query completed, remove the flag
            pass  # Don't include first_check in updated_item
        elif is_first_check:
            # Still waiting for first successful query
            updated_item["first_check"] = True
            
        self.status_data.setdefault('items', {})[code] = updated_item
        
        # 保存状态
        self.status_data["generated_at"] = now
        self.save_status_data(self.status_data)
        
        self._log(f"Status updated: {code} -> {new_status} (changed: {changed})")
        
        # 发送邮件通知（如果需要）
        await self._send_email_notification(task, result, changed, old_status, is_first_check)
    
    async def _send_email_notification(self, task: ScheduledTask, result: Dict[str, Any], changed: bool, old_status: Optional[str], is_first_check: bool = False):
        """发送邮件通知"""
        if not EMAIL_AVAILABLE or not self._is_email_configured(task.code_config):
            return
            
        code = task.code_config.code
        new_status = result.get('status', 'Unknown')
        
        # 判断是否应该发送通知
        should_notify, notif_label = should_send_notification(old_status, new_status, is_first_check)
        
        if not should_notify:
            return
        
        logger = get_email_logger()
        
        # 准备SMTP配置
        smtp_config = {
            'host': self.config.smtp_host,
            'port': self.config.smtp_port,
            'user': self.config.smtp_user,
            'pass': self.config.smtp_pass,
            'from': self.config.smtp_from
        }
        
        # Log email attempt
        log_id = logger.log_notification_email_attempt(
            task.code_config.target, code, old_status or "None", new_status, is_first_check, smtp_config
        )
        
        try:
            # 构建邮件内容
            subject = build_email_subject(new_status, code)
            body = build_email_body(
                code=code,
                status=new_status,
                when=self._now_iso(),
                changed=changed,
                old_status=old_status,
                notif_label=notif_label
            )
            
            # 发送邮件
            success, error = await send_email_async(
                to_email=task.code_config.target,
                subject=subject,
                html_body=body,
                smtp_config=smtp_config
            )
            
            if success:
                # Log successful notification
                logger.log_notification_email_result(log_id, True, smtp_response="Notification sent successfully")
                self._log(f"Email notification sent to {task.code_config.target} for {code}")
            else:
                # Log failed notification
                logger.log_notification_email_result(log_id, False, error=error)
                self._log(f"Failed to send email notification for {code}: {error}")
            
        except Exception as e:
            error_msg = str(e)
            logger.log_notification_email_result(log_id, False, error=error_msg)
            self._log(f"Failed to send email notification for {code}: {e}")
    
    def reload_config(self):
        """重新加载配置 - 完整的差异化更新"""
        import time
        import json
        import os
        
        with self.config_lock:
            try:
                # 保存旧配置
                old_codes = {c.code: c for c in self.config.codes}
                
                # 添加重试机制处理文件编辑期间的竞态条件
                for attempt in range(3):
                    try:
                        new_config = load_env_config(self.env_path)
                        
                        # 安全检查：如果新配置代码为0但旧的有代码，可能是文件编辑中的临时状态
                        if len(new_config.codes) == 0 and len(old_codes) > 0:
                            if attempt < 2:  # 前两次重试
                                self._log(f"Warning: Got 0 codes during reload (attempt {attempt+1}), retrying...")
                                time.sleep(0.5)  # 等待500ms
                                continue
                            else:
                                self._log(f"Warning: Still got 0 codes after retries, proceeding anyway")
                        break
                    except ValueError as e:
                        # 配置文件有重复代码错误
                        self._log(f"Configuration reload failed due to duplicate codes: {e}")
                        raise e
                    except Exception as e:
                        if attempt < 2:
                            self._log(f"Config reload attempt {attempt+1} failed: {e}, retrying...")
                            time.sleep(0.5)
                            continue
                        else:
                            raise e
                
                # 构建新代码映射
                new_codes = {c.code: c for c in new_config.codes}
                
                # 计算差异
                added_codes = set(new_codes.keys()) - set(old_codes.keys())
                removed_codes = set(old_codes.keys()) - set(new_codes.keys())
                modified_codes = []
                
                # 检测修改的代码
                for code in set(old_codes.keys()) & set(new_codes.keys()):
                    old_c, new_c = old_codes[code], new_codes[code]
                    if (old_c.channel != new_c.channel or 
                        old_c.target != new_c.target or 
                        old_c.freq_minutes != new_c.freq_minutes or
                        getattr(old_c, 'note', '') != getattr(new_c, 'note', '')):
                        modified_codes.append(code)
                
                # 更新配置
                self.config = new_config
                
                # 处理新增代码
                if added_codes:
                    # 立即初始化新代码到status.json
                    self._initialize_codes_to_status(added_codes)
                    
                    for code_config in self.config.codes:
                        if code_config.code in added_codes:
                            self.new_codes_to_check.append(code_config)
                
                # 处理删除和修改的代码 - 更新status.json
                if removed_codes or modified_codes:
                    self._update_status_json_for_changes(removed_codes, modified_codes, new_codes)
                
                # 记录变更
                change_summary = []
                if added_codes:
                    change_summary.append(f"added {len(added_codes)}")
                if removed_codes:
                    change_summary.append(f"removed {len(removed_codes)}")
                if modified_codes:
                    change_summary.append(f"modified {len(modified_codes)}")
                
                changes_str = ", ".join(change_summary) if change_summary else "no changes"
                self._log(f"Configuration reloaded: {len(old_codes)} -> {len(new_codes)} codes ({changes_str})")
                
                if added_codes:
                    self._log(f"New codes for immediate checking: {list(added_codes)}")
                if removed_codes:
                    self._log(f"Removed codes: {list(removed_codes)}")
                if modified_codes:
                    self._log(f"Modified codes: {modified_codes}")
                    
            except Exception as e:
                self._log(f"Failed to reload config: {e}")
                raise e
                
    def _update_status_json_for_changes(self, removed_codes, modified_codes, new_codes):
        """更新status.json以反映删除和修改的代码"""
        try:
            site_json_path = os.path.join(self.config.site_dir, "status.json")
            if os.path.exists(site_json_path):
                with open(site_json_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        # Empty file, skip update
                        return
                    status_data = json.loads(content)
                
                # 删除已移除的代码
                for code in removed_codes:
                    if code in status_data.get("items", {}):
                        del status_data["items"][code]
                        self._log(f"Removed code {code} from status.json")
                
                # 更新修改的代码的通知配置
                for code in modified_codes:
                    if code in status_data.get("items", {}) and code in new_codes:
                        new_code_cfg = new_codes[code]
                        # 检查邮件是否正确配置
                        email_configured = (
                            new_code_cfg.channel == "email" and 
                            new_code_cfg.target and 
                            self.config.smtp_host and 
                            self.config.smtp_user and 
                            self.config.smtp_pass
                        )
                        
                        # 更新通知渠道和目标
                        status_data["items"][code]["channel"] = "Email" if email_configured else ""
                        status_data["items"][code]["target"] = new_code_cfg.target or ""
                        status_data["items"][code]["freq_minutes"] = new_code_cfg.freq_minutes
                        status_data["items"][code]["note"] = getattr(new_code_cfg, 'note', '') or ""
                        self._log(f"Updated notification config for code {code}")
                
                # 更新生成时间
                status_data["generated_at"] = datetime.now().isoformat()
                
                # 写回文件
                with open(site_json_path, "w", encoding="utf-8") as f:
                    json.dump(status_data, f, ensure_ascii=False, indent=2)
                    
        except Exception as e:
            self._log(f"Error updating status.json for changes: {e}")
    
    def graceful_shutdown(self):
        """优雅关闭"""
        self._log("Initiating graceful shutdown...")
        self.running = False
        self.stop_event.set()
        
        # 停止环境文件监控
        if self.env_watcher:
            self.env_watcher.stop()
    
    def _is_email_configured(self, code_config: CodeConfig) -> bool:
        """检查邮件是否配置"""
        return (code_config.channel == "email" and 
                code_config.target and 
                self.config.smtp_host and 
                self.config.smtp_user and 
                self.config.smtp_pass)
    
    async def send_notification(self, task: ScheduledTask, result: Optional[Dict[str, Any]]):
        """发送通知（占位符）"""
        # TODO: 实现邮件通知逻辑
        pass
    
    async def run(self):
        """主运行循环"""
        self.running = True
        self._log("Priority scheduler started")
        
        # 重建队列
        self.rebuild_queue_from_status()
        
        try:
            while self.running and not self.stop_event.is_set():
                # 获取下一批任务
                tasks = self.get_next_tasks()
                
                if not tasks:
                    # 没有任务，等待一段时间
                    if self.task_queue:
                        # 计算到下一个任务的等待时间
                        next_task_time = self.task_queue[0].next_check
                        wait_seconds = max(1, (next_task_time - datetime.now()).total_seconds())
                        wait_seconds = min(wait_seconds, 300)  # 最多等待5分钟
                        self._log(f"No ready tasks, waiting {wait_seconds:.1f}s for next task")
                    else:
                        wait_seconds = 60  # 没有任务时等待1分钟
                        self._log("No tasks in queue, waiting 60s")
                    
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=wait_seconds)
                        break  # 收到停止信号
                    except asyncio.TimeoutError:
                        continue  # 超时，继续循环
                
                # 并发处理任务
                self._log(f"Processing {len(tasks)} tasks concurrently")
                
                # 添加随机抖动避免同时查询
                for i, task in enumerate(tasks):
                    if i > 0:
                        await asyncio.sleep(1)  # 1秒间隔
                
                # 并发执行
                results = await asyncio.gather(
                    *[self.process_task(task) for task in tasks],
                    return_exceptions=True
                )
                
                # 重新调度任务
                for task, success in zip(tasks, results):
                    if isinstance(success, Exception):
                        success = False
                        task.last_error = str(success)
                    
                    self.reschedule_task(task, success)
                
                # 清理空闲浏览器
                if not self.browser_manager.should_keep_alive():
                    await self.browser_manager.cleanup()
                
                # 打印统计信息
                self._log(f"Stats: processed={self.stats['processed']}, errors={self.stats['errors']}, queue_size={len(self.task_queue)}")
        
        except Exception as e:
            self._log(f"Scheduler error: {e}")
        
        finally:
            await self.cleanup()
    
    async def stop(self):
        """停止调度器"""
        self._log("Stopping priority scheduler...")
        self.running = False
        self.stop_event.set()
    
    async def cleanup(self):
        """清理资源"""
        await self.browser_manager.cleanup()
        self._log("Priority scheduler stopped")


async def run_priority_scheduler(env_path: str = ".env", once: bool = False):
    """运行优先队列调度器"""
    
    # 加载配置
    config = load_env_config(env_path)
    
    if not config.codes:
        print("No codes configured. Exiting.")
        return
    
    # 创建调度器
    scheduler = PriorityScheduler(config, env_path)
    
    if once:
        # 单次运行模式：处理所有到期任务
        scheduler.rebuild_queue_from_status()
        tasks = scheduler.get_next_tasks()
        
        if tasks:
            print(f"Processing {len(tasks)} tasks in once mode")
            results = await asyncio.gather(
                *[scheduler.process_task(task) for task in tasks],
                return_exceptions=True
            )
            print(f"Completed: {sum(1 for r in results if r is True)} successful, {sum(1 for r in results if r is not True)} failed")
        else:
            print("No tasks ready for processing")
        
        await scheduler.cleanup()
    else:
        # 持续运行模式
        # 启动环境文件监控
        scheduler.env_watcher = create_env_watcher(env_path, scheduler.reload_config)
        
        # 启动HTTP服务器（如果配置了serve）
        server_thread = None
        stop_evt = None
        
        if config.serve:
            server_thread, stop_evt = create_server_thread(
                config.site_dir, 
                config.site_port, 
                scheduler._log, 
                env_path
            )
            server_thread.start()
            
        print(f"Priority Scheduler starting. SERVE={config.serve} SITE_DIR={config.site_dir} SITE_PORT={config.site_port}")
        if scheduler.env_watcher:
            scheduler._log("Environment file hot reloading enabled")
        
        try:
            # 运行调度器主循环
            await scheduler.run()
        except KeyboardInterrupt:
            print("\nShutdown requested by user")
        finally:
            # 清理
            await scheduler.cleanup()
            if server_thread and stop_evt:
                stop_evt.set()
                server_thread.join(timeout=5)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Priority Queue Visa Scheduler")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--env", default=".env", help="Environment file path")
    
    args = parser.parse_args()
    
    asyncio.run(run_priority_scheduler(args.env, args.once))