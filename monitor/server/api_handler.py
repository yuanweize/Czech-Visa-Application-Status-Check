#!/usr/bin/env python3
"""
User Management API Module for Czech Visa Monitor
用户管理API模块

This module provides API handlers for user code management functionality
that can be imported and integrated into the main scheduler.
"""

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
from monitor.core.code_manager import CodeStorageManager
from monitor.notification import (
    send_verification_email,
    send_management_code_email,
    build_success_page,
    build_error_page
)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# Simple in-memory rate limiter
class RateLimiter:
    """Simple rate limiter using sliding window"""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}  # {client_ip: [timestamp, ...]}
        self._lock = threading.Lock()
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if request from client_ip is allowed"""
        now = time.time()
        
        with self._lock:
            # Clean old requests
            if client_ip in self.requests:
                self.requests[client_ip] = [
                    req_time for req_time in self.requests[client_ip]
                    if now - req_time < self.window_seconds
                ]
            else:
                self.requests[client_ip] = []
            
            # Check if limit exceeded
            if len(self.requests[client_ip]) >= self.max_requests:
                return False
            
            # Add current request
            self.requests[client_ip].append(now)
            return True
    
    def get_stats(self, client_ip: str) -> dict:
        """Get rate limiting stats for client"""
        now = time.time()
        
        with self._lock:
            if client_ip not in self.requests:
                return {
                    'requests': 0, 
                    'remaining': self.max_requests,
                    'reset_time': int(now + self.window_seconds)
                }
            
            # Clean old requests
            recent_requests = [
                req_time for req_time in self.requests[client_ip]
                if now - req_time < self.window_seconds
            ]
            
            return {
                'requests': len(recent_requests),
                'remaining': max(0, self.max_requests - len(recent_requests)),
                'reset_time': int(now + self.window_seconds)
            }


# Global rate limiter instance
_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100 requests per minute


class APIHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, config_path='.env', site_dir='site', **kwargs):
        self.config_path = config_path
        self.site_dir = site_dir
        self._base_url = None  # Will be set when first request comes in
        self.store = CodeStorageManager(self.site_dir)
        self.store.ensure_initialized()
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        # Custom logging for API requests only
        if self.path.startswith('/api/'):
            print(f"[{_now_iso()}] API {format % args}")
    
    def _check_rate_limit(self) -> bool:
        """Check if request should be rate limited"""
        client_ip = self.client_address[0]
        
        # Always get stats and add headers
        stats = _rate_limiter.get_stats(client_ip)
        self._rate_limit_headers = {
            'X-RateLimit-Limit': str(_rate_limiter.max_requests),
            'X-RateLimit-Remaining': str(stats['remaining']),
            'X-RateLimit-Reset': str(stats['reset_time'])
        }
        
        # Allow localhost/development without actual rate limiting
        if client_ip in ['127.0.0.1', '::1', 'localhost']:
            return True
            
        if not _rate_limiter.is_allowed(client_ip):
            stats = _rate_limiter.get_stats(client_ip)
            print(f"[{_now_iso()}] RATE_LIMIT: Blocked {client_ip} - {stats['requests']} requests")
            
            # Send 429 Too Many Requests
            self.send_response(429)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Retry-After', '60')
            self.send_header('X-RateLimit-Limit', str(_rate_limiter.max_requests))
            self.send_header('X-RateLimit-Remaining', '0')
            self.send_header('X-RateLimit-Reset', str(stats['reset_time']))
            self.end_headers()
            
            response = {
                'error': 'Rate limit exceeded',
                'message': f'Maximum {_rate_limiter.max_requests} requests per {_rate_limiter.window_seconds} seconds',
                'retry_after': 60
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
            return False
        
        return True
    
    def _send_json_response(self, status_code: int, data: dict, extra_headers: dict | None = None):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        # Add extra headers if provided (e.g., Set-Cookie)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        
        # Add rate limit headers if available
        if hasattr(self, '_rate_limit_headers'):
            for header, value in self._rate_limit_headers.items():
                self.send_header(header, value)
        
        self.end_headers()
        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.wfile.write(response)
    
    def _send_html_response(self, status_code: int, html_content: str, extra_headers: dict | None = None):
        """Send HTML response for web page responses"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(html_content.encode('utf-8'))

    def _make_session_cookie(self, session_id: str | None, max_age_seconds: int = 7*24*3600) -> str:
        """Build Set-Cookie header value for session; pass session_id=None to clear."""
        name = 'visa_session_id'
        if session_id:
            cookie = f"{name}={session_id}; Path=/; Max-Age={max_age_seconds}; SameSite=Lax"
        else:
            cookie = f"{name}=; Path=/; Max-Age=0; SameSite=Lax"
        return cookie
    
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
        """Load env-managed status data (site/config/status.json)"""
        return self.store.load_status()
    
    def _save_status_data(self, data):
        """Save env-managed status data"""
        try:
            self.store.save_status(data)
            return True
        except Exception as e:
            print(f"[{_now_iso()}] Failed to save status data: {e}")
            return False
    
    def _generate_verification_code(self):
        """Generate 6-digit verification code"""
        return f"{secrets.randbelow(900000) + 100000:06d}"
    
    def _add_to_env_config(self, code: str, email: str):
        """Deprecated: No longer writes to .env; user codes stored in users.json."""
        raise RuntimeError("Writing to .env is disabled in new storage architecture")
    
    def _remove_from_env_config(self, code: str):
        """Deprecated: .env is not modified for user codes."""
        return
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        # Check rate limit first
        if not self._check_rate_limit():
            return
            
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
        # Check rate limit first for API requests
        if self.path.startswith('/api/') and not self._check_rate_limit():
            return
            
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        # Handle API endpoints
        if path.startswith('/api/verify-add/'):
            token = path.replace('/api/verify-add/', '')
            self._handle_verify_add(token)
        elif path == '/api/public-status':
            # Safe public status endpoint without sensitive data
            self._handle_public_status()
        elif path.startswith('/api/'):
            # Other API endpoints should be POST - redirect non-business logic error
            self._send_error_redirect(405, 'Method not allowed')
        elif path.startswith('/.well-known/'):
            # Handle well-known URIs (for Chrome DevTools, etc.) silently
            self._handle_well_known_request(path)
        else:
            # Handle static files
            self._serve_static_file()
    
    def _handle_well_known_request(self, path):
        """Handle .well-known requests silently to reduce log noise"""
        # For Chrome DevTools and other development tools
        if 'devtools' in path:
            # Return empty JSON for DevTools
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{}')
        else:
            # Other well-known requests - return 404 silently
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')
    
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
        
        # SECURITY: Block access to sensitive files
        blocked_files = {
            'status.json',      # Contains session data and sensitive information
            '.env',             # Environment configuration
            'config.json',      # Configuration files
            'backup.json',      # Backup files
        }
        
        # Common browser/dev tool requests that should be silently blocked
        silent_blocked_patterns = [
            '.well-known/',
            'favicon.ico',
            'robots.txt',
            'sitemap.xml',
            'manifest.json',
            '.git/',
            '.vscode/',
            '__pycache__/',
            'node_modules/',
        ]
        
        # Check if this is a silent block (browser/dev tools)
        is_silent_block = any(pattern in file_path for pattern in silent_blocked_patterns)
        
        # Also block any hidden files or files starting with dot, and any access to site/config
        if (
            file_path in blocked_files 
            or file_path.startswith('.') 
            or '/.env' in file_path 
            or '/status.json' in file_path
            or file_path.startswith('config/')
            or '/config/' in file_path
        ):
            if not is_silent_block:
                print(f"[{_now_iso()}] SECURITY: Blocked access to sensitive file: {file_path}")
            self._send_error_redirect(403, "Access denied")
            return
        
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
                # Compute a simple ETag from size and mtime
                try:
                    stat = full_path.stat()
                    etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
                except Exception:
                    etag = None
                # Handle If-None-Match for basic 304 support
                if etag and 'If-None-Match' in self.headers and self.headers.get('If-None-Match') == etag:
                    self.send_response(304)
                    self.send_header('ETag', etag)
                    # Minimal caching headers with 304
                    if content_type.startswith('text/html'):
                        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    else:
                        self.send_header('Cache-Control', 'public, max-age=172800')  # 48h
                    self.end_headers()
                    return
                
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(content)))
                # Caching: HTML no-cache to avoid stale pages; assets cached for 48h
                if content_type.startswith('text/html'):
                    # Allow revalidation while avoiding staleness
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                else:
                    self.send_header('Cache-Control', 'public, max-age=172800')  # 48h
                if etag:
                    self.send_header('ETag', etag)
                self.end_headers()
                self.wfile.write(content)
            else:
                # Check if this is a common browser request that should be handled silently
                common_browser_files = [
                    'favicon.ico', 'robots.txt', 'sitemap.xml', 'manifest.json',
                    'apple-touch-icon.png', 'browserconfig.xml'
                ]
                
                if file_path in common_browser_files:
                    # Send 404 without logging to reduce noise
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Not Found')
                else:
                    self._send_error_redirect(404, 'File not found')
        except Exception as e:
            self._send_error_redirect(500, f'Internal server error: {e}')
    
    def _handle_add_code(self, data):
        code = data.get('code', '').strip().upper()
        email = data.get('email', '').strip().lower()
        captcha_answer = data.get('captcha_answer')
        
        print(f"[{_now_iso()}] API request: add-code for {code} to {email}")
        
        # Validate input
        if not code or not email:
            print(f"[{_now_iso()}] API error: Missing code or email")
            self._send_json_response(400, {'error': 'Code and email are required'})
            return
        
        # Validate code format
        if not re.match(r'^[A-Z]{4}\d{12}$', code):
            print(f"[{_now_iso()}] API error: Invalid code format: {code}")
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
        
        # 检查 users.json 中的现有记录（用户添加的代码）
        users_data = self.store.load_users()
        user_codes = users_data.get('codes', {})
        if code in user_codes:
            existing_email = user_codes[code].get('target', 'unknown')
            if existing_email == email:
                self._send_json_response(400, {'error': 'This code is already being monitored for this email'})
                return
            else:
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
        
        # Save pending addition to users.json
        self.store.add_pending_addition(token, code, email, expires)
        print(f"[{_now_iso()}] Generated verification token for {email}")
        
        # Generate verification URL using cached base_url
        verification_url = f"{self.base_url}/api/verify-add/{token}"
        
        # Prepare SMTP configuration
        config = self._load_config()
        
        # Validate SMTP configuration
        if not config.smtp_host:
            print(f"[{_now_iso()}] SMTP error: No SMTP host configured")
            self._send_json_response(500, {'error': 'Email service not configured'})
            return
        
        smtp_config = {
            'host': config.smtp_host,
            'port': config.smtp_port,
            'user': config.smtp_user,
            'pass': config.smtp_pass,
            'from': config.smtp_from
        }
        
        print(f"[{_now_iso()}] Sending verification email to {email}")
        try:
            success, error = send_verification_email(email, code, verification_url, self.base_url, smtp_config, self.config_path)
            
            if success:
                print(f"[{_now_iso()}] Email sent successfully to {email}")
                self._send_json_response(200, {'message': 'Verification email sent successfully'})
            else:
                print(f"[{_now_iso()}] Email sending failed to {email}: {error}")
                self._send_json_response(500, {'error': f'Failed to send email: {error}'})
        except Exception as e:
            print(f"[{_now_iso()}] Email sending exception for {email}: {e}")
            self._send_json_response(500, {'error': f'Email service error: {str(e)}'})
    
    def _handle_verify_add(self, token):
        users_data = self.store.load_users()
        pending = users_data.get('pending_additions', {}).get(token)
        
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
            users_data['pending_additions'].pop(token, None)
            self.store.save_users(users_data)
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
        
        # Add to users.json codes
        self.store.add_user_code(code, email)

        # Create a session for this user to enable seamless management
        session_id = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()
        self.store.add_session(session_id, email, expires_at)
        # Remove from pending
        self.store.pop_pending_addition(token)
        
        print(f"[{_now_iso()}] Successfully added code {code} for {email}, session created: {session_id[:8]}...")
        # 立即加入队列进行首次查询（插队到队首）
        try:
            from monitor.core.scheduler import schedule_user_code_immediately
            ok = schedule_user_code_immediately(code)
            if ok:
                print(f"[{_now_iso()}] Scheduled newly added user code immediately: {code}")
        except Exception as e:
            print(f"[{_now_iso()}] Failed to schedule user code immediately: {e}")
        
        # Success - return HTML page with embedded session
        success_html = build_success_page(
            code=code,
            message=f"Code {code} has been successfully added to the monitoring system. You will receive email notifications when the status changes.",
            base_url=self.base_url,
            session_id=session_id  # Pass session to success page
        )
        # Set cookie for 7 days to persist session in browser
        headers = {'Set-Cookie': self._make_session_cookie(session_id)}
        self._send_html_response(200, success_html, extra_headers=headers)
    
    def _handle_send_manage_code(self, data):
        email = data.get('email', '').strip().lower()
        
        print(f"[{_now_iso()}] API request: send-manage-code for {email}")
        
        if not email:
            print(f"[{_now_iso()}] API error: Missing email")
            self._send_json_response(400, {'error': 'Email is required'})
            return
        
        # Check if this email has any codes (users.json)
        users_data = self.store.load_users()
        items = users_data.get('codes', {})
        user_codes = [item for item in items.values() if item.get('target') == email]
        
        if not user_codes:
            print(f"[{_now_iso()}] API error: No codes found for {email}")
            self._send_json_response(404, {'error': 'No codes found for this email address'})
            return
        
        # Generate verification code
        verification_code = self._generate_verification_code()
        expires = (datetime.now() + timedelta(minutes=10)).isoformat()
        
        self.store.set_verification_code(email, verification_code, expires, vtype='manage')
        print(f"[{_now_iso()}] Generated management code for {email}")
        
        # Prepare SMTP configuration
        config = self._load_config()
        
        # Validate SMTP configuration
        if not config.smtp_host:
            print(f"[{_now_iso()}] SMTP error: No SMTP host configured")
            self._send_json_response(500, {'error': 'Email service not configured'})
            return
        
        smtp_config = {
            'host': config.smtp_host,
            'port': config.smtp_port,
            'user': config.smtp_user,
            'pass': config.smtp_pass,
            'from': config.smtp_from
        }
        
        print(f"[{_now_iso()}] Sending management code email to {email}")
        try:
            success, error = send_management_code_email(email, verification_code, smtp_config, self.config_path)
            
            if success:
                print(f"[{_now_iso()}] Management code email sent successfully to {email}")
                self._send_json_response(200, {'message': 'Verification code sent successfully'})
            else:
                print(f"[{_now_iso()}] Management code email failed to {email}: {error}")
                self._send_json_response(500, {'error': f'Failed to send email: {error}'})
        except Exception as e:
            print(f"[{_now_iso()}] Management code email exception for {email}: {e}")
            self._send_json_response(500, {'error': f'Email service error: {str(e)}'})
    
    def _handle_verify_manage(self, data):
        # Support both verification code and session authentication against users.json
        email = data.get('email', '').strip().lower()
        verification_code = data.get('verification_code', '').strip()
        session_id = data.get('session_id', '').strip()

        users_data = self.store.load_users()

        # Session authentication method
        if session_id:
            sessions = users_data.get('sessions', {})
            session = sessions.get(session_id)

            if not session:
                self._send_json_response(401, {'error': 'Invalid session'})
                return

            # Check expiration
            expires = datetime.fromisoformat(session['expires_at'])
            if datetime.now() > expires:
                del sessions[session_id]
                self.store.save_users(users_data)
                self._send_json_response(401, {'error': 'Session expired'})
                return

            # Update last used
            session['last_used'] = _now_iso()
            self.store.save_users(users_data)
            email = session['email']

        # Verification code method
        elif email and verification_code:
            stored = users_data.get('verification_codes', {}).get(email)

            if not stored:
                self._send_json_response(400, {'error': 'No verification code found for this email'})
                return

            # Check expiry
            expires = datetime.fromisoformat(stored['expires'])
            if datetime.now() > expires:
                users_data['verification_codes'].pop(email, None)
                self.store.save_users(users_data)
                self._send_json_response(400, {'error': 'Verification code has expired'})
                return

            # Check code
            if stored['code'] != verification_code:
                self._send_json_response(400, {'error': 'Invalid verification code'})
                return

            # Create session for this user for seamless management
            session_id = secrets.token_urlsafe(32)
            expires_at = (datetime.now() + timedelta(days=7)).isoformat()
            self.store.add_session(session_id, email, expires_at)
            # Remove used verification code
            self.store.pop_verification_code(email)

            print(f"[{_now_iso()}] Created management session for {email}: {session_id[:8]}...")

        else:
            self._send_json_response(400, {'error': 'Email and verification code, or session ID required'})
            return

        # Get user codes from users.json
        user_codes = []
        for c, rec in users_data.get('codes', {}).items():
            if rec.get('target') == email:
                user_codes.append({
                    'code': c,
                    'status': rec.get('status'),
                    'last_checked': rec.get('last_checked'),
                    'next_check': rec.get('next_check'),
                    'added_at': rec.get('added_at'),
                    'note': rec.get('note')
                })

        response_data = {'codes': user_codes}
        # Include session_id in response if we just created one
        if session_id:
            response_data['session_id'] = session_id
            extra = {'Set-Cookie': self._make_session_cookie(session_id)}
            self._send_json_response(200, response_data, extra_headers=extra)
        else:
            self._send_json_response(200, response_data)
    
    def _handle_delete_code(self, data):
        email = data.get('email', '').strip().lower()
        code = data.get('code', '').strip().upper()
        verification_code = data.get('verification_code', '').strip()
        session_id = data.get('session_id', '').strip()
        
        if not code:
            self._send_json_response(400, {'error': 'Code is required'})
            return
        
        users_data = self.store.load_users()

        # Session authentication method
        if session_id:
            sessions = users_data.get('sessions', {})
            session = sessions.get(session_id)

            if not session:
                self._send_json_response(401, {'error': 'Invalid session'})
                return

            # Check expiration
            expires = datetime.fromisoformat(session['expires_at'])
            if datetime.now() > expires:
                del sessions[session_id]
                self.store.save_users(users_data)
                self._send_json_response(401, {'error': 'Session expired'})
                return

            # Update last used
            session['last_used'] = _now_iso()
            self.store.save_users(users_data)
            email = session['email']

        # Verification code method
        elif email and verification_code:
            stored = users_data.get('verification_codes', {}).get(email)

            if not stored:
                self._send_json_response(400, {'error': 'Verification code expired or invalid'})
                return

            expires = datetime.fromisoformat(stored['expires'])
            if datetime.now() > expires or stored['code'] != verification_code:
                self._send_json_response(400, {'error': 'Invalid or expired verification code'})
                return

            # consume verification code
            self.store.pop_verification_code(email)
        else:
            self._send_json_response(400, {'error': 'Email and verification code, or session ID required'})
            return

        # Remove from users.json if owned by email
        codes = users_data.get('codes', {})
        if code in codes and (codes[code].get('target') == email):
            self.store.remove_user_code(code)
            self._send_json_response(200, {'message': 'Code deleted successfully'})
        else:
            self._send_json_response(404, {'error': 'Code not found for this user'})

    def _handle_login(self, data):
        """Handle user login request"""
        email = data.get('email', '').strip().lower()
        verification_code = data.get('verification_code', '').strip()
        
        if not email or not verification_code:
            self._send_json_response(400, {'error': 'Email and verification code are required'})
            return
        
        users_data = self.store.load_users()
        stored = users_data.get('verification_codes', {}).get(email)

        if not stored:
            self._send_json_response(400, {'error': 'No verification code found for this email'})
            return

        # Check expiration and code
        expires = datetime.fromisoformat(stored['expires'])
        if datetime.now() > expires or stored['code'] != verification_code:
            self._send_json_response(400, {'error': 'Invalid or expired verification code'})
            return

        # Create session (7 days)
        session_id = secrets.token_urlsafe(32)
        session_expires = datetime.now() + timedelta(days=7)
        self.store.add_session(session_id, email, session_expires.isoformat())
        # Remove verification code since it's been used
        self.store.pop_verification_code(email)

        # Include cookie for session persistence
        self._send_json_response(
            200,
            {
                'message': 'Login successful',
                'session_id': session_id,
                'expires': session_expires.isoformat()
            },
            extra_headers={'Set-Cookie': self._make_session_cookie(session_id)}
        )

    def _handle_logout(self, data):
        """Handle user logout request"""
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            self._send_json_response(400, {'error': 'Session ID is required'})
            return
        
        users_data = self.store.load_users()
        sessions = users_data.get('sessions', {})

        if session_id in sessions:
            self.store.remove_session(session_id)
            # Clear session cookie
            self._send_json_response(200, {'message': 'Logout successful'}, extra_headers={'Set-Cookie': self._make_session_cookie(None)})
        else:
            self._send_json_response(400, {'error': 'Invalid session ID'})

    def _handle_verify_session(self, data):
        """Handle session verification request"""
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            self._send_json_response(400, {'error': 'Session ID is required'})
            return
        
        users_data = self.store.load_users()
        sessions = users_data.get('sessions', {})
        session = sessions.get(session_id)
        
        if not session:
            self._send_json_response(401, {'error': 'Session not found'})
            return
        
        # Check expiration
        expires = datetime.fromisoformat(session['expires_at'])
        if datetime.now() > expires:
            del sessions[session_id]
            self.store.save_users(users_data)
            self._send_json_response(401, {'error': 'Session expired'})
            return
        
        # Update last used time
        session['last_used'] = _now_iso()
        self.store.save_users(users_data)
        
        self._send_json_response(200, {
            'valid': True,
            'email': session['email'],
            'expires': session['expires_at']
        })

    def _handle_public_status(self):
        """Get public status data without sensitive information"""
        try:
            # Merge env + user items without sensitive fields
            items = self.store.get_public_items()
            status_data = self.store.load_status()
            users_data = self.store.load_users()
            generated_at = status_data.get('generated_at')
            # Prefer latest timestamp
            try:
                gen_status = datetime.fromisoformat(generated_at) if generated_at else None
                gen_users = datetime.fromisoformat(users_data.get('generated_at')) if users_data.get('generated_at') else None
                latest = max([dt for dt in [gen_status, gen_users] if dt is not None]) if (gen_status or gen_users) else datetime.now()
                generated_at = latest.isoformat()
            except Exception:
                generated_at = _now_iso()

            public_data = {
                'generated_at': generated_at,
                'items': items
            }
            self._send_json_response(200, public_data)
        except Exception as e:
            print(f"[{_now_iso()}] Error getting public status: {e}")
            self._send_json_response(500, {'error': 'Internal server error'})

    def _send_error_redirect(self, error_code: int, error_message: str = ""):
        """Send redirect to external error page for non-business logic errors"""
        # Define which errors should be redirected
        redirect_errors = {400, 401, 403, 404, 405, 429, 500, 502, 503, 504}
        
        # Reduce logging noise for common browser requests
        should_log = True
        if error_code == 404 and hasattr(self, 'path'):
            # Don't log 404s for common browser/dev tool files
            common_files = ['favicon.ico', 'robots.txt', 'manifest.json', '.well-known/', 'apple-touch-icon']
            if any(file in self.path for file in common_files):
                should_log = False
        elif error_code == 403 and hasattr(self, 'path'):
            # Reduce logging for blocked dev tool requests
            if '.well-known/' in self.path or 'devtools' in self.path:
                should_log = False
        
        if error_code in redirect_errors:
            self.send_response(302)
            self.send_header('Location', 'https://error.eurun.top/')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            if should_log:
                print(f"[{_now_iso()}] REDIRECT: Error {error_code} ({error_message}) - redirected to error page")
        else:
            # For other errors, use standard error handling
            self.send_error(error_code, error_message)


