async function loadData() {
  try {
    // Use safe public API endpoint
    const res = await fetch('/api/public-status?_=' + Date.now());
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('Public API failed:', e);
    return { generated_at: '', items: {} };
  }
}

function codeKeyBigInt(code) {
  try {
    const s = String(code || '');
    const digits = (s.match(/\d+/g) || []).join('');
    if (!digits) return null;
    return BigInt(digits);
  } catch (_) {
    return null;
  }
}

let sortState = { key: 'code', dir: 'asc' }; // default: code asc
let countdownInterval = null;
let refreshInProgress = false;

function statusClass(s) {
  const t = (s || '').toLowerCase();
  if (t.includes('granted') || t.includes('已通过')) return 'status-granted';
  if (t.includes('proceedings') || t.includes('审理中')) return 'status-proc';
  if (t.includes('not found') || t.includes('未找到')) return 'status-notfound';
  return 'status-unknown';
}

function startCountdown() {
  let seconds = 60;
  const countdownEl = document.getElementById('countdown');

  if (countdownInterval) clearInterval(countdownInterval);

  countdownInterval = setInterval(() => {
    seconds--;
    if (seconds <= 0) {
      countdownEl.textContent = 'Refreshing...';
      clearInterval(countdownInterval);
    } else {
      countdownEl.textContent = `Next refresh in ${seconds}s`;
    }
  }, 1000);

  countdownEl.textContent = `Next refresh in ${seconds}s`;
}

function showLoading() {
  document.getElementById('loading-overlay').style.display = 'flex';
  const btn = document.getElementById('refresh');
  btn.disabled = true;
  btn.querySelector('.btn-text').style.display = 'none';
  btn.querySelector('.spinner').style.display = 'inline';
  refreshInProgress = true;
}

function hideLoading() {
  document.getElementById('loading-overlay').style.display = 'none';
  const btn = document.getElementById('refresh');
  btn.disabled = false;
  btn.querySelector('.btn-text').style.display = 'inline';
  btn.querySelector('.spinner').style.display = 'none';
  refreshInProgress = false;
}

