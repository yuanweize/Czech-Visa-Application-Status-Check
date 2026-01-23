
import asyncio
import os
import json
import time
from monitor.core.code_manager import CodeStorageManager
from monitor.core.scheduler import PriorityScheduler, ScheduledTask
from monitor.core.config import MonitorConfig, CodeConfig

async def test_atomic_write_safety():
    print("Testing Atomic Writes...")
    store = CodeStorageManager("site_test_atomic")
    store.ensure_initialized()
    data = {"test": "data", "val": 123}
    
    # Simple save
    store.save_users(data)
    
    path = os.path.join("site_test_atomic", "config", "users.json")
    if os.path.exists(path) and os.path.exists(path + ".bak"):
        print("✅ Atomic write and backup confirmed")
    else:
        print("❌ Backup file missing")
    
    # Verify content
    with open(path, 'r') as f:
        saved = json.load(f)
        assert saved["test"] == "data"
    print("✅ Content verified")

async def test_scheduler_task_cancellation():
    print("\nTesting Scheduler Task Cancellation on Reload...")
    config = MonitorConfig(
        site_dir="site_test", 
        codes=[CodeConfig(code="TEST1234567890", channel="none")],
        headless=True,
        log_dir="logs",
        serve=False,
        site_port=8080,
        default_freq_minutes=60,
        workers=1,
        smtp_host="",
        smtp_port=587,
        smtp_user="",
        smtp_pass="",
        smtp_from="",
        email_max_per_minute=10,
        email_first_check_delay=10
    )
    scheduler = PriorityScheduler(config)
    scheduler.loop = asyncio.get_running_loop()
    
    # Mock a running task
    mock_task = asyncio.create_task(asyncio.sleep(10))
    scheduler._active_batch_tasks.append(mock_task)
    
    # Trigger reload
    scheduler.reload_config()
    await asyncio.sleep(0.1) # Wait for event loop to catch up
    
    if mock_task.cancelled():
        print("✅ Task successfully cancelled on reload")
    else:
        print("❌ Task still running after reload")
    
    mock_task.cancel() # Cleanup

async def main():
    try:
        await test_atomic_write_safety()
        await test_scheduler_task_cancellation()
    finally:
        # Cleanup test dirs
        import shutil
        for d in ["site_test_atomic", "site_test"]:
            if os.path.exists(d):
                shutil.rmtree(d)

if __name__ == "__main__":
    asyncio.run(main())
