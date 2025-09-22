"""
Status Change Email Notifications
状态变更邮件通知模块

This module handles email notifications for visa status changes.
Provides templates and logic for status change notification emails.
"""

from __future__ import annotations

from typing import Optional, Tuple


def build_email_subject(status: str, code: str) -> str:
    """构建邮件主题
    
    Args:
        status: 签证状态
        code: 查询代码
        
    Returns:
        邮件主题字符串
    """
    # Keep concise subject; append a short CN hint for clarity
    return f"[{status}] {code} - CZ Visa Status 状态通知"


def build_email_body(
    code: str, 
    status: str, 
    when: str, 
    *,
    changed: bool = False,
    old_status: Optional[str] = None,
    notif_label: str = "状态通知"
) -> str:
    """构建邮件正文
    
    Args:
        code: 查询代码
        status: 当前状态
        when: 时间字符串
        changed: 是否状态发生变化
        old_status: 旧状态（如果有变化）
        notif_label: 通知标签
        
    Returns:
        HTML格式的邮件正文
    """
    old_to_new = ''
    if changed and old_status:
        old_to_new = f"""
        <tr>
            <td style=\"color:#555;\">Status Change / 状态变化</td>
            <td><b>{old_status}</b> &rarr; <b>{status}</b></td>
        </tr>"""
    
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; line-height:1.6; color:#222;">
        <div style="max-width:680px; margin:24px auto; border:1px solid #eee; border-radius:10px; overflow:hidden; box-shadow:0 4px 14px rgba(0,0,0,.06);">
            <div style="padding:16px 20px; background:#0b5ed7; color:#fff;">
                <div style="font-weight:600; font-size:16px; letter-spacing:.2px;">CZ Visa Status · Notification / 通知</div>
                <div style="margin-top:4px; font-size:13px; opacity:.9;">Code <b>{code}</b> · Status <b>{status}</b></div>
            </div>
            <div style="padding:16px 20px; background:#fff;">
                <table style="width:100%; border-collapse:collapse; font-size:14px;">
                    <tr>
                        <td style="width:160px; color:#555;">Code / 查询码</td>
                        <td><code style="background:#f6f8fa; padding:2px 6px; border-radius:6px;">{code}</code></td>
                    </tr>
                    <tr>
                        <td style="color:#555;">Type / 通知类型</td>
                        <td>{notif_label}</td>
                    </tr>
                    {old_to_new}
                    <tr>
                        <td style="color:#555;">Current Status / 当前状态</td>
                        <td><b>{status}</b></td>
                    </tr>
                    <tr>
                        <td style="color:#555;">Time / 时间</td>
                        <td>{when}</td>
                    </tr>
                </table>
            </div>
            <div style="padding:12px 20px; background:#fafafa; color:#666; font-size:12px; border-top:1px solid #eee;">
                Note: Emails are sent on first record or when status changes; "Query Failed / 查询失败" won't trigger notifications. / 说明：首次记录或状态变化时发送；“查询失败”不触发通知。
                <div style="margin-top:6px;">
                    Live status / 实时状态：<a href="https://visa.eurun.top/" target="_blank" rel="noopener" style="color:#0b5ed7; text-decoration:none;">https://visa.eurun.top/</a>
                </div>
            </div>
        </div>
    </div>
    """


def should_send_notification(
    old_status: Optional[str],
    new_status: str,
    is_first_check: bool = False
) -> Tuple[bool, str]:
    """
    Determine whether to send notification for status change
    判断是否应该发送通知
    
    Args:
        old_status: Previous status
        new_status: Current status  
        is_first_check: Whether this is the first check
        
    Returns:
        Tuple of (should_send: bool, notification_label: str)
    """
    # Don't send notification for query failures
    if "查询失败" in new_status or "Query Failed" in new_status:
        return False, ""
    
    # First check: do NOT notify if it's Not Found
    if is_first_check:
        if ("Not Found" in new_status) or ("未找到" in new_status):
            return False, ""
        return True, "首次查询"
    
    # Status has changed
    if old_status and old_status != new_status:
        return True, "状态变化"
    
    return False, ""