async function initTopbar(activePage) {
  const res = await fetch('/api/session');
  if (!res.ok) { window.location.href = '/'; return null; }
  const data = await res.json();
  const user = data.user;

  const topbar = document.getElementById('topbar');
  topbar.innerHTML = `
    <div class="brand">Jute sliver analyzer</div>
    <div class="user-info">
      <span>${escapeHtml(user.name)}</span>
      <button class="secondary" id="logoutBtn" style="padding:4px 10px; font-size:12px;">Sign out</button>
      <button class="secondary" id="quitBtn" style="padding:4px 10px; font-size:12px; color:#b52020; border-color:#b52020;">Quit app</button>
    </div>
  `;

  document.getElementById('logoutBtn').addEventListener('click', async () => {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/';
  });

  document.getElementById('quitBtn').addEventListener('click', async () => {
    if (!confirm('Shut down the Jute Sliver Analyzer server?')) return;
    await fetch('/api/quit', { method: 'POST' }).catch(() => {});
    document.body.innerHTML = '<div style="font-family:sans-serif;padding:2rem;color:#555;">Server stopped. You can close this tab.</div>';
  });

  return user;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function scoreBadgeClass(score) {
  if (score >= 75) return { cls: 'badge-good', label: 'Good' };
  if (score >= 50) return { cls: 'badge-moderate', label: 'Moderate' };
  return { cls: 'badge-poor', label: 'Poor' };
}

function scoreColor(score) {
  if (score >= 75) return '#1D9E75';
  if (score >= 50) return '#BA7517';
  return '#E24B4A';
}

function timeAgo(isoString) {
  const date = new Date(isoString.replace(' ', 'T') + 'Z');
  const diffMs = Date.now() - date.getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  const days = Math.round(hrs / 24);
  if (days < 30) return days + 'd ago';
  return date.toLocaleDateString();
}

function drawHistogramCanvas(canvas, hist, meanAngle) {
  const w = 280, h = 140;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, w, h);
  const barW = w / hist.length;
  ctx.fillStyle = '#5DCAA5';
  hist.forEach((v, i) => {
    const barH = v * (h - 16);
    ctx.fillRect(i * barW, h - barH - 8, barW - 1, barH);
  });
  const meanX = (meanAngle / 180) * w;
  ctx.strokeStyle = '#D85A30';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(meanX, 0);
  ctx.lineTo(meanX, h);
  ctx.stroke();
}

function drawScoreDistributionCanvas(canvas, distribution) {
  const w = 280, h = 140;
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#faf9f6';
  ctx.fillRect(0, 0, w, h);

  const bars = [
    { label: 'Poor', value: distribution.poor, color: '#E24B4A' },
    { label: 'Moderate', value: distribution.moderate, color: '#BA7517' },
    { label: 'Good', value: distribution.good, color: '#1D9E75' },
  ];
  const max = Math.max(distribution.poor, distribution.moderate, distribution.good, 1);
  const padBottom = 22, padTop = 10;
  const usableH = h - padBottom - padTop;
  const barW = w / bars.length;

  ctx.font = '11px -apple-system, sans-serif';
  bars.forEach((b, i) => {
    const barH = (b.value / max) * usableH;
    const x = i * barW + barW * 0.2;
    const bw = barW * 0.6;
    ctx.fillStyle = b.color;
    ctx.fillRect(x, h - padBottom - barH, bw, barH);
    ctx.fillStyle = '#1d1d1b';
    ctx.textAlign = 'center';
    ctx.fillText(String(b.value), i * barW + barW / 2, h - padBottom - barH - 4);
    ctx.fillStyle = '#6b6a64';
    ctx.fillText(b.label, i * barW + barW / 2, h - 6);
  });
}

// ── Machine stage priority ordering (shared across Trends pages) ─────────────
// Fixed process order for known machine stages. Anything not in this list
// (custom machine names added later, or "Unspecified") is appended after,
// sorted alphabetically, so nothing ever gets dropped from a chart.
const MACHINE_STAGE_ORDER = [
  'Spreader', 'Inter-Spreader', 'Breaker-Card', 'Finisher-Card(rolls)',
  'Drawhead(sliver)', 'Draw-1', 'Draw-2', 'Draw-3', 'Spinning'
];

// Generic priority sort usable by any page, regardless of its row shape.
// getMachineName(item) -> machine name string (or null/'Unspecified')
// getTimestamp(item)   -> a value Date() can parse (or null if unknown)
function sortByMachinePriority(items, priority, getMachineName, getTimestamp) {
  const list = [...items];
  if (priority === 'logtime') {
    list.sort((a, b) => {
      const ta = getTimestamp(a);
      const tb = getTimestamp(b);
      const da = ta ? new Date(ta).getTime() : Infinity;
      const db = tb ? new Date(tb).getTime() : Infinity;
      return da - db;
    });
  } else {
    // 'stage' — fixed process order, unknown names appended alphabetically at the end
    list.sort((a, b) => {
      const na = getMachineName(a) || 'Unspecified';
      const nb = getMachineName(b) || 'Unspecified';
      const ia = MACHINE_STAGE_ORDER.indexOf(na);
      const ib = MACHINE_STAGE_ORDER.indexOf(nb);
      const ra = ia === -1 ? MACHINE_STAGE_ORDER.length : ia;
      const rb = ib === -1 ? MACHINE_STAGE_ORDER.length : ib;
      if (ra !== rb) return ra - rb;
      return na.localeCompare(nb);
    });
  }
  return list;
}

