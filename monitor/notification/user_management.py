"""
User Management Email Templates and Functions
用户管理邮件模板和功能

This module provides email functionality specifically for user management operations
including verification emails, management codes, and HTML page templates for web responses.
"""

from typing import Tuple, Optional

from .smtp_client import send_email_immediate_sync
from ..utils.logger import get_email_logger


def build_verification_email(code: str, email: str, verification_url: str, base_url: str) -> Tuple[str, str]:
    """
    Build verification email for new code addition
    
    Args:
        code: Visa code being added
        email: User email address
        verification_url: URL for verification
        base_url: Base URL of the application
        
    Returns:
        Tuple of (subject: str, html_body: str)
    """
    subject = "Czech Visa Monitor - Verify New Code Addition"

    # Unified style aligned with status notification template
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; line-height:1.6; color:#222;">
        <div style="max-width:680px; margin:24px auto; border:1px solid #eee; border-radius:10px; overflow:hidden; box-shadow:0 4px 14px rgba(0,0,0,.06);">
            <div style="padding:16px 20px; background:#0b5ed7; color:#fff;">
                <div style="font-weight:600; font-size:16px; letter-spacing:.2px;">CZ Visa Status 验证</div>
                <div style="margin-top:4px; font-size:13px; opacity:.9;">Code <b>{code}</b> · 邮箱 <b>{email}</b></div>
            </div>
            <div style="padding:16px 20px; background:#fff;">
                <table style="width:100%; border-collapse:collapse; font-size:14px;">
                    <tr>
                        <td style="width:120px; color:#555;">操作</td>
                        <td>新增监控代码（需验证）</td>
                    </tr>
                    <tr>
                        <td style="color:#555;">查询码</td>
                        <td><code style="background:#f6f8fa; padding:2px 6px; border-radius:6px;">{code}</code></td>
                    </tr>
                    <tr>
                        <td style="color:#555;">邮箱</td>
                        <td>{email}</td>
                    </tr>
                    <tr>
                        <td style="color:#555;">有效期</td>
                        <td>10 分钟</td>
                    </tr>
                </table>
                <div style="text-align:center; margin:20px 0 4px;">
                    <a href="{verification_url}" style="background:#0b5ed7; color:#fff; padding:10px 18px; text-decoration:none; border-radius:8px; display:inline-block; font-weight:600;">✅ 确认添加 / Confirm</a>
                </div>
            </div>
            <div style="padding:12px 20px; background:#fafafa; color:#666; font-size:12px; border-top:1px solid #eee;">
                说明：若非本人操作，请忽略本邮件；未验证将不会添加该查询码。
                <div style="margin-top:6px;">主页 / Main site：<a href="{base_url}" target="_blank" rel="noopener" style="color:#0b5ed7; text-decoration:none;">{base_url}</a></div>
            </div>
        </div>
    </div>
    """
    
    return subject, html_body


def build_management_code_email(verification_code: str) -> Tuple[str, str]:
    """
    Build management verification code email
    
    Args:
        verification_code: 6-digit verification code
        
    Returns:
        Tuple of (subject: str, html_body: str)
    """
    subject = "Czech Visa Monitor - Management Verification Code"

    # Unified style aligned with status notification template
    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif; line-height:1.6; color:#222;">
        <div style="max-width:680px; margin:24px auto; border:1px solid #eee; border-radius:10px; overflow:hidden; box-shadow:0 4px 14px rgba(0,0,0,.06);">
            <div style="padding:16px 20px; background:#0b5ed7; color:#fff;">
                <div style="font-weight:600; font-size:16px; letter-spacing:.2px;">CZ Visa Status 管理验证</div>
                <div style="margin-top:4px; font-size:13px; opacity:.9;">Management Verification Code</div>
            </div>
            <div style="padding:16px 20px; background:#fff;">
                <table style="width:100%; border-collapse:collapse; font-size:14px;">
                    <tr>
                        <td style="width:120px; color:#555;">用途</td>
                        <td>查看 / 管理我的查询码</td>
                    </tr>
                    <tr>
                        <td style="color:#555;">验证码</td>
                        <td>
                            <div style="background:#f6f8fa; border:1px solid #e5e7eb; padding:10px 12px; display:inline-block; border-radius:8px; font-family:'Courier New', monospace; font-weight:700; letter-spacing:4px; font-size:22px; color:#0b5ed7;">{verification_code}</div>
                        </td>
                    </tr>
                    <tr>
                        <td style="color:#555;">有效期</td>
                        <td>10 分钟</td>
                    </tr>
                </table>
                <div style="margin-top:10px; color:#666; font-size:12px;">请在网站中输入上述验证码完成验证。</div>
            </div>
            <div style="padding:12px 20px; background:#fafafa; color:#666; font-size:12px; border-top:1px solid #eee;">
                说明：若非本人操作，请忽略本邮件；验证码过期请重新获取。
            </div>
        </div>
    </div>
    """
    
    return subject, html_body


