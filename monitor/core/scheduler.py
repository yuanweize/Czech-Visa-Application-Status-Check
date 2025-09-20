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
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from .config import MonitorConfig, CodeConfig, load_env_config
from .code_manager import CodeStorageManager, ManagedCode
from ..utils import create_logger, create_env_watcher, create_signal_handler
from ..server import create_server_thread
from ..notification import build_email_subject, build_email_body, should_send_notification

# 导入CZ查询器接口
try:
    # 添加项目根目录到路径以便导入CZ模块
    import sys
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if _project_root not in sys.path:
        sys.path.append(_project_root)
    from query_modules.cz import query_codes_async
    CZ_AVAILABLE = True
except ImportError:
    CZ_AVAILABLE = False

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


class PriorityScheduler:
    """基于优先队列的智能调度器 - 使用CZ查询器的共享浏览器架构"""
    
    def __init__(self, config: MonitorConfig, env_path: str = ".env", use_signal_handler: bool = True):
        self.config = config
        self.env_path = env_path  # 保存env_path用于配置重载
        self.task_queue: List[ScheduledTask] = []
        
        self.running = False
        self.stop_event = asyncio.Event()
        # Event loop reference for thread-safe wake-ups from file watcher threads
        self.loop = None  # type: Optional[asyncio.AbstractEventLoop]
        
        # 负载控制
        self.max_concurrent = 3  # 最大并发数
        self.min_interval = 60   # 最小间隔（秒）
        self.batch_window = 30   # 批处理窗口（秒）
        
        # 统计信息
        self.stats = {
            'processed': 0,
            'errors': 0
        }
        
        # 创建日志记录器
        self.logger = create_logger(config.log_dir, "priority_scheduler")

        # 代码存储管理器（新架构：site/config/status.json & users.json）
        self.store = CodeStorageManager(self.config.site_dir)
        self.store.ensure_initialized()
        # 初始化状态数据 - 从新路径加载
        self.status_data = self.load_status_data()
        # 当前默认频率（用于检测 DEFAULT_FREQ_MINUTES 变更）
        self._current_default_freq = self.config.default_freq_minutes
        
        # 配置重载相关
        self.config_lock = threading.Lock()
        self.env_watcher = None
        self.new_codes_to_check = []
        self.new_codes_event = asyncio.Event()  # 新增：用于唤醒主循环
        
        # 信号处理器（可选，用于常驻模式）
        self.signal_handler = None
        if use_signal_handler:
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

    @staticmethod
    def _is_granted_status(status: Optional[str]) -> bool:
        """Return True if status indicates a terminal success/approval (Granted/已通过)."""
        if not status:
            return False
        return ('Granted' in status) or ('已通过' in status)

    @staticmethod
    def _is_terminal_status(status: Optional[str]) -> bool:
        """Return True if status indicates no further checks are needed (Granted/已通过 or Rejected/被拒绝)."""
        if not status:
            return False
        return (
            ('Granted' in status) or ('已通过' in status) or
            ('Rejected' in status) or ('被拒绝' in status)
        )

    def _wake_event(self, event: asyncio.Event) -> None:
        """Safely set an asyncio.Event from any thread/context."""
        try:
            if getattr(self, 'loop', None) and self.loop and getattr(self.loop, 'is_running', lambda: False)():
                self.loop.call_soon_threadsafe(event.set)
            else:
                event.set()
        except Exception:
            try:
                event.set()
            except Exception:
                pass

    @staticmethod
    def _format_eta(seconds: float) -> str:
        """将秒转换为简洁的人类可读字符串，如 '31m 0s', '2h 5m', '1d 3h'"""
        try:
            total = int(max(0, round(seconds)))
            mins, sec = divmod(total, 60)
            hrs, mins = divmod(mins, 60)
            days, hrs = divmod(hrs, 24)
            if days > 0:
                return f"{days}d {hrs}h"
            if hrs > 0:
                return f"{hrs}h {mins}m"
            return f"{mins}m {sec}s"
        except Exception:
            return f"{seconds:.0f}s"
    
    def load_status_data(self) -> Dict[str, Any]:
        """加载状态数据"""
        try:
            data = self.store.load_status()
            return data
        except Exception as e:
            self._log(f"Error loading status data: {e}")
            data = {'generated_at': self._now_iso(), 'items': {}}
            self.save_status_data(data)
            return data
    
    def save_status_data(self, data: Dict[str, Any]):
        """保存状态数据"""
        try:
            # 仅保存到 env 管理的 status.json（site/config/status.json）
            self.store.save_status(data)
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
        
        # 初始化缺失的 env codes 到 status.json（不影响用户 codes）
        status_items = self.status_data.get('items', {})
        config_codes = {cfg.code for cfg in self.config.codes}
        existing_codes = set(status_items.keys())
        missing_codes = config_codes - existing_codes
        if missing_codes:
            self._log(f"Initializing {len(missing_codes)} new codes to status.json: {missing_codes}")
            self._initialize_codes_to_status(missing_codes)
            self.status_data = self.load_status_data()
            status_items = self.status_data.get('items', {})

        # 合并 env 与 user codes 作为调度来源
        managed_list: List[ManagedCode] = self.store.merge_codes(self.config)
        # 建立查找映射以便从 item 获取
        env_items = status_items
        users = self.store.load_users()
        user_items = users.get('codes', {})

        for managed in managed_list:
            code_config = managed.config
            code = code_config.code
            item = env_items.get(code) if managed.origin == 'env' else user_items.get(code)
            
            # 检查是否为终止状态（已通过/被拒绝），如果是则跳过
            if item and item.get('status'):
                status = item.get('status', '')
                if self._is_terminal_status(status):
                    skipped_granted += 1
                    self._log(f"Skipping terminal code from queue: {code} (status: {status})")
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
    
    def sync_status_with_config(self):
        """Sync status.json with current .env config strictly for env-managed codes.

        - Ensure all env-configured codes exist in status.json (add missing)
        - Remove any non-env codes lingering in status.json (user/test leftovers)
          User-managed codes belong in users.json and will be preserved there.
        - Align env items' notification fields and freq_minutes with .env values
          (channel/target/freq_minutes/note), and recompute next_check when needed.
        """
        try:
            status = self.store.load_status()
            users = self.store.load_users()
            items = status.get('items', {}) or {}
            cfg_map = {c.code: c for c in (self.config.codes or [])}
            cfg_codes = set(cfg_map.keys())

            # 1) Add missing env codes
            missing = cfg_codes - set(items.keys())
            if missing:
                self._initialize_codes_to_status(missing)
                status = self.store.load_status()
                items = status.get('items', {}) or {}

            # 2) Remove non-env codes from env-managed status.json (migrate was already done earlier if any)
            to_remove = [code for code in list(items.keys()) if code not in cfg_codes]
            removed_count = 0
            if to_remove:
                for code in to_remove:
                    # If code also exists in users.json, we certainly should not keep it in env status.
                    # If not in users.json, it's likely test/legacy residue and should be pruned from env file.
                    items.pop(code, None)
                    removed_count += 1
                status['items'] = items
                status['generated_at'] = self._now_iso()
                self.store.save_status(status)
                self._log(f"Pruned {removed_count} non-env codes from status.json: {to_remove}")

            # 3) Align env items with .env config values
            updated_count = 0
            now_dt = datetime.now()
            for code, cfg in cfg_map.items():
                item = items.get(code)
                if not item:
                    continue
                # Update notification fields
                email_ok = (
                    cfg.channel == 'email' and cfg.target and self.config.smtp_host and self.config.smtp_user and self.config.smtp_pass
                )
                desired_channel = 'Email' if email_ok else ''
                desired_target = cfg.target or ''
                desired_freq = cfg.freq_minutes if cfg.freq_minutes is not None else item.get('freq_minutes', self.config.default_freq_minutes)
                desired_note = getattr(cfg, 'note', '') or ''

                changed = False
                # Remove user-only metadata for env-managed items
                if 'added_by' in item:
                    item.pop('added_by', None)
                    changed = True
                if 'added_at' in item:
                    item.pop('added_at', None)
                    changed = True
                if item.get('channel') != desired_channel:
                    item['channel'] = desired_channel
                    changed = True
                if item.get('target') != desired_target:
                    item['target'] = desired_target
                    changed = True
                if item.get('freq_minutes') != desired_freq:
                    item['freq_minutes'] = desired_freq
                    changed = True
                if item.get('note') != desired_note:
                    item['note'] = desired_note
                    changed = True

                # Recompute/clear next_check depending on terminal state
                status_str = item.get('status', '')
                if self._is_terminal_status(status_str):
                    if 'next_check' in item:
                        item.pop('next_check', None)
                        changed = True
                else:
                    need_recompute = changed or (not item.get('next_check'))
                    if need_recompute:
                        lc = item.get('last_checked')
                        try:
                            base_dt = datetime.fromisoformat(lc) if lc else now_dt
                        except Exception:
                            base_dt = now_dt
                        next_check_dt = base_dt + timedelta(minutes=desired_freq)
                        item['next_check'] = next_check_dt.isoformat()
                        changed = True

                if changed:
                    updated_count += 1

            if updated_count > 0:
                status['generated_at'] = self._now_iso()
                self.store.save_status(status)
                self._log(f"Aligned {updated_count} env items with .env config in status.json")

            # Sync memory
            self.status_data = status
        except Exception as e:
            self._log(f"Error during status/config sync: {e}")

    def _reschedule_queue_for_codes(self, codes_to_resched: List[str], new_codes_map: Dict[str, CodeConfig]):
        """Recompute next_check and re-heap tasks for modified codes (e.g., freq_minutes change)."""
        if not codes_to_resched:
            return
        now = datetime.now()
        # remove existing entries for these codes
        if self.task_queue:
            self.task_queue = [t for t in self.task_queue if t.code_config.code not in codes_to_resched]
            heapq.heapify(self.task_queue)
        # push new entries with recomputed times
        for code in codes_to_resched:
            cfg = new_codes_map.get(code)
            if not cfg:
                continue
            item = (self.status_data.get('items', {}) or {}).get(code, {})
            status = item.get('status', '') if isinstance(item, dict) else ''
            if self._is_granted_status(status):
                continue
            base_dt = None
            lc = item.get('last_checked') if isinstance(item, dict) else None
            if lc:
                try:
                    base_dt = datetime.fromisoformat(lc)
                except Exception:
                    base_dt = None
            if base_dt is None:
                base_dt = now
            freq = cfg.freq_minutes or self.config.default_freq_minutes
            next_check = base_dt + timedelta(minutes=freq)
            priority = 1 if next_check <= now else 0
            if next_check <= now:
                next_check = now
            heapq.heappush(self.task_queue, ScheduledTask(next_check=next_check, code_config=cfg, priority=priority))
        # wake main loop to apply new ordering immediately
        self._wake_event(self.new_codes_event)
    
    def add_new_code(self, code_config: CodeConfig):
        """添加新代码（高优先级，立即检查）"""
        task = ScheduledTask(
            next_check=datetime.now(),
            code_config=code_config,
            priority=1  # 高优先级
        )
        heapq.heappush(self.task_queue, task)
        self._log(f"Added new high-priority code: {code_config.code}")
        # 唤醒主循环，确保立即处理
        self._wake_event(self.new_codes_event)
    
    def get_next_tasks(self) -> List[ScheduledTask]:
        """获取下一批要执行的任务"""
        ready_tasks = []
        
        # 首先处理新增的代码（立即处理）
        if self.new_codes_to_check:
            self._log(f"Processing {len(self.new_codes_to_check)} new codes immediately")
            for code_config in self.new_codes_to_check:
                task = ScheduledTask(
                    next_check=datetime.now(),
                    code_config=code_config,
                    priority=1
                )
                ready_tasks.append(task)
            self.new_codes_to_check.clear()  # 清空已处理的新代码
            return ready_tasks  # 立即返回新代码任务
        
        # 如果没有新代码，处理正常的定时任务
        if not self.task_queue:
            return []
        
        current_time = datetime.now()
        
        # 收集所有到期的任务
        while self.task_queue and self.task_queue[0].next_check <= current_time:
            task = heapq.heappop(self.task_queue)
            ready_tasks.append(task)
        
        # 检查批处理窗口内的任务 - 取更多任务进行批处理
        cutoff_time = current_time + timedelta(seconds=self.batch_window)
        
        while (self.task_queue and 
               self.task_queue[0].next_check <= cutoff_time and
               len(ready_tasks) < self.max_concurrent):
            task = heapq.heappop(self.task_queue)
            ready_tasks.append(task)
        
        if len(ready_tasks) > 0:
            immediate_count = sum(1 for t in ready_tasks if t.next_check <= current_time)
            batched_count = len(ready_tasks) - immediate_count
            if batched_count > 0:
                self._log(f"Batching {batched_count} additional tasks within {self.batch_window}s window")
        
        return ready_tasks
    
    def reschedule_task(self, task: ScheduledTask, success: bool = True):
        """重新调度任务"""
        # 检查当前状态是否为终止状态（已通过/被拒绝），如果是则不再调度
        code = task.code_config.code
        current_item = self.status_data.get('items', {}).get(code)
        if current_item and current_item.get('status'):
            status = current_item.get('status', '')
            if self._is_terminal_status(status):
                self._log(f"Code {code} is terminal ({status}), not rescheduling for future checks")
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
    
    async def process_tasks_batch(self, tasks: list[ScheduledTask]) -> list[bool]:
        """批量处理任务 - 直接调用CZ查询器的第三方接口"""
        if not tasks:
            return []
        
        if not CZ_AVAILABLE:
            self._log("CZ query module not available")
            return [False] * len(tasks)
        
        codes = [task.code_config.code for task in tasks]
        task_map = {task.code_config.code: task for task in tasks}
        completed_codes = set()
        
        self._log(f"Batch processing {len(tasks)} tasks using CZ query API")
        
        try:
            # 实时结果回调 - 查到一个立即处理一个
            async def on_result(code: str, status: str, error: str, attempts: int, timings: dict):
                """实时处理查询结果 - CZ查询器查到一个立即回调一个"""
                completed_codes.add(code)
                task = task_map.get(code)
                if task:
                    result = {
                        'status': status,
                        'timings': timings,
                        'code': code,
                        'timestamp': datetime.now().isoformat(),
                        'attempts': attempts,
                        'error': error
                    }
                    
                    # 立即更新状态数据
                    await self.update_status(task, result)
                    
                    self.stats['processed'] += 1
            
            # 直接调用CZ查询器的第三方接口（可取消）
            cz_task = asyncio.create_task(query_codes_async(
                codes=codes,
                headless=self.config.headless,
                workers=self.config.workers,
                retries=3,
                result_callback=on_result,
                suppress_cli=True
            ))

            try:
                # 等待查询完成或收到停止事件
                await asyncio.wait_for(asyncio.shield(cz_task), timeout=None)
            except asyncio.CancelledError:
                self._log("Batch processing cancelled")
            except Exception as e:
                # 如果是停止事件触发，允许优雅退出
                if self.stop_event.is_set():
                    self._log("Batch processing interrupted by stop event")
                else:
                    raise
            
            # 返回结果：完成的返回True，未完成的返回False
            results = []
            for task in tasks:
                if task.code_config.code in completed_codes:
                    results.append(True)
                else:
                    results.append(False)  # 被中断的任务，不标记为失败
            
            return results
            
        except KeyboardInterrupt:
            # 被中断时，已完成的任务保持完成状态，未完成的保持原状态
            self._log("Batch processing interrupted by user, completed tasks preserved")
            results = []
            for task in tasks:
                if task.code_config.code in completed_codes:
                    results.append(True)
                else:
                    results.append(False)  # 未完成，但不是失败
            return results
        except Exception as e:
            self._log(f"Batch processing failed: {e}")
            self.stats['errors'] += len(tasks)
            for task in tasks:
                task.last_error = str(e)
            return [False] * len(tasks)
        finally:
            # 批处理完成后，清理浏览器资源
            try:
                if CZ_AVAILABLE:
                    import query_modules.cz as cz
                    if hasattr(cz, 'cleanup_browser'):
                        await cz.cleanup_browser()
                        self._log("Browser cleanup completed after batch processing")
            except Exception as cleanup_error:
                self._log(f"Error during browser cleanup: {cleanup_error}")
    
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
            new_status = "Query Failed/查询失败"
        
        # 判断是否发生变化和是否首次查询
        changed = old_status != new_status
        # 更稳健的首次判断：标记位或从未检查过(last_checked为空)
        is_first_check = old_item.get('first_check', False) or (old_item.get('last_checked') in (None, '', 0))
        
        # 计算下次检查时间
        freq_minutes = task.code_config.freq_minutes or self.config.default_freq_minutes
        
        # 如果状态为终止（已通过/被拒绝），则不设置下次检查时间
        if self._is_terminal_status(new_status):
            next_check_iso = None
            self._log(f"Code {code} is terminal ({new_status}), no future checks scheduled")
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
            "note": task.code_config.note
        }
        
        # 只有非已通过状态才设置next_check
        if next_check_iso:
            updated_item["next_check"] = next_check_iso
        
        # Remove first_check flag after first successful query
        if is_first_check and new_status != "Query Failed/查询失败":
            # First successful query completed, remove the flag
            pass  # Don't include first_check in updated_item
        elif is_first_check:
            # Still waiting for first successful query
            updated_item["first_check"] = True
            
        self.status_data.setdefault('items', {})[code] = updated_item
        
        # 保存状态（根据来源写回对应文件）
        # 判断该 code 是否来自 env（status.json）还是用户（users.json）
        origin = 'env'
        # 优先根据配置中是否存在判断
        if not any(c.code == code for c in self.config.codes):
            origin = 'user'
        # 允许通过存储层再次确认
        merged = self.store.merge_codes(self.config)
        for m in merged:
            if m.code == code:
                origin = m.origin
                break
        # 写入对应存储
        # 针对用户来源，确保channel/target规范（不再使用单独的email字段）
        if origin == 'user':
            updated_item['channel'] = 'email' if self._is_email_configured(task.code_config) else ''
            if not updated_item.get('target'):
                try:
                    users_data = self.store.load_users()
                    rec = (users_data.get('codes') or {}).get(code)
                    if isinstance(rec, dict) and rec.get('target'):
                        updated_item['target'] = rec.get('target')
                except Exception:
                    pass
            # 确保不写入 email 键
            updated_item.pop('email', None)
            # For user-managed entries, preserve metadata if it exists
            if old_item.get('added_by') is not None:
                updated_item['added_by'] = old_item.get('added_by')
            if old_item.get('added_at') is not None:
                updated_item['added_at'] = old_item.get('added_at')
        else:
            # For env-managed entries, ensure user-only metadata is not present
            updated_item.pop('added_by', None)
            updated_item.pop('added_at', None)
        self.store.update_item(origin, code, updated_item)
        # 同步内存
        if origin == 'env':
            self.status_data.setdefault('items', {})[code] = updated_item
            self.status_data['generated_at'] = now
        
        
        self._log(f"Status updated: {code} -> {new_status} (changed: {changed})")
        
        # 发送邮件通知（如果需要）- 后台异步执行，避免阻塞查询流水线
        try:
            # 调试：打印一次邮件决策（仅在首次或变化时会发送）
            # 注意：正式环境可考虑降级为更少的日志
            asyncio.create_task(self._send_email_notification(task, result, changed, old_status, is_first_check))
        except Exception:
            pass
    
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
                
                # 检测默认频率是否变化
                default_changed = (self._current_default_freq != new_config.default_freq_minutes)
                # 更新配置
                self.config = new_config
                if default_changed:
                    self._current_default_freq = new_config.default_freq_minutes
                
                # 处理新增代码
                if added_codes:
                    # 立即初始化新代码到status.json
                    self._initialize_codes_to_status(added_codes)
                    
                    for code_config in self.config.codes:
                        if code_config.code in added_codes:
                            self.new_codes_to_check.append(code_config)
                    
                    # 唤醒主循环立即处理新代码（跨线程安全）
                    self._wake_event(self.new_codes_event)
                
                # 处理删除和修改的代码 - 更新status.json（仅 env 部分）
                if removed_codes or modified_codes:
                    self._update_status_json_for_changes(removed_codes, modified_codes, new_codes)
                    # 频率修改后需要重新排序队列
                    if modified_codes:
                        self._reschedule_queue_for_codes(modified_codes, new_codes)

                # 如果默认频率变更，则对所有使用默认频率的代码（env 与 user）重新计算 next_check 并重排队列
                if default_changed:
                    try:
                        self._log(f"DEFAULT_FREQ_MINUTES changed -> {self._current_default_freq}, rescheduling items using default")
                        now_dt = datetime.now()
                        to_reheap_codes: List[str] = []
                        # Env items（仅当CodeConfig未指定freq_minutes时使用默认）
                        status = self.store.load_status()
                        items = status.get('items', {}) or {}
                        for ccode, item in items.items():
                            cfg = new_codes.get(ccode)
                            if not cfg:
                                continue
                            if cfg.freq_minutes is None:
                                lc = item.get('last_checked')
                                try:
                                    base_dt = datetime.fromisoformat(lc) if lc else now_dt
                                except Exception:
                                    base_dt = now_dt
                                item['freq_minutes'] = self._current_default_freq
                                item['next_check'] = (base_dt + timedelta(minutes=self._current_default_freq)).isoformat()
                                to_reheap_codes.append(ccode)
                        status['generated_at'] = datetime.now().isoformat()
                        self.store.save_status(status)

                        # User items（缺失freq或标记uses_default_freq=True的随默认变化）
                        users = self.store.load_users()
                        ucodes = users.get('codes', {}) or {}
                        for ccode, urec in ucodes.items():
                            uses_default = (urec.get('freq_minutes') in (None, '')) or bool(urec.get('uses_default_freq', True))
                            if uses_default:
                                lc = urec.get('last_checked')
                                try:
                                    base_dt = datetime.fromisoformat(lc) if lc else now_dt
                                except Exception:
                                    base_dt = now_dt
                                urec['freq_minutes'] = self._current_default_freq
                                urec['uses_default_freq'] = True
                                urec['next_check'] = (base_dt + timedelta(minutes=self._current_default_freq)).isoformat()
                                if not urec.get('channel'):
                                    urec['channel'] = 'email'
                                to_reheap_codes.append(ccode)
                        users['generated_at'] = datetime.now().isoformat()
                        self.store.save_users(users)

                        # 构造用于重排的CodeConfig映射
                        targets_map: Dict[str, CodeConfig] = {}
                        for code in to_reheap_codes:
                            if code in new_codes:
                                targets_map[code] = new_codes[code]
                            else:
                                rec = ucodes.get(code, {})
                                target_val = rec.get('target')
                                targets_map[code] = CodeConfig(code=code, channel='email', target=target_val, freq_minutes=self._current_default_freq)
                        self._reschedule_queue_for_codes(to_reheap_codes, targets_map)
                    except Exception as e:
                        self._log(f"Error during default freq reschedule: {e}")

                # 从内存队列中移除被删除的代码任务，保持与配置一致
                if removed_codes:
                    before_q = len(self.task_queue)
                    if before_q:
                        self.task_queue = [t for t in self.task_queue if t.code_config.code not in removed_codes]
                        heapq.heapify(self.task_queue)
                        removed_q = before_q - len(self.task_queue)
                        if removed_q > 0:
                            self._log(f"Removed {removed_q} queued tasks for deleted codes: {list(removed_codes)}")
                    # 同时清理待立即处理的新代码列表
                    if self.new_codes_to_check:
                        before_new = len(self.new_codes_to_check)
                        self.new_codes_to_check = [c for c in self.new_codes_to_check if c.code not in removed_codes]
                        after_new = len(self.new_codes_to_check)
                        if after_new < before_new:
                            self._log("Purged removed codes from pending-new list")
                
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
        # Reload 完成后，同步（仅补齐缺失的 env codes，不再清理多余项）
        self.sync_status_with_config()
                
    def _update_status_json_for_changes(self, removed_codes, modified_codes, new_codes):
        """更新status.json以反映删除和修改的代码"""
        try:
            status_data = self.store.load_status()

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
                    # 若非已通过，基于 last_checked + 新频率 重新计算 next_check
                    try:
                        st = status_data["items"][code].get("status", "")
                        if not ("Granted" in st or "已通过" in st or "Rejected" in st or "被拒绝" in st):
                            lc = status_data["items"][code].get("last_checked")
                            base_dt = datetime.fromisoformat(lc) if lc else datetime.now()
                            freq = new_code_cfg.freq_minutes or self.config.default_freq_minutes
                            status_data["items"][code]["next_check"] = (base_dt + timedelta(minutes=freq)).isoformat()
                    except Exception:
                        pass

            # 更新生成时间
            status_data["generated_at"] = datetime.now().isoformat()

            # 写回文件并同步内存
            self.store.save_status(status_data)
            self.status_data = status_data

        except Exception as e:
            self._log(f"Error updating status.json for changes: {e}")
    
    def graceful_shutdown(self):
        """优雅关闭"""
        self._log("Initiating graceful shutdown...")
        self.running = False
        # 跨线程安全地触发停止事件
        try:
            if getattr(self, 'loop', None) and self.loop and getattr(self.loop, 'is_running', lambda: False)():
                self.loop.call_soon_threadsafe(self.stop_event.set)
            else:
                self.stop_event.set()
        except Exception:
            try:
                self.stop_event.set()
            except Exception:
                pass
        
        # 停止环境文件监控
        if self.env_watcher:
            self.env_watcher.stop()
            
        # 停止HTTP服务器(如果有)
        if hasattr(self, '_server_stop_evt') and self._server_stop_evt:
            self._server_stop_evt.set()
            self._log("HTTP server stop signal sent")
            
        # 强制设置关闭标志，确保主循环退出
        try:
            if hasattr(self, '_shutdown_forced'):
                return
            self._shutdown_forced = True
        except Exception:
            pass
    
    def set_server_stop_event(self, stop_evt):
        """设置服务器停止事件"""
        self._server_stop_evt = stop_evt
    
    def _is_email_configured(self, code_config: CodeConfig) -> bool:
        """检查邮件是否配置"""
        return (code_config.channel == "email" and 
                code_config.target and 
                self.config.smtp_host and 
                self.config.smtp_user and 
                self.config.smtp_pass)
    
    async def run(self):
        """主运行循环"""
        self.running = True
        # 记录当前事件循环，供跨线程事件触发时使用
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None
        self._log("Priority scheduler started")
        
        # 重建队列
        self.rebuild_queue_from_status()
        # 同步一次，移除 status.json 中不在配置里的条目
        self.sync_status_with_config()
        
        try:
            while self.running and not self.stop_event.is_set():
                try:
                    # 检查是否被强制关闭
                    if hasattr(self, '_shutdown_forced'):
                        self._log("Forced shutdown detected, exiting main loop")
                        break
                    # 获取下一批任务
                    tasks = self.get_next_tasks()
                    if not tasks:
                        # 没有可执行任务：要么队列为空（等待新代码），要么下一个任务在未来（睡到队首任务时间）
                        if self.task_queue:
                            next_task_time = self.task_queue[0].next_check
                            now = datetime.now()
                            wait_seconds = max(1, (next_task_time - now).total_seconds())
                            human_eta = self._format_eta(wait_seconds)
                            self._log(
                                f"No ready tasks; next at {next_task_time.isoformat()} (in {human_eta}). Sleeping until then or new-code/stop"
                            )
                            try:
                                stop_wait = asyncio.create_task(self.stop_event.wait())
                                new_wait = asyncio.create_task(self.new_codes_event.wait())
                                done, pending = await asyncio.wait(
                                    [stop_wait, new_wait], timeout=wait_seconds, return_when=asyncio.FIRST_COMPLETED
                                )
                                for t in pending:
                                    t.cancel()
                                # 明确区分哪一个事件触发
                                if stop_wait in done and self.stop_event.is_set():
                                    self._log("Stop event received, exiting main loop")
                                    break
                                if new_wait in done and self.new_codes_event.is_set():
                                    self.new_codes_event.clear()
                                    # 立即进入下一轮以处理新代码
                                    continue
                                # 若超时，则到点了，进入下一轮处理到期任务
                                continue
                            except asyncio.TimeoutError:
                                # 应该不会触发：asyncio.wait 在到期时返回而不是抛异常
                                continue
                        else:
                            # 队列为空：事件驱动等待，直到新增代码或停止
                            self._log("No tasks in queue; waiting for new codes or shutdown")
                            stop_wait = asyncio.create_task(self.stop_event.wait())
                            new_wait = asyncio.create_task(self.new_codes_event.wait())
                            done, pending = await asyncio.wait(
                                [stop_wait, new_wait], return_when=asyncio.FIRST_COMPLETED
                            )
                            for t in pending:
                                t.cancel()
                            if stop_wait in done and self.stop_event.is_set():
                                self._log("Stop event received, exiting main loop")
                                break
                            if new_wait in done and self.new_codes_event.is_set():
                                self.new_codes_event.clear()
                                # 有新代码，下一轮立即处理
                                continue
                    self._log(f"Processing {len(tasks)} tasks using batch processing")
                    try:
                        results = await self.process_tasks_batch(tasks)
                    except Exception as e:
                        self._log(f"Batch processing failed: {e}")
                        results = [False] * len(tasks)
                        for task in tasks:
                            task.last_error = str(e)
                    for task, success in zip(tasks, results):
                        self.reschedule_task(task, success)
                    self._log(f"Stats: processed={self.stats['processed']}, errors={self.stats['errors']}, queue_size={len(self.task_queue)}")
                    if self.stop_event.is_set():
                        self._log("Stop event detected after batch processing, exiting")
                        break
                except Exception as e:
                    self._log(f"Main loop inner error: {e}")
        except Exception as e:
            self._log(f"Scheduler error: {e}")
        finally:
            self._log("Main loop exiting, performing cleanup...")
            try:
                if CZ_AVAILABLE:
                    import query_modules.cz as cz
                    if hasattr(cz, 'cleanup_browser'):
                        await cz.cleanup_browser()
                        self._log("Browser cleanup completed")
            except Exception as cleanup_error:
                self._log(f"Error during cleanup: {cleanup_error}")
            await self.cleanup()
    
    async def stop(self):
        """停止调度器"""
        self._log("Stopping priority scheduler...")
        self.running = False
        self.stop_event.set()
    
    async def cleanup(self):
        """清理资源"""
        self._log("Priority scheduler stopped")


