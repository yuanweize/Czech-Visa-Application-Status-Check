"""
User Management Email Templates and Functions
用户管理邮件模板和功能

This module provides email functionality specifically for user management operations
including verification emails, management codes, and HTML page templates for web responses.
"""

from typing import Tuple, Optional

from .smtp_client import send_email_sync


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
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 2rem; text-align: center;">
            <h1>Czech Republic Visa Monitor</h1>
            <p>Verify New Code Addition</p>
        </div>
        
        <div style="padding: 2rem;">
            <h2>Hello!</h2>
            <p>You requested to add the visa code <strong>{code}</strong> to our monitoring system.</p>
            
            <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
                <p><strong>Code:</strong> {code}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Notifications:</strong> Enabled</p>
            </div>
            
            <p>To confirm this addition, please click the button below:</p>
            
            <div style="text-align: center; margin: 2rem 0;">
                <a href="{verification_url}" style="background: linear-gradient(135deg, #28a745, #20c997); color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold;">
                    ✅ Confirm Addition
                </a>
            </div>
            
            <p><strong>Important:</strong> This link will expire in 10 minutes for security reasons.</p>
            
            <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
            
            <p style="color: #666; font-size: 0.9rem;">
                If you didn't request this, please ignore this email. The code will not be added without verification.
            </p>
            
            <div style="text-align: center; margin-top: 2rem;">
                <p style="color: #666; font-size: 0.9rem;">
                    <strong>Czech Republic Visa Monitor</strong><br>
                    <a href="{base_url}">Return to Main Site</a>
                </p>
            </div>
        </div>
    </body>
    </html>
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
    
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #6c757d, #5a6268); color: white; padding: 2rem; text-align: center;">
            <h1>Czech Republic Visa Monitor</h1>
            <p>Management Verification Code</p>
        </div>
        
        <div style="padding: 2rem;">
            <h2>Hello!</h2>
            <p>You requested to manage your monitored visa codes. Your verification code is:</p>
            
            <div style="background: #f8f9fa; border: 2px solid #007bff; padding: 2rem; text-align: center; border-radius: 8px; margin: 2rem 0;">
                <h1 style="color: #007bff; font-size: 2.5rem; margin: 0; letter-spacing: 0.5rem; font-family: 'Courier New', monospace;">
                    {verification_code}
                </h1>
            </div>
            
            <p><strong>Important:</strong> This code will expire in 10 minutes for security reasons.</p>
            
            <p>Enter this code on the website to view and manage your monitored codes.</p>
            
            <hr style="margin: 2rem 0; border: none; border-top: 1px solid #ddd;">
            
            <p style="color: #666; font-size: 0.9rem;">
                If you didn't request this code, please ignore this email.
            </p>
            
            <div style="text-align: center; margin-top: 2rem;">
                <p style="color: #666; font-size: 0.9rem;">
                    <strong>Czech Republic Visa Monitor</strong><br>
                    Czech Republic Visa Application Status Monitor
                </p>
            </div>
        </div>
    </body>
    </html>
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
    subject, html_body = build_verification_email(code, to_email, verification_url, base_url)
    return send_email_sync(to_email, subject, html_body, smtp_config, env_path)


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
    subject, html_body = build_management_code_email(verification_code)
    return send_email_sync(to_email, subject, html_body, smtp_config, env_path)


def build_success_page(code: str, message: str, base_url: str) -> str:
    """
    Build success HTML page for verification responses
    
    Args:
        code: Visa code that was processed
        message: Success message to display
        base_url: Base URL for navigation links
        
    Returns:
        Complete HTML page as string
    """
    html_page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Success - Czech Visa Monitor</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #e3f2fd, #bbdefb);
                margin: 0;
                padding: 2rem;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 500px;
                width: 100%;
                padding: 3rem 2rem;
                text-align: center;
            }}
            .success-icon {{
                background: linear-gradient(135deg, #4caf50, #45a049);
                color: white;
                width: 80px;
                height: 80px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.5rem;
                margin: 0 auto 2rem;
            }}
            h1 {{
                color: #2e7d32;
                margin-bottom: 1rem;
                font-size: 1.8rem;
            }}
            .code-box {{
                background: #f8f9fa;
                border: 2px solid #4caf50;
                border-radius: 8px;
                padding: 1rem;
                margin: 1.5rem 0;
                font-family: 'Courier New', monospace;
                font-size: 1.1rem;
                font-weight: bold;
                color: #2e7d32;
            }}
            .message {{
                color: #555;
                font-size: 1.1rem;
                margin-bottom: 2rem;
                line-height: 1.6;
            }}
            .actions {{
                display: flex;
                gap: 1rem;
                justify-content: center;
                flex-wrap: wrap;
            }}
            .btn {{
                padding: 0.75rem 1.5rem;
                border: none;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                display: inline-block;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #007bff, #0056b3);
                color: white;
            }}
            .btn-secondary {{
                background: #f8f9fa;
                color: #6c757d;
                border: 1px solid #dee2e6;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            .footer {{
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid #dee2e6;
                color: #6c757d;
                font-size: 0.9rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1>Success!</h1>
            <div class="code-box">{code}</div>
            <p class="message">{message}</p>
            <div class="actions">
                <a href="{base_url}" class="btn btn-primary">Return to Main Site</a>
                <a href="{base_url}#manage" class="btn btn-secondary">Manage My Codes</a>
            </div>
            <div class="footer">
                <strong>Czech Republic Visa Monitor</strong><br>
                Your visa code is now being monitored automatically.
            </div>
        </div>
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
    details_html = f"<p class='details'>{details}</p>" if details else ""
    
    html_page = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Error - Czech Visa Monitor</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #ffebee, #ffcdd2);
                margin: 0;
                padding: 2rem;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                background: white;
                border-radius: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 500px;
                width: 100%;
                padding: 3rem 2rem;
                text-align: center;
            }}
            .error-icon {{
                background: linear-gradient(135deg, #f44336, #d32f2f);
                color: white;
                width: 80px;
                height: 80px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 2.5rem;
                margin: 0 auto 2rem;
            }}
            h1 {{
                color: #c62828;
                margin-bottom: 1rem;
                font-size: 1.8rem;
            }}
            .message {{
                color: #555;
                font-size: 1.1rem;
                margin-bottom: 1rem;
                line-height: 1.6;
            }}
            .details {{
                background: #fff3e0;
                border-left: 4px solid #ff9800;
                padding: 1rem;
                margin: 1.5rem 0;
                text-align: left;
                border-radius: 0 8px 8px 0;
                color: #e65100;
                font-size: 0.95rem;
            }}
            .actions {{
                display: flex;
                gap: 1rem;
                justify-content: center;
                flex-wrap: wrap;
                margin-top: 2rem;
            }}
            .btn {{
                padding: 0.75rem 1.5rem;
                border: none;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                display: inline-block;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #007bff, #0056b3);
                color: white;
            }}
            .btn-secondary {{
                background: #f8f9fa;
                color: #6c757d;
                border: 1px solid #dee2e6;
            }}
            .btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            }}
            .footer {{
                margin-top: 2rem;
                padding-top: 1rem;
                border-top: 1px solid #dee2e6;
                color: #6c757d;
                font-size: 0.9rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-icon">❌</div>
            <h1>{error_title}</h1>
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