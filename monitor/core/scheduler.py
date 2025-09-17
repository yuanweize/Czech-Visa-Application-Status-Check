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
    from ..notification import send_email
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
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.task_queue: List[ScheduledTask] = []
        self.browser_manager = BrowserManager()
        self.status_data = {}
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
                    return json.load(f)
            except Exception as e:
                self._log(f"Error loading status data: {e}")
        
        return {
            "generated_at": self._now_iso(),
            "items": {},
            "user_management": {
                "verification_codes": {},
                "pending_additions": {},
                "sessions": {}
            }
        }
    
    def save_status_data(self, data: Dict[str, Any]):
        """保存状态数据"""
        status_path = os.path.join(self.config.site_dir, "status.json")
        os.makedirs(self.config.site_dir, exist_ok=True)
        
        try:
            with open(status_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"Error saving status data: {e}")
    
    def rebuild_queue_from_status(self):
        """从状态文件重建队列（程序重启恢复）"""
        self.status_data = self.load_status_data()
        current_time = datetime.now()
        
        for code_config in self.config.codes:
            code = code_config.code
            item = self.status_data.get('items', {}).get(code)
            
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
        
        self._log(f"Rebuilt queue with {len(self.task_queue)} tasks")
    
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
        
        # 判断是否发生变化
        changed = old_status != new_status
        first_time = 'status' not in old_item
        
        # 计算下次检查时间
        freq_minutes = task.code_config.freq_minutes or self.config.default_freq_minutes
        next_check = datetime.now() + timedelta(minutes=freq_minutes)
        
        # 更新状态
        self.status_data.setdefault('items', {})[code] = {
            "code": code,
            "status": new_status,
            "last_checked": now,
            "last_changed": old_item.get("last_changed") if not changed else now,
            "next_check": next_check.isoformat(),
            "channel": "Email" if self._is_email_configured(task.code_config) else "",
            "target": task.code_config.target or "",
            "freq_minutes": freq_minutes,
            "note": task.code_config.note,
            "added_by": old_item.get("added_by"),
            "added_at": old_item.get("added_at")
        }
        
        # 保存状态
        self.status_data["generated_at"] = now
        self.save_status_data(self.status_data)
        
        self._log(f"Status updated: {code} -> {new_status} (changed: {changed})")
        
        # 发送邮件通知（如果需要）
        await self._send_email_notification(task, result, changed, old_status)
    
    async def _send_email_notification(self, task: ScheduledTask, result: Dict[str, Any], changed: bool, old_status: Optional[str]):
        """发送邮件通知"""
        if not EMAIL_AVAILABLE or not self._is_email_configured(task.code_config):
            return
            
        code = task.code_config.code
        new_status = result.get('status', 'Unknown')
        
        # 判断是否应该发送通知
        first_time = old_status is None
        should_notify, notif_label = should_send_notification(old_status, new_status, first_time)
        
        if not should_notify:
            return
            
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
            await send_email(
                to_email=task.code_config.target,
                subject=subject,
                body=body,
                smtp_config={
                    'host': self.config.smtp_host,
                    'port': self.config.smtp_port,
                    'user': self.config.smtp_user,
                    'pass': self.config.smtp_pass,
                    'from': self.config.smtp_from
                }
            )
            
            self._log(f"Email notification sent to {task.code_config.target} for {code}")
            
        except Exception as e:
            self._log(f"Failed to send email notification for {code}: {e}")
    
    def reload_config(self):
        """重新加载配置"""
        with self.config_lock:
            try:
                # 重新加载配置
                old_codes = set(c.code for c in self.config.codes)
                self.config = load_env_config()
                new_codes = set(c.code for c in self.config.codes)
                
                # 找出新增的代码
                added_codes = new_codes - old_codes
                if added_codes:
                    for code_config in self.config.codes:
                        if code_config.code in added_codes:
                            self.new_codes_to_check.append(code_config)
                    
                    self._log(f"Config reloaded: {len(added_codes)} new codes added")
                else:
                    self._log("Config reloaded: no changes")
                    
            except Exception as e:
                self._log(f"Failed to reload config: {e}")
    
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
    scheduler = PriorityScheduler(config)
    
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