function render(data) {
  window.lastData = data; // Store for filter operations
  const gaEl = document.getElementById('generatedAt');
  if (gaEl) {
    let genText = '';
    if (data.generated_at) {
      const d = new Date(data.generated_at);
      if (!isNaN(d.getTime())) {
        genText = d.toLocaleString();
        gaEl.title = `Last updated: ${genText}`;
      } else {
        // Fallback to raw string if not a valid date
        genText = data.generated_at;
        gaEl.title = `Last updated: ${genText}`;
      }
    } else {
      gaEl.title = '';
    }
    gaEl.textContent = 'Last updated: ' + genText;
  }
  const tb = document.querySelector('#tbl tbody');
  tb.innerHTML = '';
  const entries = Object.values(data.items || {}).sort((a, b) => {
    if (sortState.key === 'status') {
      const as = String(a.status || '').toLowerCase();
      const bs = String(b.status || '').toLowerCase();
      let cmp = 0;
      if (as < bs) cmp = -1; else if (as > bs) cmp = 1; else cmp = 0;
      if (cmp !== 0) return sortState.dir === 'asc' ? cmp : -cmp;
      // tie-break by code numeric value
      const ak = codeKeyBigInt(a.code);
      const bk = codeKeyBigInt(b.code);
      if (ak !== null && bk !== null) {
        if (ak < bk) return sortState.dir === 'asc' ? -1 : 1;
        if (ak > bk) return sortState.dir === 'asc' ? 1 : -1;
      }
      const slex = (String(a.code || '')).localeCompare(String(b.code || ''));
      return sortState.dir === 'asc' ? slex : -slex;
    } else {
      // code sort
      const ak = codeKeyBigInt(a.code);
      const bk = codeKeyBigInt(b.code);
      if (ak !== null && bk !== null) {
        if (ak < bk) return sortState.dir === 'asc' ? -1 : 1;
        if (ak > bk) return sortState.dir === 'asc' ? 1 : -1;
        const slex = (String(a.code || '')).localeCompare(String(b.code || ''));
        return sortState.dir === 'asc' ? slex : -slex;
      }
      const slex = (String(a.code || '')).localeCompare(String(b.code || ''));
      return sortState.dir === 'asc' ? slex : -slex;
    }
  });
  const q = (document.getElementById('filter').value || '').toLowerCase();
  for (const it of entries) {
    const hay = (it.code + ' ' + (it.status || '')).toLowerCase();
    if (q && !hay.includes(q)) continue;
    const tr = document.createElement('tr');

    // Code column with note support
    const tdCode = document.createElement('td');

    // Create code container with two lines (similar to time display)
    const codeContainer = document.createElement('div');
    codeContainer.className = 'code-container';

    // Main code line
    const codeDiv = document.createElement('div');
    codeDiv.className = 'code-text';
    codeDiv.textContent = it.code || '';
    if (it.next_check) {
      codeDiv.title = `Next check: ${new Date(it.next_check).toLocaleString()}`;
    }

    // Note line (if exists)
    if (it.note && it.note.trim()) {
      const noteDiv = document.createElement('div');
      noteDiv.className = 'code-note';
      noteDiv.textContent = it.note.trim();
      codeContainer.appendChild(codeDiv);
      codeContainer.appendChild(noteDiv);
    } else {
      // No note, just add the code text directly
      codeContainer.appendChild(codeDiv);
    }

    tdCode.appendChild(codeContainer);
    const tdStatus = document.createElement('td');
    const span = document.createElement('span');
    span.className = 'status-tag ' + statusClass(it.status);
    span.textContent = it.status || '';
    tdStatus.appendChild(span);

    // Enhanced time display with Last Checked and Next Check countdown
    const tdTime = document.createElement('td');
    tdTime.className = 'time-cell';

    // Create time container with two lines
    const timeContainer = document.createElement('div');
    timeContainer.className = 'time-container';

    // Last Checked line
    const lastCheckedDiv = document.createElement('div');
    lastCheckedDiv.className = 'last-checked';
    if (it.last_checked) {
      const lastCheckedTime = new Date(it.last_checked);
      lastCheckedDiv.textContent = `Last: ${lastCheckedTime.toLocaleString()}`;
      lastCheckedDiv.title = `Last checked: ${lastCheckedTime.toLocaleString()}`;
    } else {
      lastCheckedDiv.textContent = 'Last: Never';
    }

    // Next Check countdown line
    const nextCheckDiv = document.createElement('div');
    nextCheckDiv.className = 'next-check';
    if (it.next_check) {
      nextCheckDiv.setAttribute('data-next-check', it.next_check);
      nextCheckDiv.textContent = 'Next: Calculating...';
    } else {
      nextCheckDiv.textContent = 'Next: Not scheduled';
      nextCheckDiv.classList.add('muted');
    }

    timeContainer.appendChild(lastCheckedDiv);
    timeContainer.appendChild(nextCheckDiv);
    tdTime.appendChild(timeContainer);

    const tdLCh = document.createElement('td');
    tdLCh.className = 'last-changed-cell';
    if (it.last_changed) {
      const lastChangedTime = new Date(it.last_changed);
      tdLCh.textContent = lastChangedTime.toLocaleString();
      tdLCh.title = `Last changed: ${lastChangedTime.toLocaleString()}`;
    } else {
      tdLCh.textContent = 'Never';
    }
    tr.appendChild(tdCode); tr.appendChild(tdStatus); tr.appendChild(tdTime); tr.appendChild(tdLCh);
    tb.appendChild(tr);
  }

  // Start countdown timers for each next_check
  startNextCheckCountdowns();
}

// Global variable to track countdown intervals
let nextCheckIntervals = [];

