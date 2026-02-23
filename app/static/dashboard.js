// ── State ────────────────────────────────────────────────────────────────────
let charts = {};
let currentSessions = [];
let currentTopPrompts = [];
let liveInterval = null;
let heatmapMetric = 'tokens';

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

// ── Theme ─────────────────────────────────────────────────────────────────────
function getTheme() {
  return document.documentElement.dataset.theme || 'dark';
}

function initTheme() {
  const saved = localStorage.getItem('devbuddy-theme') || 'dark';
  document.documentElement.dataset.theme = saved;
  updateThemeBtn(saved);
}

function toggleTheme() {
  const next = getTheme() === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('devbuddy-theme', next);
  updateThemeBtn(next);
  loadDaily();
  loadProjects();
}

function updateThemeBtn(theme) {
  const btn = document.getElementById('theme-btn');
  if (btn) btn.textContent = theme === 'dark' ? '\u2600' : '\uD83C\uDF19';
}

function getChartScale() {
  return {
    tick: '#64748b',
    grid: getTheme() === 'light' ? '#e2e8f0' : '#334155',
  };
}

function makeGradient(ctx, r, g, b) {
  const grad = ctx.createLinearGradient(0, 0, 0, 300);
  const a = getTheme() === 'light' ? 0.18 : 0.25;
  grad.addColorStop(0, `rgba(${r},${g},${b},${a})`);
  grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
  return grad;
}

const TOOLTIP_STYLE = {
  backgroundColor: 'rgba(15,23,42,0.92)',
  titleColor: '#e2e8f0',
  bodyColor: '#94a3b8',
  borderColor: '#334155',
  borderWidth: 1,
  padding: 10,
  cornerRadius: 6,
};

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
      d.date_range.from + ' \u2192 ' + d.date_range.to;
  }
}

// ── Daily chart ──────────────────────────────────────────────────────────────
async function loadDaily() {
  const res = await fetch('/api/daily' + buildQS());
  const d = await res.json();
  const sc = getChartScale();

  if (charts.daily) charts.daily.destroy();
  const ctx = document.getElementById('daily-chart').getContext('2d');
  const gradient = makeGradient(ctx, 56, 189, 248);

  charts.daily = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.labels,
      datasets: [
        {
          label: 'Tokens',
          data: d.tokens,
          borderColor: '#38bdf8',
          backgroundColor: gradient,
          borderWidth: 2,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: '#38bdf8',
          pointHoverBorderColor: '#fff',
          pointHoverBorderWidth: 2,
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
          ...TOOLTIP_STYLE,
          callbacks: {
            label: ctx => '  ' + fmtTokens(ctx.raw) + ' tokens',
          },
        },
      },
      scales: {
        x: { ticks: { color: sc.tick, maxTicksLimit: 12 }, grid: { color: sc.grid } },
        y: { ticks: { color: sc.tick, callback: fmtTokens }, grid: { color: sc.grid } },
      },
    },
  });
}

