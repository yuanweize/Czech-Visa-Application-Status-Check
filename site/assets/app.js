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

function statusClass(s) {
  const t = (s || '').toLowerCase();
  if (t.includes('granted') || t.includes('已通过')) return 'status-granted';
  if (t.includes('proceedings') || t.includes('审理中')) return 'status-proc';
  if (t.includes('not found') || t.includes('未找到')) return 'status-notfound';
  return 'status-unknown';
}

function render(data) {
  document.getElementById('generatedAt').textContent = 'Generated at: ' + (data.generated_at || '');
  const tb = document.querySelector('#tbl tbody');
  tb.innerHTML = '';
  const sortBy = (document.getElementById('sortBy')?.value) || 'code-asc';
  const entries = Object.values(data.items || {}).sort((a, b) => {
    if (sortBy === 'status-asc') {
      const as = String(a.status||'').toLowerCase();
      const bs = String(b.status||'').toLowerCase();
      if (as < bs) return -1;
      if (as > bs) return 1;
      // tie-break by code numeric value
      const ak = codeKeyBigInt(a.code);
      const bk = codeKeyBigInt(b.code);
      if (ak !== null && bk !== null) {
        if (ak < bk) return -1;
        if (ak > bk) return 1;
      }
      return (String(a.code||'')).localeCompare(String(b.code||''));
    }
    const ak = codeKeyBigInt(a.code);
    const bk = codeKeyBigInt(b.code);
    if (ak !== null && bk !== null) {
      if (ak < bk) return -1;
      if (ak > bk) return 1;
      return (String(a.code||'')).localeCompare(String(b.code||''));
    }
    // Fallback to lexicographic if numeric key not available
    return (String(a.code||'')).localeCompare(String(b.code||''));
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
  const data = await loadData();
  render(data);
}

document.getElementById('refresh').addEventListener('click', refresh);
const filter = document.getElementById('filter');
filter.addEventListener('input', refresh);
const sortBy = document.getElementById('sortBy');
if (sortBy) sortBy.addEventListener('change', refresh);

refresh();
setInterval(refresh, 60000);
