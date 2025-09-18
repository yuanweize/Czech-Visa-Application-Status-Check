#!/usr/bin/env python3
"""
测试日志修复：模拟浏览器请求以验证日志减少效果
"""

import requests
import time

def test_requests():
    """测试各种类型的请求"""
    base_url = "http://localhost:8080"
    
    # 测试请求列表
    test_requests = [
        "/favicon.ico",                                      # 常见浏览器请求
        "/.well-known/appspecific/com.chrome.devtools.json", # Chrome开发工具
        "/robots.txt",                                       # 爬虫文件
        "/manifest.json",                                    # PWA清单
        "/nonexistent.html",                                 # 404文件
        "/api/public-status",                                # 正常API
        "/status.json",                                      # 敏感文件
        "/.env",                                            # 敏感文件
    ]
    
    print("🧪 Testing log noise reduction...")
    print("=" * 50)
    
    for endpoint in test_requests:
        try:
            url = base_url + endpoint
            print(f"Testing: {endpoint:50}", end="")
            
            response = requests.get(url, timeout=5)
            
            if endpoint == "/api/public-status":
                print(f" ✅ {response.status_code} (Expected: 200)")
            elif endpoint in ["/status.json", "/.env"]:
                print(f" 🔒 {response.status_code} (Expected: 302 redirect)")
            elif endpoint.startswith("/.well-known/"):
                print(f" 🔇 {response.status_code} (Should be silent)")
            else:
                print(f" 📝 {response.status_code} (Minimal logging)")
                
        except requests.exceptions.RequestException as e:
            print(f" ❌ Error: {e}")
        
        time.sleep(0.5)  # 避免触发频率限制
    
    print("\n" + "=" * 50)
    print("🔍 Check the server logs to verify noise reduction!")
    print("Expected behaviors:")
    print("  • .well-known/ requests: No SECURITY logs")
    print("  • favicon.ico, robots.txt: No REDIRECT logs")  
    print("  • Chrome devtools requests: Silent handling")
    print("  • Only genuine errors should be logged")

if __name__ == "__main__":
    test_requests()