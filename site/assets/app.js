async function loadData() {
  try {
    const res = await fetch('status.json?_=' + Date.now());
    const data = await res.json();
    return data;
  } catch (e) {
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
  document.getElementById('generatedAt').textContent = 'Last updated: ' + (data.generated_at || '');
  const tb = document.querySelector('#tbl tbody');
  tb.innerHTML = '';
  const entries = Object.values(data.items || {}).sort((a, b) => {
    if (sortState.key === 'status') {
      const as = String(a.status||'').toLowerCase();
      const bs = String(b.status||'').toLowerCase();
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
      const slex = (String(a.code||'')).localeCompare(String(b.code||''));
      return sortState.dir === 'asc' ? slex : -slex;
    } else {
      // code sort
      const ak = codeKeyBigInt(a.code);
      const bk = codeKeyBigInt(b.code);
      if (ak !== null && bk !== null) {
        if (ak < bk) return sortState.dir === 'asc' ? -1 : 1;
        if (ak > bk) return sortState.dir === 'asc' ? 1 : -1;
        const slex = (String(a.code||'')).localeCompare(String(b.code||''));
        return sortState.dir === 'asc' ? slex : -slex;
      }
      const slex = (String(a.code||'')).localeCompare(String(b.code||''));
      return sortState.dir === 'asc' ? slex : -slex;
    }
  });
  const q = (document.getElementById('filter').value || '').toLowerCase();
  for (const it of entries) {
    const hay = (it.code + ' ' + (it.status||'')).toLowerCase();
    if (q && !hay.includes(q)) continue;
    const tr = document.createElement('tr');
    const tdCode = document.createElement('td'); tdCode.textContent = it.code || '';
    const tdStatus = document.createElement('td');
    const span = document.createElement('span');
    span.className = 'status-tag ' + statusClass(it.status);
    span.textContent = it.status || '';
    tdStatus.appendChild(span);
    const tdLC = document.createElement('td'); tdLC.textContent = it.last_checked || '';
    const tdLCh = document.createElement('td'); tdLCh.textContent = it.last_changed || '';
    const tdCh = document.createElement('td'); tdCh.textContent = it.channel || '';
    tr.appendChild(tdCode); tr.appendChild(tdStatus); tr.appendChild(tdLC); tr.appendChild(tdLCh); tr.appendChild(tdCh);
    tb.appendChild(tr);
  }
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
  } else if (modalId === 'modal-manage') {
    generateCaptcha('captcha-question-2', 'captcha-answer-2');
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

// 添加代码表单提交
document.getElementById('form-add-code').addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const code = document.getElementById('input-code').value.trim();
  const email = document.getElementById('input-email').value.trim();
  const captchaAnswer = parseInt(document.getElementById('captcha-answer').value);
  const correctAnswer = parseInt(document.getElementById('captcha-question').dataset.answer);
  
  // 验证码检查
  if (captchaAnswer !== correctAnswer) {
    showResult('add-result', 'Incorrect answer to security question!', 'error');
    generateCaptcha('captcha-question', 'captcha-answer');
    return;
  }
  
  // 代码格式验证
  if (!/^[A-Z]{4}\d{12}$/.test(code)) {
    showResult('add-result', 'Invalid code format! Expected format: PEKI202501010001', 'error');
    return;
  }
  
  try {
    const response = await fetch('/api/add-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, email, captcha_answer: captchaAnswer })
    });
    
    const result = await response.json();
    
    if (response.ok) {
      showResult('add-result', 'Verification email sent! Please check your inbox and click the verification link.', 'success');
      document.getElementById('form-add-code').reset();
    } else {
      showResult('add-result', result.error || 'Failed to submit request', 'error');
      generateCaptcha('captcha-question', 'captcha-answer');
    }
  } catch (error) {
    showResult('add-result', 'Network error. Please try again.', 'error');
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
  
  try {
    const response = await fetch('/api/send-manage-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, captcha_answer: captchaAnswer })
    });
    
    const result = await response.json();
    
    if (response.ok) {
      showResult('manage-result', 'Verification code sent to your email!', 'success');
      document.getElementById('verification-step').style.display = 'block';
    } else {
      showResult('manage-result', result.error || 'Failed to send verification code', 'error');
      generateCaptcha('captcha-question-2', 'captcha-answer-2');
    }
  } catch (error) {
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
});

// 验证并显示用户代码
async function verifyAndShowCodes() {
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
      displayUserCodes(result.codes);
      document.getElementById('codes-list').style.display = 'block';
      showResult('manage-result', '', 'success');
    } else {
      showResult('manage-result', result.error || 'Invalid verification code', 'error');
    }
  } catch (error) {
    showResult('manage-result', 'Network error. Please try again.', 'error');
  }
}

// 显示用户代码列表
function displayUserCodes(codes) {
  const container = document.getElementById('user-codes-container');
  
  if (codes.length === 0) {
    container.innerHTML = '<p>No codes found for this email address.</p>';
    return;
  }
  
  container.innerHTML = codes.map(code => `
    <div class="user-code-item">
      <span class="code">${code.code}</span>
      <span class="status">${code.status || 'Pending first check'}</span>
      <button class="btn-danger btn-small" onclick="deleteCode('${code.code}', '${code.email}')">Delete</button>
    </div>
  `).join('');
}

// 删除代码
async function deleteCode(code, email) {
  if (!confirm(`Are you sure you want to delete ${code}?`)) {
    return;
  }
  
  const verificationCode = document.getElementById('verification-code').value.trim();
  
  try {
    const response = await fetch('/api/delete-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, email, verification_code: verificationCode })
    });
    
    const result = await response.json();
    
    if (response.ok) {
      showResult('manage-result', `Code ${code} deleted successfully!`, 'success');
      // 重新获取并显示代码列表
      setTimeout(() => verifyAndShowCodes(), 1000);
    } else {
      showResult('manage-result', result.error || 'Failed to delete code', 'error');
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

// 事件监听器
document.addEventListener('DOMContentLoaded', () => {
  // 按钮点击事件
  document.getElementById('btn-add-code').addEventListener('click', () => openModal('modal-add'));
  document.getElementById('btn-manage-codes').addEventListener('click', () => openModal('modal-manage'));
  
  // 关闭按钮事件
  document.querySelectorAll('.close').forEach(closeBtn => {
    closeBtn.addEventListener('click', (e) => {
      const modal = e.target.closest('.modal');
      closeModal(modal.id);
    });
  });
  
  // 点击模态框外部关闭
  window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
      closeModal(e.target.id);
    }
  });
});