def send_verification_email(to_email: str, code: str, verification_url: str, base_url: str, smtp_config: dict, env_path: str = ".env") -> Tuple[bool, Optional[str]]:
    """
    Send verification email for code addition
    
    Args:
        to_email: Recipient email address
        code: Visa code being added
        verification_url: URL for verification
        base_url: Base URL of the application
        smtp_config: SMTP configuration
        env_path: Path to .env file for loading base configuration (supports hot reload)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    logger = get_email_logger()
    
    # Log email attempt
    log_id = logger.log_verification_email_attempt(to_email, code, verification_url, smtp_config)
    
    try:
        subject, html_body = build_verification_email(code, to_email, verification_url, base_url)
        # Use immediate email sending for verification emails (better user experience)
        success, error_or_response = send_email_immediate_sync(to_email, subject, html_body, smtp_config, env_path)
        
        # Log email result
        if success:
            logger.log_verification_email_result(log_id, True, smtp_response=error_or_response)
        else:
            logger.log_verification_email_result(log_id, False, error=error_or_response)
        
        return success, error_or_response
        
    except Exception as e:
        error_msg = str(e)
        logger.log_verification_email_result(log_id, False, error=error_msg)
        return False, error_msg


def send_management_code_email(to_email: str, verification_code: str, smtp_config: dict, env_path: str = ".env") -> Tuple[bool, Optional[str]]:
    """
    Send management verification code email
    
    Args:
        to_email: Recipient email address
        verification_code: 6-digit verification code
        smtp_config: SMTP configuration
        env_path: Path to .env file for loading base configuration (supports hot reload)
        
    Returns:
        Tuple of (success: bool, error_message: str or None)
    """
    logger = get_email_logger()
    
    # Log email attempt
    log_id = logger.log_management_email_attempt(to_email, verification_code, smtp_config)
    
    try:
        subject, html_body = build_management_code_email(verification_code)
        # Use immediate email sending for verification codes (better user experience)
        success, error_or_response = send_email_immediate_sync(to_email, subject, html_body, smtp_config, env_path)
        
        # Log email result
        if success:
            logger.log_management_email_result(log_id, True, smtp_response=error_or_response)
        else:
            logger.log_management_email_result(log_id, False, error=error_or_response)
        
        return success, error_or_response
        
    except Exception as e:
        error_msg = str(e)
        logger.log_management_email_result(log_id, False, error=error_msg)
        return False, error_msg


def _get_common_page_styles() -> str:
    """
    Get common CSS styles for HTML pages
    
    Returns:
        Common CSS styles as string
    """
    return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 2rem;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            max-width: 500px;
            width: 100%;
            padding: 3rem 2rem;
            text-align: center;
        }
        .icon {
            color: white;
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.5rem;
            margin: 0 auto 2rem;
        }
        .success-icon {
            background: linear-gradient(135deg, #4caf50, #45a049);
        }
        .error-icon {
            background: linear-gradient(135deg, #f44336, #d32f2f);
        }
        h1 {
            margin-bottom: 1rem;
            font-size: 1.8rem;
        }
        .success-title {
            color: #2e7d32;
        }
        .error-title {
            color: #c62828;
        }
        .message {
            color: #555;
            font-size: 1.1rem;
            margin-bottom: 1rem;
            line-height: 1.6;
        }
        .code-box {
            background: #f8f9fa;
            border: 2px solid #4caf50;
            border-radius: 8px;
            padding: 1rem;
            margin: 1.5rem 0;
            font-family: 'Courier New', monospace;
            font-size: 1.1rem;
            font-weight: bold;
            color: #2e7d32;
        }
        .details {
            background: #fff3e0;
            border-left: 4px solid #ff9800;
            padding: 1rem;
            margin: 1.5rem 0;
            text-align: left;
            border-radius: 0 8px 8px 0;
            color: #e65100;
            font-size: 0.95rem;
        }
        .actions {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 2rem;
        }
        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-block;
        }
        .btn-primary {
            background: linear-gradient(135deg, #007bff, #0056b3);
            color: white;
        }
        .btn-secondary {
            background: #f8f9fa;
            color: #6c757d;
            border: 1px solid #dee2e6;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .footer {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
            font-size: 0.9rem;
        }
        .success-bg {
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
        }
        .error-bg {
            background: linear-gradient(135deg, #ffebee, #ffcdd2);
        }
    """