// ── Projects charts ────────────────────────────────────────────────────────────
async function loadProjects() {
  const res = await fetch('/api/projects' + buildQS());
  const data = await res.json();
  const sc = getChartScale();

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
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          ...TOOLTIP_STYLE,
          callbacks: {
            label: ctx => '  ' + fmtTokens(ctx.raw) + ' tokens',
            afterLabel: ctx => {
              if (!ctx.raw) return '';
              const total = tokens.reduce((a, b) => a + b, 0) || 1;
              return '  ' + ((ctx.raw / total) * 100).toFixed(1) + '% of total';
            },
          },
        },
      },
      scales: {
        x: { ticks: { color: sc.tick }, grid: { color: sc.grid } },
        y: { ticks: { color: sc.tick, callback: fmtTokens }, grid: { color: sc.grid } },
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
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      cutout: '60%',
      plugins: {
        legend: { position: 'right', labels: { color: '#94a3b8', boxWidth: 12, padding: 10 } },
        tooltip: {
          ...TOOLTIP_STYLE,
          callbacks: {
            label: ctx => {
              const total = sessions.reduce((a, b) => a + b, 0) || 1;
              const pct = ((ctx.raw / total) * 100).toFixed(1);
              return `  ${ctx.raw} sessions (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

// ── Top prompts table ─────────────────────────────────────────────────────────
async function loadTopPrompts() {
  const res = await fetch('/api/top-prompts' + buildQS());
  const data = await res.json();
  currentTopPrompts = data;
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
  currentSessions = data;
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
      <td style="color:var(--muted);font-size:12px">${s.model ? s.model.replace('claude-', '') : '\u2014'}</td>
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
  btn.textContent = '\u27F3 Refreshing\u2026';
  try {
    const res = await fetch('/api/refresh');
    const d = await res.json();
    const banner = document.getElementById('demo-banner');
    banner.style.display = d.using_demo ? 'block' : 'none';
    await loadFilters();
    await loadAll();
  } finally {
    btn.classList.remove('loading');
    btn.textContent = '\u21BB Refresh';
  }
}

// ── Export ─────────────────────────────────────────────────────────────────────
function toCSV(rows, cols) {
  const header = cols.join(',');
  const lines = rows.map(r => cols.map(c => JSON.stringify(r[c] ?? '')).join(','));
  return [header, ...lines].join('\n');
}

function downloadBlob(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportSessions(format) {
  if (!currentSessions.length) return;
  if (format === 'json') {
    downloadBlob(JSON.stringify(currentSessions, null, 2), 'sessions.json', 'application/json');
  } else {
    const cols = ['date', 'project', 'model', 'query_count', 'total_tokens', 'first_prompt'];
    downloadBlob(toCSV(currentSessions, cols), 'sessions.csv', 'text/csv');
  }
}

function exportTopPrompts(format) {
  if (!currentTopPrompts.length) return;
  if (format === 'json') {
    downloadBlob(JSON.stringify(currentTopPrompts, null, 2), 'top-prompts.json', 'application/json');
  } else {
    const cols = ['user_prompt', 'total_tokens', 'query_count', 'project'];
    downloadBlob(toCSV(currentTopPrompts, cols), 'top-prompts.csv', 'text/csv');
  }
}

// ── Live monitoring ────────────────────────────────────────────────────────────
function toggleLive() {
  const btn = document.getElementById('live-btn');
  if (liveInterval) {
    clearInterval(liveInterval);
    liveInterval = null;
    btn.classList.remove('live-active');
    btn.innerHTML = '&#9654; Live';
  } else {
    liveInterval = setInterval(checkForChanges, 30000);
    btn.classList.add('live-active');
    btn.innerHTML = '&#9646;&#9646; Live';
  }
}

async function checkForChanges() {
  try {
    const res = await fetch('/api/has-changes');
    const d = await res.json();
    if (d.changed) {
      await loadAll();
      showLiveToast();
    }
  } catch (_) { /* ignore network errors */ }
}

function showLiveToast() {
  const toast = document.getElementById('live-toast');
  if (!toast) return;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 2500);
}

// ── Activity heatmap ──────────────────────────────────────────────────────────
function setHeatmapMetric(metric, btn) {
  heatmapMetric = metric;
  document.querySelectorAll('.hm-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  loadHeatmap();
}

async function loadHeatmap() {
  const res = await fetch('/api/heatmap?metric=' + heatmapMetric);
  const data = await res.json();
  const container = document.getElementById('heatmap-grid');
  if (!data.length) { container.innerHTML = ''; return; }

  const values = data.map(d => d.value);
  const max = Math.max(...values, 1);

  function level(v) {
    if (v <= 0) return 0;
    if (v <= max * 0.25) return 1;
    if (v <= max * 0.5)  return 2;
    if (v <= max * 0.75) return 3;
    return 4;
  }

  const unitLabel = heatmapMetric === 'tokens' ? 'tokens'
    : heatmapMetric === 'prompts' ? 'prompts'
    : 'active hours';

  const numWeeks = Math.max(...data.map(d => d.week)) + 1;
  const lookup = {};
  for (const d of data) lookup[`${d.week}-${d.day}`] = d;

  // Month labels: shown at the first week of each new month
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const seenMonths = new Set();
  let monthHtml = '';
  for (let w = 0; w < numWeeks; w++) {
    for (let day = 0; day < 7; day++) {
      const cell = lookup[`${w}-${day}`];
      if (cell) {
        const mk = cell.date.substring(0, 7);
        if (!seenMonths.has(mk)) {
          seenMonths.add(mk);
          const mi = parseInt(cell.date.substring(5, 7)) - 1;
          monthHtml += `<span class="hm-month" style="grid-column:${w + 1}">${MONTHS[mi]}</span>`;
        }
        break;
      }
    }
  }

  // Cells
  let cellsHtml = '';
  for (let w = 0; w < numWeeks; w++) {
    for (let day = 0; day < 7; day++) {
      const cell = lookup[`${w}-${day}`];
      if (cell) {
        const lvl = level(cell.value);
        const [yr, mo, d] = cell.date.split('-').map(Number);
        const dateStr = new Date(yr, mo - 1, d).toLocaleDateString(undefined, {
          month: 'short', day: 'numeric', year: 'numeric'
        });
        const valStr = cell.value > 0
          ? cell.value.toLocaleString() + ' ' + unitLabel
          : 'No activity';
        cellsHtml += `<div class="hm-cell lvl-${lvl}" data-tip="${escHtml(dateStr + ' \u2014 ' + valStr)}"></div>`;
      } else {
        cellsHtml += `<div class="hm-cell lvl-0"></div>`;
      }
    }
  }

  // Day-of-week labels on the left
  const DAY_LABELS = ['Mon', '', 'Wed', '', 'Fri', '', 'Sun'];

  container.innerHTML = `
    <div class="hm-wrap">
      <div class="hm-day-col">
        <div class="hm-day-spacer"></div>
        ${DAY_LABELS.map(l => `<div class="hm-day-lbl">${l}</div>`).join('')}
      </div>
      <div class="hm-right">
        <div class="hm-month-row" style="display:grid;grid-template-columns:repeat(${numWeeks},14px);grid-template-rows:16px;">
          ${monthHtml}
        </div>
        <div class="hm-cells-grid">${cellsHtml}</div>
      </div>
    </div>
  `;

  // Floating tooltip (position:fixed so it never clips)
  const tip = document.getElementById('hm-tooltip');
  container.querySelectorAll('.hm-cell[data-tip]').forEach(el => {
    el.addEventListener('mouseenter', e => {
      tip.textContent = e.currentTarget.dataset.tip;
      tip.classList.add('visible');
    });
    el.addEventListener('mouseleave', () => tip.classList.remove('visible'));
    el.addEventListener('mousemove', e => {
      tip.style.left = (e.clientX + 14) + 'px';
      tip.style.top  = (e.clientY - 40) + 'px';
    });
  });
}

// ── Model stats ───────────────────────────────────────────────────────────────
async function loadModelStats() {
  const res = await fetch('/api/model-stats' + buildQS());
  const data = await res.json();
  const tbody = document.getElementById('model-body');
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">No data</td></tr>';
    return;
  }
  tbody.innerHTML = data.map(r => `
    <tr>
      <td style="color:var(--text);font-size:12px">${escHtml(r.model ? r.model.replace('claude-', '') : '—')}</td>
      <td class="num">${r.session_count.toLocaleString()}</td>
      <td class="num">${fmtTokens(r.total_tokens)}</td>
      <td class="num">${fmtTokens(r.avg_tokens_per_session)}</td>
      <td class="num">${r.avg_queries_per_session}</td>
    </tr>
  `).join('');
}

// ── Load all ───────────────────────────────────────────────────────────────────
function loadAll() {
  loadOverview();
  loadDaily();
  loadProjects();
  loadHeatmap();
  loadModelStats();
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
  initTheme();
  await loadFilters();
  loadAll();
})();
