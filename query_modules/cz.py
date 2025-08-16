import csv
import random
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import ElementNotInteractableException, ElementClickInterceptedException, NoSuchElementException, TimeoutException, WebDriverException, NoSuchWindowException

try:
    # webdriver-manager optional fallback
    from webdriver_manager.chrome import ChromeDriverManager
except Exception:
    ChromeDriverManager = None

class VisaStatusQuerier:
    def __init__(self, driver_path=None, headless=False):
        # keep config for possible re-creation
        self._driver_path = driver_path
        self._headless = headless
        options = webdriver.ChromeOptions()
        if self._headless:
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
        # create the driver using a helper so we can recreate if needed
        self._create_driver(driver_path, options)

    def _create_driver(self, driver_path, options):
        """Create a Chrome WebDriver and attach a WebDriverWait helper."""
        # close existing if present
        try:
            if hasattr(self, 'driver') and self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        except Exception:
            pass

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

    def _ensure_driver(self):
        """Ensure driver is alive; recreate if remote/closed unexpectedly."""
        try:
            # a lightweight call to detect dead driver
            self.driver.execute_script('return 1')
        except Exception:
            # attempt to recreate
            opts = webdriver.ChromeOptions()
            if self._headless:
                opts.add_argument('--headless')
                opts.add_argument('--disable-gpu')
            opts.add_experimental_option('prefs', {"profile.managed_default_content_settings.images": 2})
            opts.add_argument('--disable-extensions')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--window-size=1200,800')
            try:
                opts.set_capability('pageLoadStrategy', 'eager')
            except Exception:
                pass
            self._create_driver(self._driver_path, opts)

    def _dismiss_overlays(self, timeout=8):
        """Attempt to close cookie banners and modal windows using targeted selectors and JS clicks.

        Returns True if overlays appear cleared, False otherwise.
        """
        try:
            # quick targeted attempts for known buttons (Refuse all / close)
            js_click_by_text = r'''
            (function(){
              var texts = ['refuse all','refuse','decline','do not accept','odmítnout','odmítnout vše','nepřijmout','zamítnout','reject','close','zavřít'];
              function norm(s){return (s||'').trim().toLowerCase();}
              function tryClick(el){ try{ el.click(); return true;}catch(e){ try{ var ev=new MouseEvent('click',{bubbles:true,cancelable:true,view:window}); el.dispatchEvent(ev); return true;}catch(e2){ try{ el.remove(); return true;}catch(e3){} } return false; }
              var sels = ['.cookies__wrapper button.button__outline','.cookies__wrapper button','.cookies__container button.button__outline','button.button__outline','button.button__close','.modal__window button.button__close','button.button'];
              sels.forEach(function(sel){ document.querySelectorAll(sel).forEach(function(b){ try{ var t=norm(b.innerText||b.value||''); for(var i=0;i<texts.length;i++){ if(t.indexOf(texts[i])>=0){ tryClick(b); break; } } }catch(e){} }); });
              var hide = ['.cookies__wrapper','.cookie-consent','.gdpr-banner','[data-cookie]','[data-cookies-edit]','.modal__window','.modal-backdrop'];
              hide.forEach(function(s){ document.querySelectorAll(s).forEach(function(w){ try{ w.style.display='none'; w.style.pointerEvents='none'; w.style.zIndex='-9999'; }catch(e){} }); });
            })();
            '''

            # First, do a fast one-shot JS click/hide and check immediately.
            try:
                self.driver.execute_script(js_click_by_text)
            except Exception:
                pass

            checks = ['.cookies__wrapper', '.cookie-consent', '.gdpr-banner', '[data-cookie]', '[data-cookies-edit]', '.modal__window', '.modal-backdrop']
            # quick check: if no overlay-like element is visible, return immediately
            try:
                still_quick = False
                for sel in checks:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    except Exception:
                        elems = []
                    for el in elems:
                        try:
                            if el.is_displayed():
                                still_quick = True
                                break
                        except Exception:
                            still_quick = True
                            break
                    if still_quick:
                        break
            except Exception:
                # fall through to the slower loop below if the quick check fails
                pass

            end = time.time() + timeout
            while time.time() < end:
                try:
                    # run targeted JS click/hide again inside the slower loop
                    self.driver.execute_script(js_click_by_text)
                except Exception:
                    pass
                # also try Selenium-level clicks for visible refuse/close buttons
                try:
                    for sel in ('.cookies__wrapper button.button__outline', 'button.button__outline', '.modal__window button.button__close', 'button.button__close'):
                        try:
                            els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        except Exception:
                            els = []
                        for el in els:
                            try:
                                if el.is_displayed() and el.is_enabled():
                                    try:
                                        # use JS dispatch first
                                        self.driver.execute_script("var ev = new MouseEvent('click', {bubbles:true,cancelable:true,view:window}); arguments[0].dispatchEvent(ev);", el)
                                    except Exception:
                                        try:
                                            el.click()
                                        except Exception:
                                            try:
                                                self.driver.execute_script("arguments[0].click();", el)
                                            except Exception:
                                                pass
                            except Exception:
                                pass
                except Exception:
                    pass

                # check if wrappers still present and visible
                still = False
                try:
                    for sel in checks:
                        try:
                            elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        except Exception:
                            elems = []
                        for el in elems:
                            try:
                                if el.is_displayed():
                                    still = True
                                    break
                            except Exception:
                                still = True
                                break
                        if still:
                            break
                except Exception:
                    still = True

                if not still:
                    return True
                # shorter sleep to speed up loop responsiveness
                time.sleep(0.15)
        except Exception:
            pass
        # do not save debug here; caller will decide when to persist a dump
        return False

    def _save_overlay_debug(self, tag='debug'):
        """Save current page HTML to logs/fails for later diagnosis; tag is short descriptor."""
        try:
            import os, datetime
            fails_dir = os.path.join(os.getcwd(), 'logs', 'fails')
            os.makedirs(fails_dir, exist_ok=True)
            fn = os.path.join(fails_dir, f"overlay_debug_{tag}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
            try:
                src = self.driver.page_source
                with open(fn, 'w', encoding='utf-8') as fh:
                    fh.write(src)
            except Exception:
                pass
        except Exception:
            pass

    def query_status(self, code, max_attempts=3):
        """Query a single code and return a bilingual normalized status string.

        Retries on transient failures and returns a bilingual 'Query Failed / 查询失败' on permanent failure.
        """
        url = 'https://ipc.gov.cz/en/status-of-your-application/'
        for attempt in range(1, max_attempts + 1):
            try:
                # ensure driver is healthy before navigation
                try:
                    self._ensure_driver()
                except Exception:
                    pass
                # navigate; wrap to handle first-run transient failures
                try:
                    self.driver.get(url)
                except Exception:
                    # short pause and recreate then retry navigation once
                    time.sleep(0.5)
                    try:
                        self._ensure_driver()
                        self.driver.get(url)
                    except Exception:
                        # re-raise to be handled by outer retry logic
                        raise

                # Fast-path: try to populate and submit immediately when the input is available.
                fast_attempted = False
                try:
                    try:
                        short_wait = WebDriverWait(self.driver, 4)
                        input_box = short_wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                    except Exception:
                        input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))

                    # try fast JS-set and immediate submit
                    try:
                        # JS set by name and dispatch events
                        set_js = (
                            "(function(name, val){"
                            "  try { var el = document.getElementsByName(name)[0]; if(!el) return false; el.focus(); el.value = val; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); return (el.value === val); } catch(e){ return false; }"
                            "})(arguments[0], arguments[1]);"
                        )
                        ok = bool(self.driver.execute_script(set_js, 'visaApplicationNumber', code))
                    except Exception:
                        ok = False

                    submit_btn = None
                    try:
                        submit_btn = self.driver.find_element(By.XPATH, "//button[@type='submit']")
                    except Exception:
                        try:
                            submit_btn = self.driver.find_element(By.XPATH, "//button[contains(., 'validate') or contains(., 'Validate') or contains(., 'ověřit')]")
                        except Exception:
                            submit_btn = None

                    if ok and submit_btn is not None:
                        try:
                            # fast JS click attempt
                            self.driver.execute_script("arguments[0].click();", submit_btn)
                            fast_attempted = True
                        except Exception:
                            fast_attempted = False
                    # if fast path succeeded we proceed to wait for results below
                except (NoSuchWindowException, WebDriverException):
                    # driver window closed or session lost: recreate and reload page, then retry once
                    try:
                        print('  Detected closed window/session; recreating browser and retrying... / 检测到浏览器窗口关闭/会话丢失，正在重建并重试...')
                        self._ensure_driver()
                        try:
                            self.driver.get(url)
                        except Exception:
                            time.sleep(0.5)
                            self.driver.get(url)
                        # re-dismiss overlays after recreation
                        try:
                            self._dismiss_overlays(timeout=6)
                        except Exception:
                            pass
                        input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                    except Exception:
                        # let outer retry handle it
                        raise

                # aggressive overlay dismissal: immediate hide + quick clicks without waiting
                try:
                    # immediate aggressive removal of all common overlay types
                    self.driver.execute_script("""
                        var overlays = '.cookies__wrapper, .cookie-consent, .gdpr-banner, .modal__window, .modal-backdrop, [data-cookie], [data-cookies-edit]';
                        document.querySelectorAll(overlays).forEach(e => {
                            e.style.display = 'none'; 
                            e.style.visibility = 'hidden'; 
                            e.style.pointerEvents = 'none';
                            e.style.zIndex = '-9999';
                            try { e.remove(); } catch(ex) {}
                        });
                        // also click refuse/close buttons instantly
                        document.querySelectorAll('button.button__outline, button.button__close').forEach(b => {
                            try { b.click(); } catch(e) {}
                        });
                    """)
                except Exception:
                    pass

                # find input immediately - don't wait for overlays to fully clear
                try:
                    # try immediate find first
                    try:
                        input_box = self.driver.find_element(By.NAME, 'visaApplicationNumber')
                    except Exception:
                        # minimal wait if not found immediately
                        quick_wait = WebDriverWait(self.driver, 2)
                        input_box = quick_wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                except (NoSuchWindowException, WebDriverException):
                    # driver window closed or session lost: recreate and reload page, then retry once
                    try:
                        print('  Detected closed window/session; recreating browser and retrying... / 检测到浏览器窗口关闭/会话丢失，正在重建并重试...')
                        self._ensure_driver()
                        try:
                            self.driver.get(url)
                        except Exception:
                            time.sleep(0.5)
                            self.driver.get(url)
                        # re-dismiss overlays after recreation
                        try:
                            self.driver.execute_script("document.querySelectorAll('.cookies__wrapper, .modal__window').forEach(e=>e.style.display='none');")
                        except Exception:
                            pass
                        input_box = self.wait.until(EC.presence_of_element_located((By.NAME, 'visaApplicationNumber')))
                    except Exception:
                        # let outer retry handle it
                        raise

                # fast input: prefer JS setter by name (safer across contexts) and verify it; fallback to send_keys
                ok = False
                for attempt in range(3):  # try up to 3 times to ensure value sticks
                    try:
                        set_js = (
                            "(function(name, val){"
                            "  try {"
                            "    var el = document.getElementsByName(name)[0];"
                            "    if(!el){ return false; }"
                            "    el.focus();"
                            "    el.value = val;"
                            "    el.dispatchEvent(new Event('input', {bubbles:true}));"
                            "    el.dispatchEvent(new Event('change', {bubbles:true}));"
                            "    return (el.value === val);"
                            "  } catch(e) { return false; }"
                            "})(arguments[0], arguments[1]);"
                        )
                        ok = bool(self.driver.execute_script(set_js, 'visaApplicationNumber', code))
                        if ok:
                            # verify the value is still there after a short delay (in case page scripts clear it)
                            time.sleep(0.1)
                            actual = self.driver.execute_script("var el=document.getElementsByName('visaApplicationNumber')[0]; return el ? (el.value||'') : '';")
                            if actual and str(actual).strip() == code:
                                break
                            else:
                                ok = False  # value was cleared, try again
                    except Exception:
                        ok = False
                    
                    if not ok and attempt < 2:
                        time.sleep(0.2)  # brief pause before retry

                if not ok:
                    # try to focus/click then send keys as a reliable fallback
                    for attempt in range(2):
                        try:
                            try:
                                input_box.click()
                            except Exception:
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView(true); arguments[0].focus();", input_box)
                                except Exception:
                                    pass
                            input_box.clear()
                            # small pause to ensure focus before typing
                            time.sleep(0.1)
                            input_box.send_keys(code)
                            
                            # verify send_keys worked and value persists
                            time.sleep(0.1)
                            actual = self.driver.execute_script("var el=document.getElementsByName('visaApplicationNumber')[0]; return el ? (el.value||'') : '';")
                            if actual and str(actual).strip() == code:
                                ok = True
                                break
                        except Exception:
                            pass
                        
                        if attempt < 1:
                            time.sleep(0.3)  # longer pause before final retry

                # verify that the input now contains the code; if not, attempt a final JS read to capture value for diagnostics
                try:
                    actual = self.driver.execute_script("var el=document.getElementsByName('visaApplicationNumber')[0]; return el ? (el.value||'') : '';")
                    if not actual or str(actual).strip() != code:
                        # final attempt: re-set the value one more time before submitting
                        try:
                            self.driver.execute_script("var el=document.getElementsByName('visaApplicationNumber')[0]; if(el){ el.value=arguments[0]; el.dispatchEvent(new Event('input', {bubbles:true})); }", code)
                            time.sleep(0.05)
                            actual = self.driver.execute_script("var el=document.getElementsByName('visaApplicationNumber')[0]; return el ? (el.value||'') : '';")
                        except Exception:
                            pass
                        
                        if not actual or str(actual).strip() == '':
                            # nothing; will likely cause a Not Found result if submit proceeds — raise to trigger retry
                            raise Exception('Input population failed - value keeps getting cleared')
                except Exception:
                    # ensure outer logic treats this as a transient failure and retries
                    raise

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
                            time.sleep(0.1)
                            submit_btn.click()
                        except Exception:
                            try:
                                self.driver.execute_script("arguments[0].click();", submit_btn)
                            except Exception:
                                pass

                # wait for result alert or other visible result text using a JS poll across multiple selectors
                status_text = ''
                try:
                    end = time.time() + 6  # reduced from 8 to 6 seconds
                    # include role/aria selectors which many sites use for live alerts
                    selectors = ['.alert__content', '.alert', '.result', '.status', '.ipc-result', '.application-status', '[role=alert]', '[aria-live]']
                    while time.time() < end:
                        try:
                            found_text = ''
                            # First: try Selenium to read text from matching elements (accept text even if not displayed)
                            for s in selectors:
                                try:
                                    els = self.driver.find_elements(By.CSS_SELECTOR, s)
                                except Exception:
                                    els = []
                                for el in els:
                                    try:
                                        txt = (el.text or '').strip()
                                        if not txt:
                                            # fallback to innerText/textContent via JS for elements that may not report visible
                                            try:
                                                txt = self.driver.execute_script("return (arguments[0].innerText || arguments[0].textContent || '').trim();", el) or ''
                                            except Exception:
                                                txt = ''
                                        if txt:
                                            found_text = txt
                                            break
                                    except Exception:
                                        continue
                                if found_text:
                                    break
                            if found_text:
                                status_text = found_text.strip().lower()
                                break

                            # Second: JS-wide scan over selectors to find any non-empty innerText/textContent regardless of visibility
                            try:
                                js_scan = "var sels=arguments[0]; for(var i=0;i<sels.length;i++){var nodes=document.querySelectorAll(sels[i]); for(var j=0;j<nodes.length;j++){ try{ var t=(nodes[j].innerText||nodes[j].textContent||'').trim(); if(t) return t;}catch(e){} } } return '';"
                                txt = self.driver.execute_script(js_scan, selectors)
                                if txt and str(txt).strip():
                                    status_text = str(txt).strip().lower()
                                    break
                            except Exception:
                                pass
                        except Exception:
                            pass
                        time.sleep(0.2)  # reduced from 0.35 to 0.2 for faster polling
                    if not status_text:
                        raise TimeoutException('No visible result text found')
                    if 'not found' in status_text:
                        return 'Not Found / 未找到'
                    if 'still' in status_text and 'proceedings' in status_text:
                        return 'Proceedings / 审理中'
                    if 'for information on how to proceed' in status_text or 'granted' in status_text or 'approved' in status_text:
                        return 'Granted / 已通过'
                    if 'proceedings' in status_text:
                        return 'Rejected/Closed / 被拒绝/已关闭'
                    return 'Unknown Status / 未知状态'+f"(status_text/状态文本: {status_text})"
                except TimeoutException:
                    # no result visible in time — treat as transient and retry
                    raise
                except Exception:
                    # treat other exceptions as transient
                    raise
            except Exception as e:
                if attempt < max_attempts:
                    print(f"  Attempt/ 尝试  {attempt} failed, retrying.../失败，正在重试...({e})")
                    time.sleep(1 + attempt + random.uniform(0, 0.5))
                    continue
                else:
                    print(f"  Final attempt failed/最终尝试失败: {e}")
                    return 'Query Failed / 查询失败'+f"(status_text/状态文本: {status_text})"


    def close(self):
        self.driver.quit()