def build_success_page(code: str, message: str, base_url: str, session_id: str = None) -> str:
    """
    Build success HTML page for verification responses
    
    Args:
        code: Visa code that was processed
        message: Success message to display
        base_url: Base URL for navigation links
        session_id: Optional session ID to auto-login user
        
    Returns:
        Complete HTML page as string
    """
    common_styles = _get_common_page_styles()
    
    # Add session JavaScript if session_id is provided
    session_script = f"""
        <script>
            // Auto-set session for seamless experience
            localStorage.setItem('visa_session_id', '{session_id}');
            // Also persist via cookie for 7 days
            (function() {{
                try {{
                    var maxAge = 7 * 24 * 3600;
                    document.cookie = 'visa_session_id=' + encodeURIComponent('{session_id}') + '; Path=/; Max-Age=' + maxAge + '; SameSite=Lax';
                }} catch (e) {{}}
            }})();
            console.log('Session automatically set for user convenience');
        </script>
    """ if session_id else ""
    
    html_page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Success - Czech Visa Monitor</title>
        <style>
            {common_styles}
        </style>
    </head>
    <body class="success-bg">
        <div class="container">
            <div class="icon success-icon">✅</div>
            <h1 class="success-title">Success!</h1>
            <div class="code-box">{code}</div>
            <p class="message" style="margin-bottom: 2rem;">{message}</p>
            <div class="actions">
                <a href="{base_url}" class="btn btn-primary">Return to Main Site</a>
                <a href="{base_url}#manage" class="btn btn-secondary">Manage My Codes</a>
            </div>
            <div class="footer">
                <strong>Czech Republic Visa Monitor</strong><br>
                Your visa code is now being monitored automatically.
            </div>
        </div>
        {session_script}
    </body>
    </html>
    """
    
    return html_page


def build_error_page(error_title: str, error_message: str, base_url: str, details: str = None) -> str:
    """
    Build error HTML page for verification responses
    
    Args:
        error_title: Main error title
        error_message: Error message to display
        base_url: Base URL for navigation links
        details: Optional additional details
        
    Returns:
        Complete HTML page as string
    """
    common_styles = _get_common_page_styles()
    details_html = f"<p class='details'>{details}</p>" if details else ""
    
    html_page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error - Czech Visa Monitor</title>
        <style>
            {common_styles}
        </style>
    </head>
    <body class="error-bg">
        <div class="container">
            <div class="icon error-icon">❌</div>
            <h1 class="error-title">{error_title}</h1>
            <p class="message">{error_message}</p>
            {details_html}
            <div class="actions">
                <a href="{base_url}" class="btn btn-primary">Return to Main Site</a>
                <a href="{base_url}#add" class="btn btn-secondary">Try Again</a>
            </div>
            <div class="footer">
                <strong>Czech Republic Visa Monitor</strong><br>
                Need help? Please contact support.
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_page