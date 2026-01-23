
import unittest
import threading
import json
import shutil
import os
import sys
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

# Adjust path to import monitor modules
sys.path.insert(0, os.getcwd())

from monitor.core.code_manager import CodeStorageManager
from monitor.server.api_handler import APIHandler

class TestSystemRefactor(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("test_site_env")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        (self.test_dir / "config").mkdir()
        
        # Initialize empty JSON files
        with open(self.test_dir / "config" / "users.json", "w") as f:
            json.dump({"codes": {}, "pending_additions": {}}, f)
        with open(self.test_dir / "config" / "status.json", "w") as f:
            json.dump({}, f)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_code_manager_concurrency(self):
        """Verify thread safety of CodeStorageManager"""
        manager = CodeStorageManager(str(self.test_dir))
        manager.ensure_initialized()
        
        def worker(idx):
            token = f"token_{idx}"
            code = f"TEST{idx}"
            manager.add_pending_addition(token, code, "test@example.com", "2025-01-01")
            
        threads = []
        for i in range(20):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # Verify all 20 items exist
        users = manager.load_users()
        self.assertEqual(len(users['pending_additions']), 20, "Race condition detected! Lost writes in pending_additions")

    def test_api_validation_oam(self):
        """Verify OAM input validation and code reconstruction"""
        # Properly instantiate APIHandler avoiding BaseHTTPRequestHandler init loop
        with patch('http.server.BaseHTTPRequestHandler.__init__') as mock_super:
            handler = APIHandler("mock_req", "mock_addr", "mock_server", site_dir=str(self.test_dir))
            handler.request_version = 'HTTP/1.1' # Required for send_header
            handler.wfile = MagicMock()
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.headers = {'Host': 'localhost:8080'}

        
        # 1. Invalid OAM serial
        data = {
            'query_type': 'oam',
            'email': 'valid@example.com',
            'oam_serial': 'abc', # Invalid
            'oam_type': 'XX',
            'oam_year': '2025'
        }
        handler._handle_add_code(data)
        # Should be 400
        handler.send_response.assert_called_with(400)
        
        # 2. Valid OAM with Malicious Code injection attempt
        handler.send_response.reset_mock()
        data = {
            'query_type': 'oam',
            'email': 'valid@example.com',
            'code': '<script>alert(1)</script>', # Malicious code
            'oam_serial': '12345',
            'oam_type': 'DV',
            'oam_year': '2025'
        }
        # Mock send_verification_email to avoid actual sending
        with patch('monitor.server.api_handler.send_verification_email') as mock_send:
            mock_send.return_value = (True, None)
            handler._handle_add_code(data)
            
        # Verify what was stored in users.json
        manager = CodeStorageManager(str(self.test_dir))
        users = manager.load_users()
        pending = list(users['pending_additions'].values())[0]
        
        # Crucial Check: Code should be reconstructed, NOT what we sent
        expected_code = "OAM-12345/DV/2025"
        self.assertEqual(pending['code'], expected_code, "OAM code reconstruction failed! Malicious input might have persisted.")
        self.assertNotEqual(pending['code'], '<script>alert(1)</script>')

    def test_api_email_validation(self):
        """Verify Email Regex"""
        with patch('http.server.BaseHTTPRequestHandler.__init__') as mock_super:
            handler = APIHandler("mock_req", "mock_addr", "mock_server", site_dir=str(self.test_dir))
            handler.request_version = 'HTTP/1.1'
            handler.wfile = MagicMock()
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
        
        data = {'code': 'TEST1234567890', 'email': 'bad_email'}
        handler._handle_add_code(data)
        handler.send_response.assert_called_with(400)

    def test_global_state_removal(self):
        """Verify CURRENT_SCHEDULER is gone"""
        import monitor.core.scheduler as sched
        self.assertFalse(hasattr(sched, 'CURRENT_SCHEDULER'), "CURRENT_SCHEDULER global variable still exists!")
        self.assertFalse(hasattr(sched, 'schedule_user_code_immediately'), "Legacy function schedule_user_code_immediately still exists!")

if __name__ == '__main__':
    # No monkey patching needed here as we do it in tests
    
    # We also need to mock load_config used in APIHandler
    patcher = patch('monitor.server.api_handler.load_env_config')
    mock_conf = patcher.start()
    mock_conf.return_value = MagicMock()
    mock_conf.return_value.smtp_host = "smtp.mock"
    
    unittest.main()