# Background task to clean up expired data
def cleanup_expired_data(site_dir='site'):
    """Clean up expired verification codes, pending additions, and sessions in users.json"""
    store = CodeStorageManager(site_dir)
    store.ensure_initialized()
    while True:
        try:
            users = store.load_users()
            now = datetime.now()
            changed = False

            # Clean expired verification codes
            verification_codes = users.get('verification_codes', {})
            expired_codes = []
            for email, code_data in list(verification_codes.items()):
                try:
                    expires = datetime.fromisoformat(code_data['expires'])
                    if now > expires:
                        expired_codes.append(email)
                except Exception:
                    expired_codes.append(email)
            for email in expired_codes:
                verification_codes.pop(email, None)
                changed = True

            # Clean expired pending additions
            pending_additions = users.get('pending_additions', {})
            expired_tokens = []
            for token, addition_data in list(pending_additions.items()):
                try:
                    expires = datetime.fromisoformat(addition_data['expires'])
                    if now > expires:
                        expired_tokens.append(token)
                except Exception:
                    expired_tokens.append(token)
            for token in expired_tokens:
                pending_additions.pop(token, None)
                changed = True

            # Clean expired sessions
            sessions = users.get('sessions', {})
            expired_sessions = []
            for sid, session_data in list(sessions.items()):
                try:
                    expires = datetime.fromisoformat(session_data['expires_at'])
                    if now > expires:
                        expired_sessions.append(sid)
                except Exception:
                    expired_sessions.append(sid)
            for sid in expired_sessions:
                sessions.pop(sid, None)
                changed = True

            if changed:
                store.save_users(users)
                print(f"[{_now_iso()}] Cleaned up expired users.json data")
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