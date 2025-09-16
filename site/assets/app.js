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
    arrowCode.textContent = sortState.dir === 'asc' ? '↑' : '↓';
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
