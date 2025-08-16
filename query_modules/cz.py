import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

class VisaStatusQuerier:
    def __init__(self, driver_path=None, headless=False):
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--window-size=1200,800')
        self.driver = webdriver.Chrome(executable_path=driver_path, options=options) if driver_path else webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 15)

    def query_status(self, code):
        url = 'https://ipc.gov.cz/en/status-of-your-application/'
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                self.driver.get(url)
                # 关闭cookies弹窗（如有）
                try:
                    cookie_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, '.cookies__wrapper button, .cookies__button, [data-cookies-edit] button, [data-cookies-edit]'))
                    )
                    cookie_btn.click()
                    time.sleep(0.5)
                except Exception:
                    pass  # 没有弹窗可忽略

                # 输入查询码，确保输入框可交互
                input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                if not (input_box.is_displayed() and input_box.is_enabled()):
                    # 尝试刷新一次再查
                    self.driver.refresh()
                    time.sleep(1)
                    input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))

                input_box.clear()
                input_box.send_keys(code)

                # 提交：优先查找更宽松的submit按钮匹配
                try:
                    submit_btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                except Exception:
                    submit_btn = self.driver.find_element(By.XPATH, "//button[contains(., 'validate') or contains(., 'Validate') or contains(., 'ověřit')]")
                submit_btn.click()

                # 等待页面内alert块出现（短超时），若失败则重试
                try:
                    alert_div = WebDriverWait(self.driver, 8).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, '.alert__content'))
                    )
                    status_text = alert_div.text.strip().lower()
                    # 关键字匹配
                    if 'not found' in status_text or 'not found' in status_text:
                        return 'Not Found'
                    elif 'still being processed' in status_text or 'proceedings' in status_text:
                        return 'Proceedings'
                    elif 'was granted' in status_text or 'granted' in status_text:
                        return 'Granted'
                    elif 'was rejected' in status_text or 'rejected' in status_text or 'closed' in status_text:
                        return 'Rejected/Closed'
                    else:
                        return 'Unknown'
                except Exception:
                    # 视为一次网络/渲染问题，准备重试
                    raise
            except Exception as e:
                # 若未到达最大重试次数，短等待后重试；否则返回标准失败状态
                if attempt < max_attempts:
                    print(f"  尝试 {attempt} 失败，正在重试... ({e})")
                    time.sleep(1 + attempt)
                    continue
                else:
                    print(f"  最终尝试失败: {e}")
                    return 'Query Failed'

    def close(self):
        self.driver.quit()

def update_csv_with_status(csv_path, code_col='查询码', status_col='签证状态'):
    import os
    if not os.path.exists(csv_path):
        print(f"[错误] 未找到CSV文件: {csv_path}\n请先用 generate-codes 生成或指定正确的文件路径。\n或指定目标CSV文件（如 `--i query_codes.csv`）")
        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    if status_col not in header:
        header.append(status_col)
    code_idx = header.index(code_col)
    status_idx = header.index(status_col)
    querier = VisaStatusQuerier()
    for i, row in enumerate(rows[1:], 1):
        code = row[code_idx]
        if len(row) <= status_idx or not row[status_idx]:
            print(f"查询: {code}")
            status = querier.query_status(code)
            if len(row) <= status_idx:
                row += [''] * (status_idx - len(row) + 1)
            row[status_idx] = status
            print(f"  状态: {status}")
            # 每条查询后立即写入文件，防止中途出错丢失
            with open(csv_path, 'w', newline='', encoding='utf-8') as wf:
                writer = csv.writer(wf)
                writer.writerow(header)
                writer.writerows(rows[1:])
        else:
            print(f"已存在: {code} -> {row[status_idx]}")
    querier.close()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='批量查询签证状态（捷克）')
    parser.add_argument('--csv', default='query_codes.csv', help='csv文件路径')
    args = parser.parse_args()
    update_csv_with_status(args.csv)
