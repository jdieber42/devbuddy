// ── State ────────────────────────────────────────────────────────────────────
let charts = {};

function getFilters() {
  return {
    from_date: document.getElementById('f-from').value || null,
    to_date:   document.getElementById('f-to').value   || null,
    project:   document.getElementById('f-project').value || null,
    model:     document.getElementById('f-model').value   || null,
  };
}

function buildQS(extra) {
  const f = { ...getFilters(), ...extra };
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? '?' + s : '';
}

function fmtTokens(n) {
  if (!n) return '0';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e4) return (n / 1e3).toFixed(0) + 'K';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}

// ── Colours ──────────────────────────────────────────────────────────────────
const PALETTE = [
  '#38bdf8','#818cf8','#34d399','#fbbf24','#f87171',
  '#a78bfa','#fb923c','#4ade80','#e879f9','#67e8f9',
];

// ── Overview cards ───────────────────────────────────────────────────────────
async function loadOverview() {
  const res = await fetch('/api/overview' + buildQS());
  const d = await res.json();
  document.getElementById('c-sessions').textContent = d.sessions.toLocaleString();
  document.getElementById('c-tokens').textContent   = fmtTokens(d.total_tokens);
  document.getElementById('c-hours').textContent    = d.active_hours.toLocaleString();
  document.getElementById('c-queries').textContent  = d.total_queries.toLocaleString() + ' total queries';
  if (d.date_range && d.date_range.from) {
    document.getElementById('c-date-range').textContent =
      d.date_range.from + ' → ' + d.date_range.to;
  }
}

// ── Daily chart ──────────────────────────────────────────────────────────────
async function loadDaily() {
  const res = await fetch('/api/daily' + buildQS());
  const d = await res.json();

  if (charts.daily) charts.daily.destroy();
  const ctx = document.getElementById('daily-chart').getContext('2d');
  charts.daily = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [
        {
          label: 'Tokens',
          data: d.tokens,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.08)',
          borderWidth: 2,
          pointRadius: 2,
          tension: 0.3,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ' ' + fmtTokens(ctx.raw) + ' tokens',
          },
        },
      },
      scales: {
        x: { ticks: { color: '#64748b', maxTicksLimit: 12 }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b', callback: fmtTokens }, grid: { color: '#1e293b' } },
      },
    },
  });
}

// ── Projects charts ───────────────────────────────────────────────────────────
async function loadProjects() {
  const res = await fetch('/api/projects' + buildQS());
  const data = await res.json();

  const labels   = data.map(p => p.project);
  const tokens   = data.map(p => p.total_tokens);
  const sessions = data.map(p => p.session_count);
  const colors   = PALETTE.slice(0, data.length);

  // Bar chart — tokens by project
  if (charts.efficiency) charts.efficiency.destroy();
  const ctx1 = document.getElementById('efficiency-chart').getContext('2d');
  charts.efficiency = new Chart(ctx1, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Tokens',
        data: tokens,
        backgroundColor: colors,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: ctx => ' ' + fmtTokens(ctx.raw) + ' tokens' },
        },
      },
      scales: {
        x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b', callback: fmtTokens }, grid: { color: '#1e293b' } },
      },
    },
  });

  // Donut — sessions by project
  if (charts.donut) charts.donut.destroy();
  const ctx2 = document.getElementById('donut-chart').getContext('2d');
  charts.donut = new Chart(ctx2, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: sessions,
        backgroundColor: colors,
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      cutout: '60%',
      plugins: {
        legend: { position: 'right', labels: { color: '#94a3b8', boxWidth: 12, padding: 10 } },
        tooltip: {
          callbacks: { label: ctx => ' ' + ctx.raw + ' sessions' },
        },
      },
    },
  });
}

