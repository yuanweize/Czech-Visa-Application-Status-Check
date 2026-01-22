"""
Code storage manager for new config layout under site/config

- status.json: env-managed codes statuses only (no user management)
- users.json: user-added codes and sessions/verification data

Provides:
- ensure_initialized(): create folders/files; migrate old site/status.json
- load/save for status and users
- merge_codes(): merge env codes (from MonitorConfig) with user codes
- update_item(origin, code, updated_item): write to proper file
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any

from .config import MonitorConfig, CodeConfig


def _now_iso() -> str:
    return datetime.now().isoformat()


@dataclass
class ManagedCode:
    code: str
    origin: str  # 'env' | 'user'
    config: CodeConfig
    # existing stored item if any (status fields)
    item: Optional[Dict[str, Any]] = None


class CodeStorageManager:
    def __init__(self, site_dir: str):
        self.site_dir = site_dir
        self.config_dir = os.path.join(site_dir, 'config')
        self.status_path = os.path.join(self.config_dir, 'status.json')
        self.users_path = os.path.join(self.config_dir, 'users.json')
        self.legacy_status_path = os.path.join(site_dir, 'status.json')

    # ---------- initialization & migration ----------
    def ensure_initialized(self):
        os.makedirs(self.config_dir, exist_ok=True)
        # Migrate legacy site/status.json -> site/config/status.json
        if not os.path.exists(self.status_path):
            legacy = self._read_json_safe(self.legacy_status_path)
            if legacy is not None:
                # Drop user_management from legacy when migrating
                data = {
                    'generated_at': legacy.get('generated_at') or _now_iso(),
                    'items': legacy.get('items') or {}
                }
                self._write_json(self.status_path, data)
            else:
                # Create fresh empty status
                self._write_json(self.status_path, {
                    'generated_at': _now_iso(),
                    'items': {}
                })
        # Initialize users.json if missing
        if not os.path.exists(self.users_path):
            self._write_json(self.users_path, {
                'generated_at': _now_iso(),
                'codes': {},
                'sessions': {},
                'verification_codes': {},
                'pending_additions': {}
            })

    # ---------- low-level IO ----------
    def _read_json_safe(self, path: str) -> Optional[Dict[str, Any]]:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
        except Exception:
            return None
        return None

    def _write_json(self, path: str, data: Dict[str, Any]):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ---------- status.json (env) ----------
    def load_status(self) -> Dict[str, Any]:
        self.ensure_initialized()
        data = self._read_json_safe(self.status_path)
        if data is None:
            data = {'generated_at': _now_iso(), 'items': {}}
            self._write_json(self.status_path, data)
        return data

    def save_status(self, data: Dict[str, Any]):
        data = data or {}
        if 'generated_at' not in data:
            data['generated_at'] = _now_iso()
        if 'items' not in data:
            data['items'] = {}
        self._write_json(self.status_path, data)

    # ---------- users.json (user) ----------
    def load_users(self) -> Dict[str, Any]:
        self.ensure_initialized()
        data = self._read_json_safe(self.users_path)
        if data is None:
            data = {
                'generated_at': _now_iso(),
                'codes': {},
                'sessions': {},
                'verification_codes': {},
                'pending_additions': {}
            }
            self._write_json(self.users_path, data)
        return data

    def save_users(self, data: Dict[str, Any]):
        if data is None:
            return
        if 'generated_at' not in data:
            data['generated_at'] = _now_iso()
        for k in ('codes', 'sessions', 'verification_codes', 'pending_additions'):
            data.setdefault(k, {})
        # 清理空结构，避免让用户误解（保持文件简洁）
        compact = dict(data)
        for k in ('verification_codes', 'pending_additions'):
            if isinstance(compact.get(k), dict) and len(compact.get(k)) == 0:
                compact.pop(k, None)
        self._write_json(self.users_path, compact)

    # ---------- merge & update ----------
    def merge_codes(self, config: MonitorConfig) -> List[ManagedCode]:
        """Merge env codes (from .env config) with user-added codes (from users.json)."""
        status = self.load_status()
        users = self.load_users()
        items = status.get('items', {}) or {}
        user_codes = users.get('codes', {}) or {}

        result: List[ManagedCode] = []
        # env codes from config
        cfg_map = {c.code: c for c in (config.codes or [])}
        for code, c in cfg_map.items():
            stored_item = items.get(code)
            result.append(ManagedCode(code=code, origin='env', config=c, item=stored_item))
        # user codes
        for code, rec in user_codes.items():
            # Build a CodeConfig using stored user target
            target_email = rec.get('target')
            # Normalize missing fields in user record for downstream consumers
            if 'channel' not in rec or not rec.get('channel'):
                rec['channel'] = 'email'
            # Ensure target exists (it is the sole email address field we keep)
            freq_val = rec.get('freq_minutes')
            if isinstance(freq_val, str):
                try:
                    freq_val = int(freq_val)
                except Exception:
                    freq_val = None
            user_cfg = CodeConfig(code=code, channel='email', target=target_email, freq_minutes=freq_val, note=rec.get('note'))
            result.append(ManagedCode(code=code, origin='user', config=user_cfg, item=rec))
        return result

    def update_item(self, origin: str, code: str, updated_item: Dict[str, Any]):
        """Write updated status item to the corresponding storage based on origin."""
        if origin == 'env':
            data = self.load_status()
            items = data.setdefault('items', {})
            items[code] = updated_item
            data['generated_at'] = _now_iso()
            self.save_status(data)
        else:
            users = self.load_users()
            codes = users.setdefault('codes', {})
            # Normalize channel to lowercase 'email' for user-managed entries when notifications are enabled
            if updated_item.get('channel'):
                updated_item['channel'] = str(updated_item['channel']).lower()
            # Do not store separate 'email' field; rely solely on 'target'
            updated_item.pop('email', None)
            codes[code] = updated_item
            users['generated_at'] = _now_iso()
            self.save_users(users)

    # Helpers for API layer
    def add_pending_addition(self, token: str, code: str, email: str, expires_iso: str):
        users = self.load_users()
        pend = users.setdefault('pending_additions', {})
        pend[token] = {'code': code, 'email': email, 'expires': expires_iso}
        users['generated_at'] = _now_iso()
        self.save_users(users)

    def pop_pending_addition(self, token: str) -> Optional[Dict[str, Any]]:
        users = self.load_users()
        pend = users.setdefault('pending_additions', {})
        rec = pend.pop(token, None)
        self.save_users(users)
        return rec

    def add_user_code(self, code: str, email: str):
        users = self.load_users()
        codes = users.setdefault('codes', {})
        codes[code] = {
            'code': code,
            'channel': 'email',
            'target': email,
            'status': 'Pending/等待查询',
            'last_checked': None,
            'last_changed': None,
            'first_check': True,
            'uses_default_freq': True,
        }
        users['generated_at'] = _now_iso()
        self.save_users(users)

    def remove_user_code(self, code: str):
        users = self.load_users()
        codes = users.setdefault('codes', {})
        if code in codes:
            del codes[code]
            self.save_users(users)

    def add_session(self, session_id: str, email: str, expires_at: str):
        users = self.load_users()
        sessions = users.setdefault('sessions', {})
        sessions[session_id] = {
            'email': email,
            'created_at': _now_iso(),
            'expires_at': expires_at,
            'last_used': _now_iso(),
        }
        self.save_users(users)

    def update_session_last_used(self, session_id: str):
        users = self.load_users()
        sessions = users.setdefault('sessions', {})
        if session_id in sessions:
            sessions[session_id]['last_used'] = _now_iso()
            self.save_users(users)

    def remove_session(self, session_id: str):
        users = self.load_users()
        sessions = users.setdefault('sessions', {})
        if session_id in sessions:
            del sessions[session_id]
            self.save_users(users)

    def set_verification_code(self, email: str, code: str, expires_iso: str, vtype: str = 'manage'):
        users = self.load_users()
        ver = users.setdefault('verification_codes', {})
        ver[email] = {'code': code, 'expires': expires_iso, 'type': vtype}
        self.save_users(users)

    def pop_verification_code(self, email: str) -> Optional[Dict[str, Any]]:
        users = self.load_users()
        ver = users.setdefault('verification_codes', {})
        rec = ver.pop(email, None)
        self.save_users(users)
        return rec

    def get_public_items(self) -> Dict[str, Dict[str, Any]]:
        """Merge env and user items for public exposure without sensitive fields."""
        status = self.load_status()
        users = self.load_users()
        public: Dict[str, Dict[str, Any]] = {}
        # env
        for code, item in (status.get('items') or {}).items():
            public[code] = {
                'code': item.get('code', code),
                'status': item.get('status'),
                'last_checked': item.get('last_checked'),
                'last_changed': item.get('last_changed'),
                'next_check': item.get('next_check'),
                'note': item.get('note'),
            }
        # user
        for code, item in (users.get('codes') or {}).items():
            public[code] = {
                'code': code,
                'status': item.get('status'),
                'last_checked': item.get('last_checked'),
                'last_changed': item.get('last_changed'),
                'next_check': item.get('next_check'),
                'note': item.get('note'),
            }
        return public
