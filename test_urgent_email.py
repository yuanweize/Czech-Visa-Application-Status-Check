#!/usr/bin/env python3
"""
测试验证码邮件的立即发送功能
"""

import asyncio
import time
from monitor.notification.smtp_client import (
    send_verification_email_urgent_sync, 
    send_email_queued_sync,
    configure_email_queue,
    get_email_queue_stats
)

def test_urgent_vs_queued():
    """对比测试立即发送和队列发送"""
    print("=== 验证码邮件优先级测试 ===")
    
    # 配置队列：每分钟最多3封邮件（低限制，便于测试）
    configure_email_queue(max_emails_per_minute=3)
    print("配置邮件队列：每分钟最多3封邮件")
    
    # SMTP配置
    smtp_config = {
        'host': 'smtpx.fel.cvut.cz',
        'port': 465,
        'user': 'yuanweiz',
        'pass': 'Pengxiaodi0402.',
        'from': 'yuanweiz@fel.cvut.cz'
    }
    
    print("\\n1. 先发送3封普通邮件到队列（填满每分钟限制）")
    for i in range(3):
        result = send_email_queued_sync(
            to_email='iyuanweize@gmail.com',
            subject=f'普通邮件 #{i+1}',
            html_body=f'<p>这是第{i+1}封普通邮件，会进入队列等待</p>',
            smtp_config=smtp_config,
            priority=0
        )
        print(f"普通邮件{i+1}排队: {result[0]}")
        time.sleep(1)
    
    # 检查队列状态
    stats = get_email_queue_stats()
    print(f"\\n队列状态 - 队列大小: {stats['queue_size']}, 等待时间: {stats['rate_limit_wait']:.1f}s")
    
    print("\\n2. 现在发送验证码邮件（应该立即发送，不受队列限制）")
    start_time = time.time()
    
    urgent_result = send_verification_email_urgent_sync(
        to_email='iyuanweize@gmail.com',
        subject='🚨 紧急验证码邮件',
        html_body='''
        <div style="background: #ff6b6b; color: white; padding: 20px; border-radius: 8px;">
            <h2>🚨 验证码邮件 - 立即发送测试</h2>
            <p>这是一封验证码邮件，应该立即发送，不受队列限制！</p>
            <div style="background: white; color: black; padding: 10px; text-align: center; font-size: 24px; margin: 10px 0;">
                <strong>123456</strong>
            </div>
            <p>发送时间: {}</p>
        </div>
        '''.format(time.strftime("%Y-%m-%d %H:%M:%S")),
        smtp_config=smtp_config
    )
    
    end_time = time.time()
    send_duration = end_time - start_time
    
    print(f"验证码邮件发送结果: {urgent_result[0]}")
    print(f"验证码邮件发送耗时: {send_duration:.2f}秒")
    
    if urgent_result[0] and send_duration < 10:
        print("✅ 验证码邮件成功立即发送！")
    else:
        print("❌ 验证码邮件发送可能有问题")
    
    # 最终队列状态
    final_stats = get_email_queue_stats()
    print(f"\\n最终队列状态:")
    print(f"- 队列大小: {final_stats['queue_size']}")
    print(f"- 已发送: {final_stats['sent']}")
    print(f"- 等待时间: {final_stats['rate_limit_wait']:.1f}s")

if __name__ == "__main__":
    test_urgent_vs_queued()