#!/usr/bin/env python3
"""
User Management API Module for Czech Visa Monitor
用户管理API模块

This module provides API handlers for user code management functionality
that can be imported and integrated into the main scheduler.
"""

import os
import json
import secrets
import smtplib
import ssl
import re
import threading
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formataddr
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from monitor.config import load_env_config


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class APIHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, config_path='.env', site_dir='site', **kwargs):
        self.config_path = config_path
        self.site_dir = site_dir
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        # Custom logging for API requests only
        if self.path.startswith('/api/'):
            print(f"[{_now_iso()}] API {format % args}")
    
    def _send_json_response(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.wfile.write(response)
    
    def _send_html_response(self, status_code: int, html: str):
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _load_config(self):
        """Load configuration from .env file"""
        return load_env_config(self.config_path)
    
    def _load_status_data(self):
        """Load status data from status.json"""
        status_path = os.path.join(self.site_dir, "status.json")
        try:
            with open(status_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {
                "generated_at": _now_iso(),
                "items": {},
                "user_management": {
                    "verification_codes": {},
                    "pending_additions": {}
                }
            }
    
    def _save_status_data(self, data):
        """Save status data to status.json"""
        status_path = os.path.join(self.site_dir, "status.json")
        try:
            with open(status_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[{_now_iso()}] Failed to save status data: {e}")
            return False
    
    def _generate_verification_code(self):
        """Generate 6-digit verification code"""
        return f"{secrets.randbelow(900000) + 100000:06d}"
    
    def _send_email(self, to_email: str, subject: str, html_body: str):
        """Send email using configuration from .env"""
        try:
            config = self._load_config()
            
            if not config.smtp_host:
                return False, "SMTP not configured"
            
            msg = MIMEText(html_body, "html", "utf-8")
            sender = config.smtp_from or "CZ Visa Monitor"
            if "@" in sender:
                msg["From"] = formataddr(("CZ Visa Monitor", sender))
            else:
                msg["From"] = "CZ Visa Monitor <noreply@example.com>"
            msg["To"] = to_email
            msg["Subject"] = subject
            
            port = config.smtp_port or 465
            if port == 465:
                with smtplib.SMTP_SSL(config.smtp_host, port, context=ssl.create_default_context()) as server:
                    if config.smtp_user and config.smtp_pass:
                        server.login(config.smtp_user, config.smtp_pass)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(config.smtp_host, port) as server:
                    server.ehlo()
                    try:
                        server.starttls(context=ssl.create_default_context())
                        server.ehlo()
                    except:
                        pass
                    if config.smtp_user and config.smtp_pass:
                        server.login(config.smtp_user, config.smtp_pass)
                    server.send_message(msg)
            
            return True, None
        except Exception as e:
            return False, str(e)
    
    def _add_to_env_config(self, code: str, email: str):
        """Add new code to .env configuration"""
        env_path = Path(self.config_path)
        
        # Read existing configuration
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = ""
        
        # Check if using CODES_JSON format
        if "CODES_JSON=" in content:
            # Parse existing CODES_JSON
            lines = content.split('\n')
            codes_json_lines = []
            in_codes_json = False
            other_lines = []
            
            for line in lines:
                if line.strip().startswith('CODES_JSON='):
                    in_codes_json = True
                    codes_json_lines.append(line)
                elif in_codes_json:
                    codes_json_lines.append(line)
                    if line.strip().endswith(']'):
                        in_codes_json = False
                else:
                    other_lines.append(line)
            
            # Parse JSON
            codes_json_str = '\n'.join(codes_json_lines).split('=', 1)[1]
            try:
                codes_list = json.loads(codes_json_str)
            except:
                codes_list = []
            
            # Add new code
            codes_list.append({
                "code": code,
                "channel": "email",
                "target": email,
                "freq_minutes": 60
            })
            
            # Rebuild content
            other_content = '\n'.join(other_lines)
            new_codes_json = json.dumps(codes_list, ensure_ascii=False, indent=1)
            new_content = other_content + f"\nCODES_JSON={new_codes_json}\n"
        else:
            # Use numbered format, find max index
            max_idx = 0
            for line in content.split('\n'):
                if line.strip().startswith('CODE_'):
                    try:
                        idx = int(line.split('_')[1].split('=')[0])
                        max_idx = max(max_idx, idx)
                    except:
                        pass
            
            # Add new code
            new_idx = max_idx + 1
            new_content = content + f"""
CODE_{new_idx}={code}
CHANNEL_{new_idx}=email
TARGET_{new_idx}={email}
FREQ_MINUTES_{new_idx}=60
"""
        
        # Write file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_content.strip() + '\n')
    
    def _remove_from_env_config(self, code: str):
        """Remove code from .env configuration"""
        env_path = Path(self.config_path)
        if not env_path.exists():
            return
        
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if "CODES_JSON=" in content:
            # Handle CODES_JSON format
            lines = content.split('\n')
            codes_json_lines = []
            in_codes_json = False
            other_lines = []
            
            for line in lines:
                if line.strip().startswith('CODES_JSON='):
                    in_codes_json = True
                    codes_json_lines.append(line)
                elif in_codes_json:
                    codes_json_lines.append(line)
                    if line.strip().endswith(']'):
                        in_codes_json = False
                else:
                    other_lines.append(line)
            
            # Parse and filter JSON
            codes_json_str = '\n'.join(codes_json_lines).split('=', 1)[1]
            try:
                codes_list = json.loads(codes_json_str)
                codes_list = [c for c in codes_list if c.get('code') != code]
            except:
                codes_list = []
            
            # Rebuild
            other_content = '\n'.join(other_lines)
            new_codes_json = json.dumps(codes_list, ensure_ascii=False, indent=1)
            new_content = other_content + f"\nCODES_JSON={new_codes_json}\n"
        else:
            # Handle numbered format
            lines = content.split('\n')
            new_lines = []
            skip_indices = set()
            
            # Find indices to remove
            for line in lines:
                if line.strip().startswith('CODE_') and f"={code}" in line:
                    try:
                        idx = line.split('_')[1].split('=')[0]
                        skip_indices.add(idx)
                    except:
                        pass
            
            # Filter lines
            for line in lines:
                skip = False
                for idx in skip_indices:
                    if (line.strip().startswith(f'CODE_{idx}=') or 
                        line.strip().startswith(f'CHANNEL_{idx}=') or 
                        line.strip().startswith(f'TARGET_{idx}=') or 
                        line.strip().startswith(f'FREQ_MINUTES_{idx}=')):
                        skip = True
                        break
                if not skip:
                    new_lines.append(line)
            
            new_content = '\n'.join(new_lines)
        
        # Write file
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_content.strip() + '\n')
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if post_data else {}
        except Exception:
            self._send_json_response(400, {'error': 'Invalid JSON data'})
            return
        
        if path == '/api/add-code':
            self._handle_add_code(data)
        elif path == '/api/send-manage-code':
            self._handle_send_manage_code(data)
        elif path == '/api/verify-manage':
            self._handle_verify_manage(data)
        elif path == '/api/delete-code':
            self._handle_delete_code(data)
        else:
            self._send_json_response(404, {'error': 'API endpoint not found'})
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Handle API endpoints
        if path.startswith('/api/verify-add/'):
            token = path.replace('/api/verify-add/', '')
            self._handle_verify_add(token)
        elif path.startswith('/api/'):
            # Other API endpoints should be POST
            self._send_json_response(405, {'error': 'Method not allowed'})
        else:
            # Handle static files
            self._serve_static_file()
    
    def _serve_static_file(self):
        """Serve static files from site directory"""
        import os
        import mimetypes
        from pathlib import Path
        
        # Parse the path
        parsed_path = urlparse(self.path)
        file_path = parsed_path.path.lstrip('/')
        
        # Default to index.html for root
        if not file_path or file_path == '/':
            file_path = 'index.html'
        
        # Build full file path
        full_path = Path(self.site_dir) / file_path
        
        try:
            if full_path.exists() and full_path.is_file():
                # Determine content type
                content_type, _ = mimetypes.guess_type(str(full_path))
                if content_type is None:
                    content_type = 'application/octet-stream'
                
                # Read and serve file
                with open(full_path, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, 'File not found')
        except Exception as e:
            self.send_error(500, f'Internal server error: {e}')
    
    def _handle_add_code(self, data):
        code = data.get('code', '').strip().upper()
        email = data.get('email', '').strip().lower()
        captcha_answer = data.get('captcha_answer')
        
        # Validate input
        if not code or not email:
            self._send_json_response(400, {'error': 'Code and email are required'})
            return
        
        # Validate code format
        if not re.match(r'^[A-Z]{4}\d{12}$', code):
            self._send_json_response(400, {'error': 'Invalid visa code format'})
            return
        
        # Check if already exists
        status_data = self._load_status_data()
        items = status_data.get('items', {})
        if code in items and items[code].get('added_by') == email:
            self._send_json_response(400, {'error': 'This code is already being monitored for this email'})
            return
        
        # Generate verification token
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        status_data.setdefault('user_management', {}).setdefault('pending_additions', {})[token] = {
            'code': code,
            'email': email,
            'expires': expires
        }
        
        self._save_status_data(status_data)
        
        # Send verification email
        config = self._load_config()
        base_url = f"http://localhost:{config.site_port}"
        verification_url = f"http://localhost:{config.site_port}/api/verify-add/{token}"
        
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
        
        success, error = self._send_email(email, subject, html_body)
        
        if success:
            self._send_json_response(200, {'message': 'Verification email sent successfully'})
        else:
            self._send_json_response(500, {'error': f'Failed to send email: {error}'})
    
    def _handle_verify_add(self, token):
        status_data = self._load_status_data()
        pending = status_data.get('user_management', {}).get('pending_additions', {}).get(token)
        
        if not pending:
            self._send_html_response(400, """
            <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 2rem;">
                <h1>❌ Invalid Verification Link</h1>
                <p>This verification link is invalid or has already been used.</p>
                <a href="/">Return to Main Site</a>
            </body>
            </html>
            """)
            return
        
        # Check expiry
        expires = datetime.fromisoformat(pending['expires'])
        if datetime.now() > expires:
            del status_data['user_management']['pending_additions'][token]
            self._save_status_data(status_data)
            self._send_html_response(400, """
            <html>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 2rem;">
                <h1>⏰ Link Expired</h1>
                <p>This verification link has expired. Please submit a new request.</p>
                <a href="/">Return to Main Site</a>
            </body>
            </html>
            """)
            return
        
        code = pending['code']
        email = pending['email']
        
        # Add to status.json
        status_data.setdefault('items', {})[code] = {
            'code': code,
            'status': None,
            'last_checked': None,
            'last_changed': None,
            'channel': 'Email',
            'target': email,
            'added_at': _now_iso(),
            'added_by': email
        }
        
        # Remove from pending
        del status_data['user_management']['pending_additions'][token]
        self._save_status_data(status_data)
        
        # Add to .env config
        try:
            self._add_to_env_config(code, email)
        except Exception as e:
            print(f"[{_now_iso()}] Failed to add to .env: {e}")
        
        config = self._load_config()
        base_url = f"http://localhost:{config.site_port}"
        
        self._send_html_response(200, f"""
        <html>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 2rem; background: linear-gradient(135deg, #f8f9fa, #e9ecef);">
            <div style="background: white; padding: 3rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); max-width: 500px; margin: 0 auto;">
                <h1 style="color: #28a745;">✅ Success!</h1>
                <p>Your visa code <strong>{code}</strong> has been successfully added to the monitoring system.</p>
                
                <div style="background: #d4edda; padding: 1rem; border-radius: 8px; margin: 1rem 0; border: 1px solid #c3e6cb;">
                    <p style="margin: 0; color: #155724;"><strong>What happens next?</strong></p>
                    <p style="margin: 0.5rem 0 0 0; color: #155724;">• Your code will be checked every hour</p>
                    <p style="margin: 0.5rem 0 0 0; color: #155724;">• You'll receive email notifications when the status changes</p>
                    <p style="margin: 0.5rem 0 0 0; color: #155724;">• You can view real-time status on our website</p>
                </div>
                
                <div style="margin: 2rem 0;">
                    <a href="{base_url}" style="background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 1rem 2rem; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold;">
                        🏠 Return to Main Site
                    </a>
                </div>
                
                <p style="color: #666; font-size: 0.9rem;">
                    Need to manage your codes? Use the "Manage My Codes" button on the main site.
                </p>
            </div>
        </body>
        </html>
        """)
    
    def _handle_send_manage_code(self, data):
        email = data.get('email', '').strip().lower()
        
        if not email:
            self._send_json_response(400, {'error': 'Email is required'})
            return
        
        # Check if has codes
        status_data = self._load_status_data()
        items = status_data.get('items', {})
        user_codes = [item for item in items.values() if item.get('added_by') == email]
        
        if not user_codes:
            self._send_json_response(404, {'error': 'No codes found for this email address'})
            return
        
        # Generate verification code
        verification_code = self._generate_verification_code()
        expires = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        status_data.setdefault('user_management', {}).setdefault('verification_codes', {})[email] = {
            'code': verification_code,
            'expires': expires,
            'type': 'manage'
        }
        
        self._save_status_data(status_data)
        
        # Send email
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
        
        success, error = self._send_email(email, subject, html_body)
        
        if success:
            self._send_json_response(200, {'message': 'Verification code sent successfully'})
        else:
            self._send_json_response(500, {'error': f'Failed to send email: {error}'})
    
    def _handle_verify_manage(self, data):
        email = data.get('email', '').strip().lower()
        verification_code = data.get('verification_code', '').strip()
        
        if not email or not verification_code:
            self._send_json_response(400, {'error': 'Email and verification code are required'})
            return
        
        # Check verification code
        status_data = self._load_status_data()
        stored = status_data.get('user_management', {}).get('verification_codes', {}).get(email)
        
        if not stored:
            self._send_json_response(400, {'error': 'No verification code found for this email'})
            return
        
        # Check expiry
        expires = datetime.fromisoformat(stored['expires'])
        if datetime.now() > expires:
            del status_data['user_management']['verification_codes'][email]
            self._save_status_data(status_data)
            self._send_json_response(400, {'error': 'Verification code has expired'})
            return
        
        # Check code
        if stored['code'] != verification_code:
            self._send_json_response(400, {'error': 'Invalid verification code'})
            return
        
        # Get user codes
        items = status_data.get('items', {})
        user_codes = []
        for item in items.values():
            if item.get('added_by') == email:
                user_codes.append({
                    'code': item['code'],
                    'email': email,
                    'status': item.get('status'),
                    'last_checked': item.get('last_checked'),
                    'added_at': item.get('added_at')
                })
        
        self._send_json_response(200, {'codes': user_codes})
    
    def _handle_delete_code(self, data):
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip().upper()
        verification_code = data.get('verification_code', '').strip()
        
        if not all([email, code, verification_code]):
            self._send_json_response(400, {'error': 'Email, code, and verification code are required'})
            return
        
        # Check verification code
        status_data = self._load_status_data()
        stored = status_data.get('user_management', {}).get('verification_codes', {}).get(email)
        
        if not stored:
            self._send_json_response(400, {'error': 'Verification code expired or invalid'})
            return
        
        expires = datetime.fromisoformat(stored['expires'])
        if datetime.now() > expires or stored['code'] != verification_code:
            self._send_json_response(400, {'error': 'Invalid or expired verification code'})
            return
        
        # Remove from status.json
        items = status_data.get('items', {})
        if code in items and items[code].get('added_by') == email:
            del items[code]
            self._save_status_data(status_data)
        
        # Remove from .env config
        try:
            self._remove_from_env_config(code)
        except Exception as e:
            print(f"[{_now_iso()}] Failed to remove from .env: {e}")
        
        self._send_json_response(200, {'message': 'Code deleted successfully'})


# Background task to clean up expired data
def cleanup_expired_data(site_dir='site'):
    """Clean up expired verification codes and pending additions"""
    while True:
        try:
            status_path = os.path.join(site_dir, "status.json")
            if os.path.exists(status_path):
                with open(status_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                now = datetime.now()
                changed = False
                
                # Clean expired verification codes
                verification_codes = data.get('user_management', {}).get('verification_codes', {})
                expired_codes = []
                for email, code_data in verification_codes.items():
                    expires = datetime.fromisoformat(code_data['expires'])
                    if now > expires:
                        expired_codes.append(email)
                
                for email in expired_codes:
                    del verification_codes[email]
                    changed = True
                
                # Clean expired pending additions
                pending_additions = data.get('user_management', {}).get('pending_additions', {})
                expired_tokens = []
                for token, addition_data in pending_additions.items():
                    expires = datetime.fromisoformat(addition_data['expires'])
                    if now > expires:
                        expired_tokens.append(token)
                
                for token in expired_tokens:
                    del pending_additions[token]
                    changed = True
                
                # Save if changed
                if changed:
                    with open(status_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"[{_now_iso()}] Cleaned up expired data")
        
        except Exception as e:
            print(f"[{_now_iso()}] Error during cleanup: {e}")
        
        # Run every 5 minutes
        time.sleep(300)


def start_cleanup_thread(site_dir='site'):
    """Start the background cleanup thread"""
    cleanup_thread = threading.Thread(
        target=cleanup_expired_data, 
        args=(site_dir,), 
        daemon=True
    )
    cleanup_thread.start()
    return cleanup_thread