# 全局注册当前运行的调度器，供API层即时唤醒与插队
CURRENT_SCHEDULER: Optional["PriorityScheduler"] = None

async def run_priority_scheduler(env_path: str = ".env", once: bool = False):
    """运行优先队列调度器"""
    
    # 加载配置
    config = load_env_config(env_path)
    
    if not config.codes:
        print("No codes configured. Exiting.")
        return
    
    # 创建调度器（一次性模式禁用信号处理器，避免干扰退出）
    scheduler = PriorityScheduler(config, env_path, use_signal_handler=not once)
    # 注册全局引用
    global CURRENT_SCHEDULER
    CURRENT_SCHEDULER = scheduler
    
    if once:
        # 单次运行模式：使用批量处理
        scheduler.rebuild_queue_from_status()
        tasks = scheduler.get_next_tasks()
        
        if tasks:
            print(f"Processing {len(tasks)} tasks in once mode using batch processing")
            results = await scheduler.process_tasks_batch(tasks)
            successful = sum(1 for r in results if r is True)
            failed = len(results) - successful
            print(f"Completed: {successful} successful, {failed} failed")
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
            # 设置服务器停止事件到调度器
            scheduler.set_server_stop_event(stop_evt)
            
        print(f"Priority Scheduler starting. SERVE={config.serve} SITE_DIR={config.site_dir} SITE_PORT={config.site_port}")
        if scheduler.env_watcher:
            scheduler._log("Environment file hot reloading enabled")
        
        # 信号处理：使用统一的SignalHandler（在调度器构造时已注册），这里不再重复注册
        
        try:
            # 运行调度器主循环
            await scheduler.run()
        except KeyboardInterrupt:
            print("\nShutdown requested by user")
            scheduler.running = False
            scheduler.stop_event.set()
        finally:
            # 清理
            await scheduler.cleanup()
            if server_thread and stop_evt:
                stop_evt.set()
                server_thread.join(timeout=5)
            # 强制退出
            import os
            os._exit(0)


def schedule_user_code_immediately(code: str):
    """供API调用：将用户新添加的 code 立即加入队列头进行查询"""
    try:
        if CURRENT_SCHEDULER is None:
            return False
        # 在合并视角下，为该code构造临时CodeConfig：尽量从 users.json 恢复 email 与频率
        target_email = None
        freq = CURRENT_SCHEDULER.config.default_freq_minutes
        try:
            users = CURRENT_SCHEDULER.store.load_users()
            rec = (users.get('codes') or {}).get(code)
            if isinstance(rec, dict):
                target_email = rec.get('target') or None
                f = rec.get('freq_minutes')
                if isinstance(f, int):
                    freq = f
                else:
                    try:
                        freq = int(f) if f is not None else freq
                    except Exception:
                        pass
        except Exception:
            pass
        cfg = CodeConfig(code=code, channel='email', target=target_email, freq_minutes=freq)
        CURRENT_SCHEDULER.add_new_code(cfg)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Priority Queue Visa Scheduler")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--env", default=".env", help="Environment file path")
    
    args = parser.parse_args()
    
    asyncio.run(run_priority_scheduler(args.env, args.once))