// ── Machine types (shared across Upload, Trends, Mass Variation) ──────────────
// Default machine list lives server-side in the `machines` table and is seeded
// from the same fixed list the app ships with. Custom machine names added by
// any user are saved permanently (shared across everyone) and can be removed
// again unless they're one of the built-in defaults.
async function fetchMachines() {
  try {
    const res = await fetch('/api/machines');
    if (!res.ok) return [];
    const data = await res.json();
    return data.machines || [];
  } catch (e) {
    return [];
  }
}

async function addMachine(name) {
  const res = await fetch('/api/machines', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Could not add machine');
  return data.machine;
}

async function deleteMachine(id) {
  const res = await fetch('/api/machines/' + id, { method: 'DELETE' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || 'Could not remove machine');
  return data;
}

// Populates a <select> with machine options (optional blank "All machines" /
// "Select machine" lead option), preserving the previous selection if it's
// still present after refresh.
function populateMachineSelect(selectEl, machines, opts) {
  const settings = Object.assign({ blankLabel: null, selected: '' }, opts || {});
  const prevValue = selectEl.value || settings.selected || '';
  selectEl.innerHTML = '';
  if (settings.blankLabel !== null) {
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = settings.blankLabel;
    selectEl.appendChild(blank);
  }
  machines.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.name;
    opt.textContent = m.name;
    selectEl.appendChild(opt);
  });
  if (prevValue && machines.some(m => m.name === prevValue)) {
    selectEl.value = prevValue;
  }
}

// ── Shared sidebar CSS injected once ────────────────────────────────────────
(function injectSidebarCSS() {
  if (document.getElementById('_toolSidebarCSS')) return;
  const s = document.createElement('style');
  s.id = '_toolSidebarCSS';
  s.textContent = `
    .tool-shell {
      display: flex;
      align-items: flex-start;
      min-height: calc(100vh - 57px);
    }
    .tool-sidebar {
      width: 220px;
      flex-shrink: 0;
      background: #fff;
      border-right: 1px solid #e4e1d9;
      padding: 1.25rem 0;
      align-self: stretch;
      position: sticky;
      top: 57px;
      height: calc(100vh - 57px);
      overflow-y: auto;
    }
    .tool-sidebar-label {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: #9a9890;
      text-transform: uppercase;
      padding: 0 1.25rem 0.6rem;
    }
    .tool-sidebar-sub {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: #9a9890;
      text-transform: uppercase;
      padding: 0.9rem 1.25rem 0.4rem;
      border-top: 1px solid #f0ede6;
      margin-top: 0.5rem;
    }
    .tool-sidebar a, .tool-sidebar button.sidebar-btn {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0.6rem 1.25rem;
      font-size: 13.5px;
      color: #1d1d1b;
      text-decoration: none;
      border-left: 3px solid transparent;
      transition: background 0.12s;
      width: 100%;
      background: none;
      border-top: none;
      border-right: none;
      border-bottom: none;
      cursor: pointer;
      font-family: inherit;
      text-align: left;
    }
    .tool-sidebar a:hover, .tool-sidebar button.sidebar-btn:hover { background: #f5f4f1; text-decoration: none; }
    .tool-sidebar a.active, .tool-sidebar button.sidebar-btn.active {
      border-left-color: #185fa5;
      background: #eff5ff;
      font-weight: 600;
      color: #185fa5;
    }
    .tool-sidebar .tool-icon { font-size: 16px; width: 20px; text-align: center; flex-shrink: 0; }
    .tool-content {
      flex: 1;
      min-width: 0;
      padding: 2rem 1.5rem 4rem;
      max-width: 960px;
    }
    @media (max-width: 720px) {
      .tool-shell { flex-direction: column; }
      .tool-sidebar {
        width: 100%; height: auto; position: static;
        border-right: none; border-bottom: 1px solid #e4e1d9;
        padding: 0.5rem 0; display: flex; overflow-x: auto;
      }
      .tool-sidebar-label, .tool-sidebar-sub { display: none; }
      .tool-sidebar a, .tool-sidebar button.sidebar-btn {
        flex-shrink: 0; padding: 0.5rem 0.85rem;
        border-left: none; border-bottom: 3px solid transparent; white-space: nowrap;
      }
      .tool-sidebar a.active, .tool-sidebar button.sidebar-btn.active {
        border-left-color: transparent; border-bottom-color: #185fa5;
      }
      .tool-content { padding: 1.25rem 1rem 3rem; max-width: 100%; }
    }
  `;
  document.head.appendChild(s);
})();
