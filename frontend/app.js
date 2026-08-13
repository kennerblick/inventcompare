const API = '/api';
let currentSnapshot = null;
let network = null;

function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (isError ? ' error' : '');
  setTimeout(() => { el.className = 'toast'; }, 3000);
}

async function api(path, opts) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

// ── Navigation ──────────────────────────────────────────────────────────
document.querySelectorAll('.nav-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('view-' + tab.dataset.view).classList.add('active');
    if (tab.dataset.view === 'graph') renderGraph();
    if (tab.dataset.view === 'settings') loadSettings();
  });
});

// ── Sources / Dashboard ─────────────────────────────────────────────────
async function loadSources() {
  const sources = await api('/sources');
  const container = document.getElementById('source-cards');
  container.innerHTML = '';
  for (const s of sources) {
    const dotClass = !s.configured ? 'grey' : s.reachable === true ? 'green' : s.reachable === false ? 'red' : 'yellow';
    const statusText = !s.configured ? 'nicht konfiguriert' : s.reachable === true ? 'erreichbar' : s.reachable === false ? 'nicht erreichbar' : 'unbekannt';
    const card = document.createElement('div');
    card.className = 'source-card';
    card.innerHTML = `
      <h3><span class="dot ${dotClass}"></span> ${s.name}</h3>
      <div class="row"><span>Status</span><span>${statusText}</span></div>
      <div class="row"><span>Geräte</span><span>${s.device_count ?? '–'}</span></div>
      <div class="row"><span>Letzter Sync</span><span>${s.last_sync ? new Date(s.last_sync).toLocaleString('de-DE') : '–'}</span></div>
      ${s.error ? `<div class="row" style="color:var(--red)">${s.error}</div>` : ''}
    `;
    container.appendChild(card);
  }
}

// ── Comparison ───────────────────────────────────────────────────────────
async function loadComparison(showEmptyHint = true) {
  try {
    currentSnapshot = await api('/comparison');
  } catch (e) {
    currentSnapshot = null;
    if (showEmptyHint) toast('Noch kein Sync vorhanden – bitte "Sync jetzt" ausführen.', true);
  }
  updateStatsBar();
  renderTable();
}

function updateStatsBar() {
  const s = currentSnapshot?.summary;
  document.getElementById('stat-total').textContent = s ? s.total : '–';
  document.getElementById('stat-match').textContent = s ? s.match : '–';
  document.getElementById('stat-mismatch').textContent = s ? s.field_mismatch : '–';
  document.getElementById('stat-missing').textContent = s ? s.missing : '–';
  document.getElementById('stat-generated').textContent = currentSnapshot
    ? 'Stand: ' + new Date(currentSnapshot.generated_at).toLocaleString('de-DE')
    : 'Noch kein Sync';
}

function renderTable() {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  if (!currentSnapshot) return;

  const search = document.getElementById('filter-search').value.toLowerCase();
  const statusFilter = document.getElementById('filter-status').value;

  const entries = currentSnapshot.entries.filter(e => {
    if (statusFilter && e.status !== statusFilter) return false;
    if (search && !e.hostname.toLowerCase().includes(search)) return false;
    return true;
  });

  for (const e of entries) {
    const tr = document.createElement('tr');
    const diffHtml = e.diffs.map(d =>
      `<div class="diff-line"><b>${d.field}:</b> ${Object.entries(d.values).map(([k, v]) => `${k}=${v ?? '–'}`).join(' / ')}</div>`
    ).join('');
    tr.innerHTML = `
      <td>${e.hostname}</td>
      <td>${e.present_in.map(s => `<span class="badge badge-source">${s}</span>`).join('')}</td>
      <td>${e.missing_in.map(s => `<span class="badge badge-source">${s}</span>`).join('') || '–'}</td>
      <td><span class="badge badge-${e.status}">${statusLabel(e.status)}</span></td>
      <td>${diffHtml || '–'}</td>
    `;
    tbody.appendChild(tr);
  }
}

function statusLabel(status) {
  return { match: 'Übereinstimmend', field_mismatch: 'Abweichung', missing: 'Fehlend' }[status] || status;
}

document.getElementById('filter-search').addEventListener('input', renderTable);
document.getElementById('filter-status').addEventListener('change', renderTable);

// ── Graph ────────────────────────────────────────────────────────────────
function renderGraph() {
  const container = document.getElementById('network-container');
  if (!currentSnapshot || currentSnapshot.entries.length === 0) {
    container.innerHTML = '<div class="empty-hint">Keine Daten – bitte zunächst einen Sync ausführen.</div>';
    return;
  }

  const nodes = [];
  const edges = [];
  const sourceHubs = new Set();
  currentSnapshot.entries.forEach(e => [...e.present_in].forEach(s => sourceHubs.add(s)));

  for (const hub of sourceHubs) {
    nodes.push({ id: 'hub:' + hub, label: hub, shape: 'box', color: '#4f8ef7', font: { color: '#fff' }, size: 30 });
  }

  const colorFor = { match: '#22c55e', field_mismatch: '#f59e0b', missing: '#ef4444' };

  currentSnapshot.entries.forEach((e, idx) => {
    const nodeId = 'dev:' + idx;
    nodes.push({
      id: nodeId,
      label: e.hostname,
      shape: 'dot',
      size: 10,
      color: colorFor[e.status] || '#8b92a8',
      font: { color: '#e2e5f0', size: 11 },
    });
    for (const source of e.present_in) {
      edges.push({ from: nodeId, to: 'hub:' + source, color: { color: '#2e3347' } });
    }
  });

  const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
  const options = {
    physics: { stabilization: true, barnesHut: { gravitationalConstant: -4000, springLength: 90 } },
    interaction: { hover: true },
  };
  if (network) network.destroy();
  network = new vis.Network(container, data, options);
}