function startNextCheckCountdowns() {
  // Clear existing intervals
  nextCheckIntervals.forEach(interval => clearInterval(interval));
  nextCheckIntervals = [];

  // Find all next-check elements
  const nextCheckElements = document.querySelectorAll('.next-check[data-next-check]');

  nextCheckElements.forEach(element => {
    const nextCheckTime = new Date(element.getAttribute('data-next-check'));

    function updateCountdown() {
      const now = new Date();
      const timeRemaining = nextCheckTime - now;

      if (timeRemaining <= 0) {
        element.textContent = 'Next: Overdue';
        element.className = 'next-check overdue';
        return;
      }

      const minutes = Math.floor(timeRemaining / (1000 * 60));
      const hours = Math.floor(minutes / 60);
      const days = Math.floor(hours / 24);

      let countdownText = 'Next: ';
      if (days > 0) {
        countdownText += `${days}d ${hours % 24}h`;
      } else if (hours > 0) {
        countdownText += `${hours}h ${minutes % 60}m`;
      } else {
        countdownText += `${minutes}m`;
      }

      element.textContent = countdownText;
      element.title = `Next check: ${nextCheckTime.toLocaleString()}`;
    }

    // Update immediately
    updateCountdown();

    // Update every minute
    const interval = setInterval(updateCountdown, 60000);
    nextCheckIntervals.push(interval);
  });
}

async function refresh() {
  if (refreshInProgress) return;

  showLoading();
  const data = await loadData();
  render(data);
  hideLoading();
  startCountdown();
}

document.getElementById('refresh').addEventListener('click', refresh);
const filter = document.getElementById('filter');
filter.addEventListener('input', () => {
  if (!refreshInProgress) render(window.lastData || { items: {} });
});

// Clickable header sorting
const thCode = document.getElementById('th-code');
const thStatus = document.getElementById('th-status');
function setHeaderIndicators() {
  const arrowCode = document.getElementById('arrow-code');
  const arrowStatus = document.getElementById('arrow-status');

  if (sortState.key === 'code') {
    arrowCode.textContent = sortState.dir === 'asc' ? '↓' : '↑';
    arrowStatus.textContent = '';
  } else {
    arrowCode.textContent = '';
    arrowStatus.textContent = sortState.dir === 'asc' ? '↑' : '↓';
  }
}
function toggleSort(key) {
  if (sortState.key === key) {
    sortState.dir = (sortState.dir === 'asc') ? 'desc' : 'asc';
  } else {
    sortState.key = key;
    sortState.dir = 'asc';
  }
  setHeaderIndicators();
  if (!refreshInProgress) render(window.lastData || { items: {} });
}
if (thCode) thCode.addEventListener('click', () => toggleSort('code'));
if (thStatus) thStatus.addEventListener('click', () => toggleSort('status'));

// initialize indicators for default (code asc)
setHeaderIndicators();

refresh();
setInterval(refresh, 60000);

// 验证码生成
function generateCaptcha(questionId, answerId) {
  const num1 = Math.floor(Math.random() * 10) + 1;
  const num2 = Math.floor(Math.random() * 10) + 1;
  const answer = num1 + num2;

  document.getElementById(questionId).textContent = `Please calculate: ${num1} + ${num2} = ?`;
  document.getElementById(questionId).dataset.answer = answer;
}

// 模态框控制
function openModal(modalId) {
  document.getElementById(modalId).style.display = 'block';
  if (modalId === 'modal-add') {
    generateCaptcha('captcha-question', 'captcha-answer');
    toggleQueryTypeFields(); // Ensure fields are correct for the default selected type
  } else if (modalId === 'modal-manage') {
    generateCaptcha('captcha-question-2', 'captcha-answer-2');
    // Reset manage modal state
    resetManageModal();
  }
}

