import csv
import random
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import ElementNotInteractableException, ElementClickInterceptedException, NoSuchElementException

try:
    # webdriver-manager optional fallback
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    ChromeDriverManager = None

class VisaStatusQuerier:
    def __init__(self, driver_path=None, headless=False):
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
        # performance tweaks: disable images and extensions, reduce shared memory use
        options.add_experimental_option('prefs', {"profile.managed_default_content_settings.images": 2})
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1200,800')
        # faster page load: don't wait for all resources
        try:
            options.set_capability('pageLoadStrategy', 'eager')
        except Exception:
            # older selenium may ignore
            pass
        # Prefer explicit driver_path; otherwise try webdriver-manager to install a matching driver
        if driver_path:
            service = Service(driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            if ChromeDriverManager is not None:
                driver_binary = ChromeDriverManager().install()
                service = Service(driver_binary)
                self.driver = webdriver.Chrome(service=service, options=options)
            else:
                # last resort: rely on PATH / system-installed chromedriver
                self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

    def query_status(self, code, max_attempts=3):
        """Query a single code and return a bilingual normalized status string.

        Retries on transient failures and returns a bilingual 'Query Failed / 查询失败' on permanent failure.
        """
        url = 'https://ipc.gov.cz/en/status-of-your-application/'
        for attempt in range(1, max_attempts + 1):
            try:
                self.driver.get(url)

                # Robustly dismiss cookie banners or overlays (click -> js click -> hide)
                try:
                    cookie_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '.cookies__wrapper button, .cookies__button, [data-cookies-edit] button, [data-cookies-edit]'))
                    )
                    try:
                        cookie_btn.click()
                    except (ElementNotInteractableException, ElementClickInterceptedException):
                        try:
                            self.driver.execute_script("arguments[0].click();", cookie_btn)
                        except Exception:
                            # last resort: hide known overlays
                            try:
                                self.driver.execute_script("document.querySelectorAll('.cookies__wrapper, .cookies__button, [data-cookies-edit], .cookie-consent, .gdpr-banner').forEach(e=>e.style.display='none');")
                            except Exception:
                                pass
                except Exception:
                    # best-effort hide
                    try:
                        self.driver.execute_script("document.querySelectorAll('.cookies__wrapper, .cookies__button, [data-cookies-edit], .cookie-consent, .gdpr-banner').forEach(e=>e.style.display='none');")
                    except Exception:
                        pass

                # find input and populate
                input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                if not (input_box.is_displayed() and input_box.is_enabled()):
                    self.driver.refresh()
                    time.sleep(1)
                    input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))

                input_box.clear()
                input_box.send_keys(code)

                # submit (try multiple fallbacks)
                submit_btn = None
                try:
                    submit_btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                except Exception:
                    try:
                        submit_btn = self.driver.find_element(By.XPATH, "//button[contains(., 'validate') or contains(., 'Validate') or contains(., 'ověřit')]")
                    except Exception:
                        submit_btn = None

                if submit_btn is not None:
                    try:
                        submit_btn.click()
                    except (ElementNotInteractableException, ElementClickInterceptedException):
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
                            time.sleep(0.2)
                            submit_btn.click()
                        except Exception:
                            try:
                                self.driver.execute_script("arguments[0].click();", submit_btn)
                            except Exception:
                                pass

                # wait for result alert
                try:
                    alert_div = WebDriverWait(self.driver, 8).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, '.alert__content'))
                    )
                    status_text = alert_div.text.strip().lower()
                    if 'not found' in status_text:
                        return 'Not Found / 未找到'
                    if 'still being processed' in status_text or 'proceedings' in status_text:
                        return 'Proceedings / 审理中'
                    if 'was granted' in status_text or 'granted' in status_text:
                        return 'Granted / 已通过'
                    if 'was rejected' in status_text or 'rejected' in status_text or 'closed' in status_text:
                        return 'Rejected/Closed / 被拒绝/已关闭'
                    return 'Unknown / 未知'
                except Exception:
                    # treat as transient and retry
                    raise
            except Exception as e:
                if attempt < max_attempts:
                    print(f"  Attempt {attempt} failed, retrying... ({e}) / 尝试 {attempt} 失败，正在重试... ({e})")
                    time.sleep(1 + attempt + random.uniform(0, 0.5))
                    continue
                else:
                    print(f"  Final attempt failed: {e} / 最终尝试失败: {e}")
                    return 'Query Failed / 查询失败'

    def close(self):
        self.driver.quit()

