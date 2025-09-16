async function loadData() {
  try {
    const res = await fetch('status.json?_=' + Date.now());
    const data = await res.json();
    return data;
  } catch (e) {
    return { generated_at: '', items: {} };
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
  const entries = Object.values(data.items || {}).sort((a,b)=> (a.code||'').localeCompare(b.code||''));
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

refresh();
setInterval(refresh, 60000);