async function resetManageModal() {
  // Clear verification code input
  document.getElementById('verification-code').value = '';

  // Check if user is logged in with valid session
  console.log('Checking session for user login...');
  const sessionId = getSessionId();
  console.log('Found session ID:', sessionId ? sessionId.substring(0, 8) + '...' : 'None');

  const isLoggedIn = await verifySession();
  console.log('Session verification result:', isLoggedIn);

  if (isLoggedIn) {
    console.log('User is logged in, showing management interface');
    // Show only logged-in state
    document.getElementById('form-verify-email').style.display = 'none';
    document.getElementById('verification-step').style.display = 'none';
    document.getElementById('codes-list').style.display = 'block';
    document.getElementById('logout-section').style.display = 'block';
    await loadUserCodes();
  } else {
    console.log('User is not logged in, showing login interface');
    // Show login state
    document.getElementById('form-verify-email').style.display = 'block';
    document.getElementById('verification-step').style.display = 'none';
    document.getElementById('codes-list').style.display = 'none';
    document.getElementById('logout-section').style.display = 'none';
  }
}

function closeModal(modalId) {
  document.getElementById(modalId).style.display = 'none';
  // 重置表单
  document.querySelector(`#${modalId} form`).reset();
  document.getElementById('add-result').style.display = 'none';
  document.getElementById('manage-result').style.display = 'none';
  document.getElementById('verification-step').style.display = 'none';
  document.getElementById('codes-list').style.display = 'none';
}

// Toggle between ZOV and OAM form fields (Robust Edition)
function toggleQueryTypeFields() {
  const checkedRadio = document.querySelector('input[name="query_type"]:checked');
  if (!checkedRadio) return;

  const queryType = checkedRadio.value;
  const zovSection = document.getElementById('zov-fields');
  const oamSection = document.getElementById('oam-fields');

  if (queryType === 'oam') {
    // Hide ZOV with animation
    zovSection.classList.add('fade-out');
    setTimeout(() => {
      zovSection.style.display = 'none';
      zovSection.classList.remove('fade-out');

      // Show OAM with animation
      oamSection.style.display = 'block';
      oamSection.classList.add('fade-in');
      setTimeout(() => oamSection.classList.remove('fade-in'), 400);
    }, 300);
  } else {
    // Hide OAM with animation
    oamSection.classList.add('fade-out');
    setTimeout(() => {
      oamSection.style.display = 'none';
      oamSection.classList.remove('fade-out');

      // Show ZOV with animation
      zovSection.style.display = 'block';
      zovSection.classList.add('fade-in');
      setTimeout(() => zovSection.classList.remove('fade-in'), 400);
    }, 300);
  }
}

// Add event listeners for radio buttons centrally
function initTypeSelectors() {
  const container = document.querySelector('.segmented-control');
  if (container) {
    container.addEventListener('change', (e) => {
      if (e.target.name === 'query_type') {
        toggleQueryTypeFields();
      }
    });
  }
}

// Populate year dropdown with sensible range
function populateYears() {
  const yearSelect = document.getElementById('oam-year');
  if (!yearSelect) return;

  const currentYear = new Date().getFullYear();
  yearSelect.innerHTML = '';

  // Years from 2020 to current year + 2
  for (let y = 2020; y <= currentYear + 2; y++) {
    const option = document.createElement('option');
    option.value = y;
    option.textContent = y;
    if (y === currentYear) option.selected = true;
    yearSelect.appendChild(option);
  }
}

// Initialize year dropdown on page load
populateYears();