// ── Settings ─────────────────────────────────────────────────────────────
async function loadSettings() {
  const data = await api('/settings');
  const cfg = data.config;
  document.getElementById('set-interval').value = cfg.sync_interval_minutes;
  document.getElementById('set-zabbix-enabled').checked = !!cfg.sources_enabled.zabbix;
  document.getElementById('set-idoit-enabled').checked = !!cfg.sources_enabled.idoit;
  document.getElementById('set-gitlab-enabled').checked = !!cfg.sources_enabled.gitlab;
  document.getElementById('set-ignore-case').checked = !!cfg.matching.ignore_case;
  document.getElementById('set-strip-domain').checked = !!cfg.matching.strip_domain;
  document.getElementById('set-idoit-types').value = (cfg.idoit.object_types || []).join(', ');
  document.getElementById('set-idoit-in-operation').checked = cfg.idoit.only_in_operation !== false;
  document.getElementById('set-zabbix-groups').value = (cfg.zabbix.host_groups || []).join(', ');
  document.getElementById('set-gitlab-paths').value = (cfg.gitlab.group_paths || []).join(', ');
  document.getElementById('set-gitlab-archived').checked = !!cfg.gitlab.include_archived;

  const credEl = document.getElementById('cred-status');
  credEl.innerHTML = Object.entries(data.credentials_configured).map(([name, ok]) =>
    `<div class="cred-status"><span class="dot ${ok ? 'green' : 'red'}"></span> ${name}: ${ok ? 'Zugangsdaten gesetzt' : 'nicht gesetzt (.env prüfen)'}</div>`
  ).join('');
}

document.getElementById('btn-load-idoit-types').addEventListener('click', async () => {
  const listEl = document.getElementById('idoit-types-list');
  listEl.innerHTML = '<div class="empty-hint">Lade Objekttypen…</div>';
  try {
    const types = await api('/sources/idoit/object-types');
    if (types.length === 0) {
      listEl.innerHTML = '<div class="empty-hint">Keine Objekttypen gefunden.</div>';
      return;
    }
    listEl.innerHTML = `<table><thead><tr><th>Titel</th><th>const (bevorzugt)</th><th>ID (falls kein const)</th></tr></thead><tbody>
      ${types.map(t => `<tr><td>${t.title ?? '–'}</td><td>${t.const ? `<code>${t.const}</code>` : '–'}</td><td><code>${t.id ?? '–'}</code></td></tr>`).join('')}
    </tbody></table>
    <div class="empty-hint" style="padding:8px 0 0;">Individuell angelegte Objekttypen haben oft keine eigene "const" – in dem Fall die ID ins Filterfeld eintragen.</div>`;
  } catch (e) {
    listEl.innerHTML = '';
    toast('Fehler beim Laden der Objekttypen: ' + e.message, true);
  }
});

document.getElementById('btn-save-settings').addEventListener('click', async () => {
  const payload = {
    sync_interval_minutes: parseInt(document.getElementById('set-interval').value, 10) || 15,
    sources_enabled: {
      zabbix: document.getElementById('set-zabbix-enabled').checked,
      idoit: document.getElementById('set-idoit-enabled').checked,
      gitlab: document.getElementById('set-gitlab-enabled').checked,
    },
    matching: {
      ignore_case: document.getElementById('set-ignore-case').checked,
      strip_domain: document.getElementById('set-strip-domain').checked,
    },
    idoit: {
      object_types: document.getElementById('set-idoit-types').value.split(',').map(s => s.trim()).filter(Boolean),
      only_in_operation: document.getElementById('set-idoit-in-operation').checked,
    },
    zabbix: {
      host_groups: document.getElementById('set-zabbix-groups').value.split(',').map(s => s.trim()).filter(Boolean),
    },
    gitlab: {
      group_paths: document.getElementById('set-gitlab-paths').value.split(',').map(s => s.trim()).filter(Boolean),
      include_archived: document.getElementById('set-gitlab-archived').checked,
    },
  };
  try {
    await api('/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    toast('Einstellungen gespeichert');
  } catch (e) {
    toast('Fehler: ' + e.message, true);
  }
});

// ── Sync ─────────────────────────────────────────────────────────────────
document.getElementById('btn-sync').addEventListener('click', async () => {
  const btn = document.getElementById('btn-sync');
  btn.disabled = true;
  btn.textContent = 'Sync läuft…';
  try {
    currentSnapshot = await api('/comparison/sync', { method: 'POST' });
    updateStatsBar();
    renderTable();
    if (document.getElementById('view-graph').classList.contains('active')) renderGraph();
    await loadSources();
    toast('Sync abgeschlossen');
  } catch (e) {
    toast('Sync fehlgeschlagen: ' + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sync jetzt';
  }
});

// ── Init ─────────────────────────────────────────────────────────────────
(async function init() {
  await loadSources();
  await loadComparison(false);
})();
