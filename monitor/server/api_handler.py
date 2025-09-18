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
import re
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from monitor.core.config import load_env_config
from monitor.notification import (
    send_email_sync, 
    build_verification_email,
    build_management_code_email,
    send_verification_email,
    send_management_code_email,
    build_success_page,
    build_error_page
)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class APIHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, config_path='.env', site_dir='site', **kwargs):
        self.config_path = config_path
        self.site_dir = site_dir
        self._base_url = None  # Will be set when first request comes in
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
    
    def _send_html_response(self, status_code: int, html_content: str):
        """Send HTML response for web page responses"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))
    
    def _load_config(self):
        """Load configuration from .env file"""
        return load_env_config(self.config_path)
    
    def _get_base_url(self):
        """Generate base URL from request headers (cached)"""
        if self._base_url is None:
            host_header = self.headers.get('Host', f'localhost:{self._load_config().site_port}')
            
            # Determine protocol based on common patterns
            if 'localhost' in host_header or host_header.startswith('127.0.0.1') or host_header.startswith('192.168.'):
                protocol = 'http'
            elif any(domain in host_header for domain in ['eurun.top', 'yuanweize.win']) or ':443' in host_header:
                protocol = 'https'
            else:
                # Default to https for production domains, http for others
                protocol = 'https' if '.' in host_header.split(':')[0] and not host_header.startswith('localhost') else 'http'
            
            self._base_url = f"{protocol}://{host_header}"
        
        return self._base_url
    
    @property
    def base_url(self):
        """Property for easy access to base URL"""
        return self._get_base_url()
    
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
                    "pending_additions": {},
                    "sessions": {}
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
        elif path == '/api/login':
            self._handle_login(data)
        elif path == '/api/logout':
            self._handle_logout(data)
        elif path == '/api/verify-session':
            self._handle_verify_session(data)
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
        
        # 简单重复检测 - 检查配置文件和status.json
        try:
            config = self._load_config()
            
            # 检查配置文件中是否已存在
            for code_config in config.codes:
                if code_config.code == code:
                    if code_config.target == email:
                        self._send_json_response(400, {
                            'error': 'This code is already being monitored for this email',
                            'details': 'You are already receiving notifications for this visa code.'
                        })
                        return
                    else:
                        # 隐藏部分邮箱信息保护隐私
                        if code_config.target and '@' in code_config.target:
                            masked_email = code_config.target[:3] + '***@' + code_config.target.split('@')[1]
                        else:
                            masked_email = 'hidden'
                        
                        self._send_json_response(400, {
                            'error': 'This code is already being monitored',
                            'details': f'This visa code is already being monitored for {masked_email}. If this is your code, please contact support.'
                        })
                        return
        except Exception as e:
            # 配置加载失败，记录错误但继续检查status.json
            print(f"[{_now_iso()}] Config load error during duplicate check: {e}")
        
        # 检查status.json中的现有记录
        status_data = self._load_status_data()
        items = status_data.get('items', {})
        if code in items:
            existing_email = items[code].get('added_by', items[code].get('target', 'unknown'))
            if existing_email == email:
                self._send_json_response(400, {'error': 'This code is already being monitored for this email'})
                return
            else:
                # 隐藏部分邮箱信息
                if existing_email and '@' in existing_email:
                    masked_email = existing_email[:3] + '***@' + existing_email.split('@')[1]
                else:
                    masked_email = 'hidden'
                self._send_json_response(400, {
                    'error': 'This code is already being monitored',
                    'details': f'This visa code is already being monitored for {masked_email}. If this is your code, please contact support.'
                })
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
        
        # Generate verification URL using cached base_url
        verification_url = f"{self.base_url}/api/verify-add/{token}"
        
        # Prepare SMTP configuration
        config = self._load_config()
        smtp_config = {
            'host': config.smtp_host,
            'port': config.smtp_port,
            'user': config.smtp_user,
            'pass': config.smtp_pass,
            'from': config.smtp_from
        }
        
        success, error = send_verification_email(email, code, verification_url, self.base_url, smtp_config, self.config_path)
        
        if success:
            self._send_json_response(200, {'message': 'Verification email sent successfully'})
        else:
            self._send_json_response(500, {'error': f'Failed to send email: {error}'})
    
    def _handle_verify_add(self, token):
        status_data = self._load_status_data()
        pending = status_data.get('user_management', {}).get('pending_additions', {}).get(token)
        
        if not pending:
            error_html = build_error_page(
                error_title="Invalid Verification Link",
                error_message="This verification link is invalid or has already been used.",
                base_url=self.base_url,
                details="The link may have expired or been used already. Please submit a new request from the main site."
            )
            self._send_html_response(400, error_html)
            return
        
        # Check expiry
        expires = datetime.fromisoformat(pending['expires'])
        if datetime.now() > expires:
            del status_data['user_management']['pending_additions'][token]
            self._save_status_data(status_data)
            error_html = build_error_page(
                error_title="Link Expired",
                error_message="This verification link has expired.",
                base_url=self.base_url,
                details="Verification links expire after 10 minutes for security reasons. Please submit a new request from the main site."
            )
            self._send_html_response(400, error_html)
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
            error_html = build_error_page(
                error_title="Configuration Error",
                error_message="Failed to add code to monitoring configuration.",
                base_url=self.base_url,
                details="The code was recorded but may not be monitored until the configuration is updated. Please contact support."
            )
            self._send_html_response(500, error_html)
            return
        
        # Success - return HTML page
        success_html = build_success_page(
            code=code,
            message=f"Code {code} has been successfully added to the monitoring system. You will receive email notifications when the status changes.",
            base_url=self.base_url
        )
        self._send_html_response(200, success_html)
    
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
        
        # Prepare SMTP configuration
        config = self._load_config()
        smtp_config = {
            'host': config.smtp_host,
            'port': config.smtp_port,
            'user': config.smtp_user,
            'pass': config.smtp_pass,
            'from': config.smtp_from
        }
        
        success, error = send_management_code_email(email, verification_code, smtp_config, self.config_path)
        
        if success:
            self._send_json_response(200, {'message': 'Verification code sent successfully'})
        else:
            self._send_json_response(500, {'error': f'Failed to send email: {error}'})
    
    def _handle_verify_manage(self, data):
        # Support both verification code and session authentication
        email = data.get('email', '').strip().lower()
        verification_code = data.get('verification_code', '').strip()
        session_id = data.get('session_id', '').strip()
        
        status_data = self._load_status_data()
        
        # Session authentication method
        if session_id:
            sessions = status_data.get('user_management', {}).get('sessions', {})
            session = sessions.get(session_id)
            
            if not session:
                self._send_json_response(401, {'error': 'Invalid session'})
                return
            
            # Check expiration
            expires = datetime.fromisoformat(session['expires'])
            if datetime.now() > expires:
                del sessions[session_id]
                self._save_status_data(status_data)
                self._send_json_response(401, {'error': 'Session expired'})
                return
            
            # Update last used
            session['last_used'] = _now_iso()
            self._save_status_data(status_data)
            email = session['email']
            
        # Verification code method (legacy)
        elif email and verification_code:
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
        else:
            self._send_json_response(400, {'error': 'Email and verification code, or session ID required'})
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
                    'next_check': item.get('next_check'),
                    'added_at': item.get('added_at'),
                    'note': item.get('note')
                })
        
        self._send_json_response(200, {'codes': user_codes})
    
    def _handle_delete_code(self, data):
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip().upper()
        verification_code = data.get('verification_code', '').strip()
        session_id = data.get('session_id', '').strip()
        
        if not code:
            self._send_json_response(400, {'error': 'Code is required'})
            return
        
        status_data = self._load_status_data()
        
        # Session authentication method
        if session_id:
            sessions = status_data.get('user_management', {}).get('sessions', {})
            session = sessions.get(session_id)
            
            if not session:
                self._send_json_response(401, {'error': 'Invalid session'})
                return
            
            # Check expiration
            expires = datetime.fromisoformat(session['expires'])
            if datetime.now() > expires:
                del sessions[session_id]
                self._save_status_data(status_data)
                self._send_json_response(401, {'error': 'Session expired'})
                return
            
            # Update last used
            session['last_used'] = _now_iso()
            self._save_status_data(status_data)
            email = session['email']
            
        # Verification code method (legacy)
        elif email and verification_code:
            stored = status_data.get('user_management', {}).get('verification_codes', {}).get(email)
            
            if not stored:
                self._send_json_response(400, {'error': 'Verification code expired or invalid'})
                return
            
            expires = datetime.fromisoformat(stored['expires'])
            if datetime.now() > expires or stored['code'] != verification_code:
                self._send_json_response(400, {'error': 'Invalid or expired verification code'})
                return
        else:
            self._send_json_response(400, {'error': 'Email and verification code, or session ID required'})
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

    def _handle_login(self, data):
        """Handle user login request"""
        email = data.get('email', '').strip().lower()
        verification_code = data.get('verification_code', '').strip()
        
        if not email or not verification_code:
            self._send_json_response(400, {'error': 'Email and verification code are required'})
            return
        
        status_data = self._load_status_data()
        stored = status_data.get('user_management', {}).get('verification_codes', {}).get(email)
        
        if not stored:
            self._send_json_response(400, {'error': 'No verification code found for this email'})
            return
        
        # Check expiration and code
        expires = datetime.fromisoformat(stored['expires'])
        if datetime.now() > expires or stored['code'] != verification_code:
            self._send_json_response(400, {'error': 'Invalid or expired verification code'})
            return
        
        # Create session (7 days)
        import secrets
        session_id = secrets.token_urlsafe(32)
        session_expires = datetime.now() + timedelta(days=7)
        
        status_data.setdefault('user_management', {}).setdefault('sessions', {})[session_id] = {
            'email': email,
            'created': _now_iso(),
            'expires': session_expires.isoformat(),
            'last_used': _now_iso()
        }
        
        # Remove verification code since it's been used
        del status_data['user_management']['verification_codes'][email]
        
        self._save_status_data(status_data)
        self._send_json_response(200, {
            'message': 'Login successful',
            'session_id': session_id,
            'expires': session_expires.isoformat()
        })

    def _handle_logout(self, data):
        """Handle user logout request"""
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            self._send_json_response(400, {'error': 'Session ID is required'})
            return
        
        status_data = self._load_status_data()
        sessions = status_data.get('user_management', {}).get('sessions', {})
        
        if session_id in sessions:
            del sessions[session_id]
            self._save_status_data(status_data)
            self._send_json_response(200, {'message': 'Logout successful'})
        else:
            self._send_json_response(400, {'error': 'Invalid session ID'})

    def _handle_verify_session(self, data):
        """Handle session verification request"""
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            self._send_json_response(400, {'error': 'Session ID is required'})
            return
        
        status_data = self._load_status_data()
        sessions = status_data.get('user_management', {}).get('sessions', {})
        session = sessions.get(session_id)
        
        if not session:
            self._send_json_response(401, {'error': 'Session not found'})
            return
        
        # Check expiration
        expires = datetime.fromisoformat(session['expires'])
        if datetime.now() > expires:
            del sessions[session_id]
            self._save_status_data(status_data)
            self._send_json_response(401, {'error': 'Session expired'})
            return
        
        # Update last used time
        session['last_used'] = _now_iso()
        self._save_status_data(status_data)
        
        self._send_json_response(200, {
            'valid': True,
            'email': session['email'],
            'expires': session['expires']
        })


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
                
                # Clean expired sessions (7 days)
                sessions = data.get('user_management', {}).get('sessions', {})
                expired_sessions = []
                for session_id, session_data in sessions.items():
                    expires = datetime.fromisoformat(session_data['expires'])
                    if now > expires:
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    del sessions[session_id]
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