// 添加代码表单提交
document.getElementById('form-add-code').addEventListener('submit', async (e) => {
  e.preventDefault();

  const queryType = document.querySelector('input[name="query_type"]:checked').value;
  const email = document.getElementById('input-email').value.trim();
  const captchaAnswer = parseInt(document.getElementById('captcha-answer').value);
  const correctAnswer = parseInt(document.getElementById('captcha-question').dataset.answer);

  // 验证码检查
  if (captchaAnswer !== correctAnswer) {
    showResult('add-result', 'Incorrect answer to security question!', 'error');
    generateCaptcha('captcha-question', 'captcha-answer');
    return;
  }

  let requestBody = { email, captcha_answer: captchaAnswer, query_type: queryType };

  if (queryType === 'zov') {
    // ZOV format validation
    const code = document.getElementById('input-code').value.trim();
    if (!/^[A-Z]{4}\d{12}$/.test(code)) {
      showResult('add-result', 'Invalid ŽOV format! Expected: PEKI202501010001', 'error');
      return;
    }
    requestBody.code = code;
  } else {
    // OAM format validation
    const serial = document.getElementById('oam-serial').value.trim();
    const suffix = document.getElementById('oam-suffix').value.trim();
    const oamType = document.getElementById('oam-type').value;
    const oamYear = document.getElementById('oam-year').value;

    if (!serial || !/^\d+$/.test(serial)) {
      showResult('add-result', 'OAM serial number must be numeric!', 'error');
      return;
    }

    // Build OAM code string
    let codeStr = `OAM-${serial}`;
    if (suffix) codeStr += `-${suffix}`;
    codeStr += `/${oamType}/${oamYear}`;

    requestBody.code = codeStr;
    requestBody.oam_serial = serial;
    requestBody.oam_suffix = suffix || null;
    requestBody.oam_type = oamType;
    requestBody.oam_year = parseInt(oamYear);
  }

  // 添加加载状态
  const submitBtn = e.target.querySelector('button[type="submit"]');
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner">⟳</span> Sending...';

  // 清除之前的结果消息
  document.getElementById('add-result').style.display = 'none';

  try {
    const response = await fetch('/api/add-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });

    const result = await response.json();

    if (response.ok) {
      showResult('add-result', 'Verification email sent! Please check your inbox and click the verification link.', 'success');
      document.getElementById('form-add-code').reset();
      toggleQueryTypeFields(); // Reset form visibility
      generateCaptcha('captcha-question', 'captcha-answer');
    } else {
      showResult('add-result', result.error || 'Failed to submit request', 'error');
      generateCaptcha('captcha-question', 'captcha-answer');
    }
  } catch (error) {
    showResult('add-result', 'Network error. Please try again.', 'error');
  } finally {
    // 恢复按钮状态
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalText;
  }
});

// 邮箱验证表单提交
document.getElementById('form-verify-email').addEventListener('submit', async (e) => {
  e.preventDefault();

  const email = document.getElementById('verify-email').value.trim();
  const captchaAnswer = parseInt(document.getElementById('captcha-answer-2').value);
  const correctAnswer = parseInt(document.getElementById('captcha-question-2').dataset.answer);

  if (captchaAnswer !== correctAnswer) {
    showResult('manage-result', 'Incorrect answer to security question!', 'error');
    generateCaptcha('captcha-question-2', 'captcha-answer-2');
    return;
  }

  // Check if email was sent recently (60 seconds cooldown)
  const lastSentKey = `lastEmailSent_${email}`;
  const lastSent = localStorage.getItem(lastSentKey);
  const now = Date.now();

  if (lastSent && (now - parseInt(lastSent)) < 60000) {
    const remainingSeconds = Math.ceil((60000 - (now - parseInt(lastSent))) / 1000);
    showResult('manage-result', `Please wait ${remainingSeconds} seconds before sending another code`, 'error');
    return;
  }

  // Disable button and show sending state
  const submitBtn = e.target.querySelector('button[type="submit"]');
  const originalText = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner">⟳</span> Sending...';

  // 清除之前的结果消息
  document.getElementById('manage-result').style.display = 'none';

  try {
    const response = await fetch('/api/send-manage-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, captcha_answer: captchaAnswer })
    });

    const result = await response.json();

    if (response.ok) {
      // Store send time
      localStorage.setItem(lastSentKey, now.toString());

      showResult('manage-result', 'Verification code sent to your email!', 'success');
      document.getElementById('verification-step').style.display = 'block';

      // Start countdown
      startSendCooldown(submitBtn, originalText, 60);
    } else {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
      showResult('manage-result', result.error || 'Failed to send verification code', 'error');
      generateCaptcha('captcha-question-2', 'captcha-answer-2');
    }
  } catch (error) {
    submitBtn.disabled = false;
    submitBtn.innerHTML = originalText;
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
});

// Countdown function for send button
function startSendCooldown(button, originalText, seconds) {
  let remaining = seconds;
  const updateButton = () => {
    if (remaining > 0) {
      button.textContent = `Wait ${remaining}s`;
      remaining--;
      setTimeout(updateButton, 1000);
    } else {
      button.disabled = false;
      button.textContent = originalText;
    }
  };
  updateButton();
}

// Session Management
function getSessionId() {
  // Prefer localStorage, fallback to cookie
  const fromStorage = localStorage.getItem('visa_session_id');
  if (fromStorage) return fromStorage;
  const m = document.cookie.match(/(?:^|; )visa_session_id=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function setSessionId(sessionId) {
  localStorage.setItem('visa_session_id', sessionId);
  // Also set a cookie (7 days) to persist across tabs and in case storage is cleared
  const maxAge = 7 * 24 * 3600;
  document.cookie = `visa_session_id=${encodeURIComponent(sessionId)}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
}

function clearSession() {
  localStorage.removeItem('visa_session_id');
  // Clear cookie
  document.cookie = 'visa_session_id=; Path=/; Max-Age=0; SameSite=Lax';
}

async function verifySession() {
  const sessionId = getSessionId();
  if (!sessionId) return false;

  try {
    const response = await fetch('/api/verify-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    });

    if (response.ok) {
      const result = await response.json();
      return result.valid;
    } else {
      clearSession();
      return false;
    }
  } catch (error) {
    clearSession();
    return false;
  }
}

async function loginWithVerificationCode() {
  const email = document.getElementById('verify-email').value.trim();
  const verificationCode = document.getElementById('verification-code').value.trim();

  if (!/^\d{6}$/.test(verificationCode)) {
    showResult('manage-result', 'Please enter a valid 6-digit verification code', 'error');
    return;
  }

  try {
    const response = await fetch('/api/verify-manage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, verification_code: verificationCode })
    });

    const result = await response.json();

    if (response.ok) {
      // Save session if provided
      if (result.session_id) {
        setSessionId(result.session_id);
        console.log('Session created for seamless management experience');
      }

      // Display user codes
      displayUserCodes(result.codes);

      // Hide login forms and show only codes management
      document.getElementById('form-verify-email').style.display = 'none';
      document.getElementById('verification-step').style.display = 'none';
      document.getElementById('codes-list').style.display = 'block';
      document.getElementById('logout-section').style.display = 'block';

      showResult('manage-result', 'Login successful!', 'success');
    } else {
      showResult('manage-result', result.error || 'Invalid verification code', 'error');
    }
  } catch (error) {
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
}

async function logout() {
  const sessionId = getSessionId();
  if (sessionId) {
    try {
      await fetch('/api/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });
    } catch (error) {
      console.log('Logout request failed, but clearing local session');
    }
  }

  clearSession();

  // Restore login interface
  document.getElementById('form-verify-email').style.display = 'block';
  document.getElementById('verification-step').style.display = 'none';
  document.getElementById('codes-list').style.display = 'none';
  document.getElementById('logout-section').style.display = 'none';

  // Clear forms
  document.getElementById('verify-email').value = '';
  document.getElementById('verification-code').value = '';

  showResult('manage-result', 'Logged out successfully', 'success');
}

// 验证并显示用户代码
async function verifyAndShowCodes() {
  await loginWithVerificationCode();
}

// 显示用户代码列表
function displayUserCodes(codes) {
  const container = document.getElementById('user-codes-container');

  if (codes.length === 0) {
    container.innerHTML = '<p>No codes found for this email address.</p>';
    return;
  }

  container.innerHTML = codes.map(code => {
    const nextCheckTooltip = code.next_check ?
      `title="Next check: ${new Date(code.next_check).toLocaleString()}"` : '';

    return `
    <div class="user-code-item" ${nextCheckTooltip}>
      <span class="code">${code.code}</span>
      <span class="status">${code.status || 'Pending first check'}</span>
      ${code.note ? `<span class="note">${code.note}</span>` : ''}
      <button class="btn-danger btn-small" onclick="deleteCode('${code.code}', '${code.email}')">Delete</button>
    </div>
  `;
  }).join('');
}

async function loadUserCodes() {
  const sessionId = getSessionId();
  if (!sessionId) return;

  try {
    const response = await fetch('/api/verify-manage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId })
    });

    const result = await response.json();

    if (response.ok) {
      displayUserCodes(result.codes);
    } else {
      if (response.status === 401) {
        clearSession();
        document.getElementById('codes-list').style.display = 'none';
        document.getElementById('logout-section').style.display = 'none';
      }
      showResult('manage-result', result.error || 'Failed to load codes', 'error');
    }
  } catch (error) {
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
}

// 删除代码
async function deleteCode(code, email) {
  if (!confirm(`Are you sure you want to delete ${code}?`)) {
    return;
  }

  const sessionId = getSessionId();
  if (!sessionId) {
    showResult('manage-result', 'Please log in first', 'error');
    return;
  }

  try {
    const response = await fetch('/api/delete-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, email, session_id: sessionId })
    });

    const result = await response.json();

    if (response.ok) {
      showResult('manage-result', `Code ${code} deleted successfully!`, 'success');
      // 重新获取并显示代码列表
      setTimeout(() => loadUserCodes(), 1000);
    } else {
      if (response.status === 401) {
        clearSession();
        document.getElementById('codes-list').style.display = 'none';
        document.getElementById('logout-section').style.display = 'none';
        showResult('manage-result', 'Session expired. Please log in again.', 'error');
      } else {
        showResult('manage-result', result.error || 'Failed to delete code', 'error');
      }
    }
  } catch (error) {
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
}

// 显示结果消息
function showResult(elementId, message, type) {
  const element = document.getElementById(elementId);
  element.textContent = message;
  element.className = `result-message ${type}`;
  element.style.display = message ? 'block' : 'none';
}

// Hash路由处理
function handleHashRouting() {
  const hash = window.location.hash.substring(1); // Remove #
  console.log('Handling hash routing:', hash);

  switch (hash) {
    case 'manage':
      console.log('Opening manage modal from hash');
      openModal('modal-manage');
      break;
    case 'add':
      console.log('Opening add modal from hash');
      openModal('modal-add');
      break;
    default:
      // No specific hash, close all modals
      if (hash === '') {
        closeAllModals();
      }
      break;
  }
}

// 关闭所有模态框
function closeAllModals() {
  document.querySelectorAll('.modal').forEach(modal => {
    modal.style.display = 'none';
  });
}

// 事件监听器
document.addEventListener('DOMContentLoaded', async () => {
  // Initialize UI components
  initTypeSelectors();
  populateYears();
  generateCaptcha('captcha-question', 'captcha-answer');
  generateCaptcha('captcha-question-2', 'captcha-answer-2');

  // Check for existing session on page load
  if (await verifySession()) {
    await loadUserCodes();
    document.getElementById('codes-list').style.display = 'block';
    document.getElementById('logout-section').style.display = 'block';
  }

  // Handle URL hash routing
  handleHashRouting();

  // Listen for hash changes
  window.addEventListener('hashchange', handleHashRouting);

  // 按钮点击事件
  document.getElementById('btn-add-code').addEventListener('click', () => openModal('modal-add'));
  document.getElementById('btn-manage-codes').addEventListener('click', () => openModal('modal-manage'));

  // 关闭按钮事件 (Robust delegation)
  document.addEventListener('click', (e) => {
    if (e.target.classList.contains('close')) {
      const modal = e.target.closest('.modal');
      closeModal(modal.id);
    }
  });

  // 点击模态框外部关闭
  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
      closeModal(e.target.id);
    }
  });
});