// ── Top prompts table ─────────────────────────────────────────────────────────
async function loadTopPrompts() {
  const res = await fetch('/api/top-prompts' + buildQS());
  const data = await res.json();
  const tbody = document.getElementById('prompts-body');
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">No data</td></tr>';
    return;
  }
  tbody.innerHTML = data.map(p => `
    <tr>
      <td><div class="prompt-text" title="${escHtml(p.user_prompt)}">${escHtml(p.user_prompt)}</div></td>
      <td class="num">${fmtTokens(p.total_tokens)}</td>
      <td class="num">${p.query_count}</td>
      <td><span class="badge">${escHtml(p.project || '')}</span></td>
    </tr>
  `).join('');
}

// ── Sessions table ────────────────────────────────────────────────────────────
async function loadSessions() {
  const res = await fetch('/api/sessions' + buildQS());
  const data = await res.json();
  const tbody = document.getElementById('sessions-body');
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">No sessions</td></tr>';
    return;
  }
  tbody.innerHTML = data.map(s => `
    <tr>
      <td><div class="prompt-text" title="${escHtml(s.first_prompt)}">${escHtml(s.first_prompt)}</div></td>
      <td><span class="badge">${escHtml(s.project)}</span></td>
      <td>${s.date}</td>
      <td style="color:var(--muted);font-size:12px">${s.model ? s.model.replace('claude-', '') : '—'}</td>
      <td class="num">${s.query_count}</td>
      <td class="num">${fmtTokens(s.total_tokens)}</td>
    </tr>
  `).join('');
}

// ── Insights ──────────────────────────────────────────────────────────────────
async function loadInsights() {
  const res = await fetch('/api/insights' + buildQS());
  const data = await res.json();
  const container = document.getElementById('insights-list');
  if (!data.length) {
    container.innerHTML = '<div class="empty">No insights generated yet. Keep coding!</div>';
    return;
  }
  container.innerHTML = data.map(ins => `
    <div class="insight-card ${ins.type}">
      <div class="insight-title">${escHtml(ins.title)}</div>
      <div class="insight-desc">${escHtml(ins.description)}</div>
      ${ins.action ? `<div class="insight-action">${escHtml(ins.action)}</div>` : ''}
    </div>
  `).join('');
}

// ── Filters ───────────────────────────────────────────────────────────────────
async function loadFilters() {
  const res = await fetch('/api/filters');
  const d = await res.json();
  const ps = document.getElementById('f-project');
  const ms = document.getElementById('f-model');
  ps.innerHTML = '<option value="">All Projects</option>' +
    d.projects.map(p => `<option value="${escAttr(p)}">${escHtml(p)}</option>`).join('');
  ms.innerHTML = '<option value="">All Models</option>' +
    d.models.map(m => `<option value="${escAttr(m)}">${escHtml(m)}</option>`).join('');
}

function applyFilters() { loadAll(); }

function clearFilters() {
  document.getElementById('f-from').value = '';
  document.getElementById('f-to').value = '';
  document.getElementById('f-project').value = '';
  document.getElementById('f-model').value = '';
  loadAll();
}

// ── Refresh ────────────────────────────────────────────────────────────────────
async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('loading');
  btn.textContent = '⟳ Refreshing…';
  try {
    const res = await fetch('/api/refresh');
    const d = await res.json();
    const banner = document.getElementById('demo-banner');
    banner.style.display = d.using_demo ? 'block' : 'none';
    await loadFilters();
    await loadAll();
  } finally {
    btn.classList.remove('loading');
    btn.textContent = '↻ Refresh';
  }
}

// ── Load all ───────────────────────────────────────────────────────────────────
function loadAll() {
  loadOverview();
  loadDaily();
  loadProjects();
  loadTopPrompts();
  loadSessions();
  loadInsights();
}

// ── Escape helpers ─────────────────────────────────────────────────────────────
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escAttr(str) { return escHtml(str); }

// ── Boot ───────────────────────────────────────────────────────────────────────
(async () => {
  await loadFilters();
  loadAll();
})();