def update_csv_with_status(csv_path, code_col='查询码/Code', status_col='签证状态/Status', driver_path=None, headless=False, retries=None, log_dir='logs', per_query_delay=0.5, jitter=0.5):
    import os
    if not os.path.exists(csv_path):
        print(f"[Error] CSV not found / [错误] 未找到CSV文件: {csv_path}\nPlease generate it with generate-codes or provide the correct path (e.g. --i query_codes.csv).\n请先用 generate-codes 生成或指定正确的文件路径（例如 --i query_codes.csv）。")

        return
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    # normalize header matching: find indices by exact or case-insensitive match
    def find_col(name):
        if name in header:
            return header.index(name)
        nl = name.lower()
        for i, h in enumerate(header):
            if h and h.lower() == nl:
                return i
        # try partial matches
        for i, h in enumerate(header):
            if h and nl in h.lower():
                return i
        return None

    code_idx = find_col(code_col)
    if code_idx is None:
        raise ValueError(f'Could not find code column {code_col} in CSV header: {header}')
    status_idx = find_col(status_col)
    if status_idx is None:
        # add the status column at the end
        header.append(status_col)
        status_idx = len(header) - 1
    querier = VisaStatusQuerier(driver_path=driver_path, headless=headless)
    for i, row in enumerate(rows[1:], 1):
        # ensure row length matches header
        while len(row) < len(header):
            row.append('')
        code = row[code_idx]
        # if status column already has a non-empty value, skip
        if row[status_idx] and str(row[status_idx]).strip():
            print(f"Skipped(exists)/跳过(已存在):{code} -> {row[status_idx]}")
            continue

        # perform the query for empty status
        print(f"Querying/查询： {code}")
        try:
            # Use provided retries if set, otherwise default inside query_status
            max_attempts = retries if (retries is not None and retries > 0) else 3
            status = querier.query_status(code, max_attempts=max_attempts)
            err_msg = ''
        except Exception as e:
            status = 'Query Failed / 查询失败'
            err_msg = str(e)

        # ensure row long enough then write status
        row[status_idx] = status
        print(f"  Status/状态: {status}")
        # save overlay debug only for Unknown or Query Failed to aid later debugging
        try:
            if isinstance(status, str) and (status.lower().startswith('unknown') or 'query failed' in status.lower()):
                try:
                    querier._save_overlay_debug(tag=status.split()[0])
                except Exception:
                    pass
        except Exception:
            pass

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
                    fw.writerow(['日期/Date', '查询码/Code', '状态/Status', '备注/Remark'])
                fw.writerow([datetime.date.today().isoformat(), code, status, err_msg])

            # pacing: small delay + jitter to avoid hammering the remote server
            try:
                delay = float(per_query_delay) if per_query_delay is not None else 0.5
                j = float(jitter) if jitter is not None else 0.5
                sleep_for = max(0.0, delay + random.uniform(0, j))
                time.sleep(sleep_for)
            except Exception:
                pass
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