def update_csv_with_status(csv_path, code_col='查询码', status_col='签证状态', driver_path=None, headless=False, retries=None, log_dir='logs', per_query_delay=0.5, jitter=0.5):
    import os
    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found: {csv_path}\nPlease generate it with generate-codes or provide the correct path (e.g. --i query_codes.csv). / [错误] 未找到CSV文件: {csv_path}\n请先用 generate-codes 生成或指定正确的文件路径（例如 --i query_codes.csv）。")
        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    if status_col not in header:
        header.append(status_col)
    code_idx = header.index(code_col)
    status_idx = header.index(status_col)
    querier = VisaStatusQuerier(driver_path=driver_path, headless=headless)
    for i, row in enumerate(rows[1:], 1):
        code = row[code_idx]
        if len(row) <= status_idx or not row[status_idx]:
            print(f"Querying: {code} / 查询: {code}")
            try:
                # Use provided retries if set, otherwise default inside query_status
                max_attempts = retries if (retries is not None and retries > 0) else 3
                status = querier.query_status(code, max_attempts=max_attempts)
            except Exception as e:
                status = 'Query Failed'
                err_msg = str(e)
            else:
                err_msg = ''
            if len(row) <= status_idx:
                row += [''] * (status_idx - len(row) + 1)
            row[status_idx] = status
            print(f"  Status: {status} / 状态: {status}")
            # 每条查询后立即写入文件，防止中途出错丢失
            with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
                writer = csv.writer(wf)
                writer.writerow(header)
                writer.writerows(rows[1:])
            # 如果查询失败，写入 logs/fails 当日失败文件，便于后续重试
            # treat any variant containing 'query failed' (case-insensitive) as failure
            if isinstance(status, str) and 'query failed' in status.lower():
                import os
                import datetime
                fails_dir = os.path.join(os.getcwd(), log_dir, 'fails')
                os.makedirs(fails_dir, exist_ok=True)
                fail_file = os.path.join(fails_dir, f"{datetime.date.today().isoformat()}_fails.csv")
                write_header = not os.path.exists(fail_file)
                with open(fail_file, 'a', newline='', encoding='utf-8') as ff:
                    fw = csv.writer(ff)
                    if write_header:
                        fw.writerow(['日期', '查询码', '状态', '备注'])
                    fw.writerow([datetime.date.today().isoformat(), code, status, err_msg])
                # pacing: small delay + jitter to avoid hammering the remote server
                try:
                    delay = float(per_query_delay) if per_query_delay is not None else 0.5
                    j = float(jitter) if jitter is not None else 0.5
                    sleep_for = max(0.0, delay + random.uniform(0, j))
                    time.sleep(sleep_for)
                except Exception:
                    pass
        else:
            print(f"Skipped (exists): {code} -> {row[status_idx]} / 已存在: {code} -> {row[status_idx]}")
    querier.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Czech bulk visa-status checker / 捷克批量查询签证状态')
    parser.add_argument('--csv', default='query_codes.csv', help='CSV file path / CSV 文件路径')
    parser.add_argument('--driver-path', default=None, help='ChromeDriver executable path (optional) / ChromeDriver 可执行文件路径（可选）')
    parser.add_argument('--headless', action='store_true', help='Run browser headless / 以无头模式运行浏览器')
    parser.add_argument('--retries', type=int, default=3, help='Retries per query (default 3) / 每条查询的重试次数（默认 3）')
    parser.add_argument('--log-dir', default='logs', help='Logs directory (default: logs) / 日志目录（默认: logs）')
    parser.add_argument('--delay', type=float, default=0.5, help='Base per-query delay seconds (helps avoid rate-limits) / 每条查询基础延迟（秒），可避免短时间内高并发')
    parser.add_argument('--jitter', type=float, default=0.5, help='Max jitter seconds to add to delay / 随机抖动最大值（秒），用于在基础延迟上增加随机性')
    args = parser.parse_args()
    update_csv_with_status(args.csv, driver_path=args.driver_path, headless=args.headless, retries=args.retries, log_dir=args.log_dir, per_query_delay=args.delay, jitter=args.jitter)
