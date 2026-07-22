import './style.css'

// ══════════════════════════════════════════════════════════════════════════════
// State
// ══════════════════════════════════════════════════════════════════════════════
let globalConfig = null;
let editingAreaIdx = -1;  // -1 = new, >=0 = editing
let confirmCallback = null;
let logAutoRefreshTimer = null;
let matchOffset = 0;
const MATCH_PAGE_SIZE = 20;

// ══════════════════════════════════════════════════════════════════════════════
// DOM Refs
// ══════════════════════════════════════════════════════════════════════════════
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const views = {
  feed:     $('#view-feed'),
  areas:    $('#view-areas'),
  settings: $('#view-settings'),
  system:   $('#view-system'),
};

// ══════════════════════════════════════════════════════════════════════════════
// Theme Toggle
// ══════════════════════════════════════════════════════════════════════════════
function initTheme() {
  const saved = localStorage.getItem('telefeed-theme');
  if (saved === 'light') document.body.classList.add('light');
  updateThemeIcons();
}

function toggleTheme() {
  document.body.classList.toggle('light');
  localStorage.setItem('telefeed-theme', document.body.classList.contains('light') ? 'light' : 'dark');
  updateThemeIcons();
}

function updateThemeIcons() {
  const isLight = document.body.classList.contains('light');
  $('#icon-moon').classList.toggle('hidden', isLight);
  $('#icon-sun').classList.toggle('hidden', !isLight);
}

$('#btn-theme').addEventListener('click', toggleTheme);
initTheme();

// ══════════════════════════════════════════════════════════════════════════════
// Navigation
// ══════════════════════════════════════════════════════════════════════════════
$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.view;
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    Object.entries(views).forEach(([k, v]) => v.classList.toggle('hidden', k !== target));
  });
});

// ══════════════════════════════════════════════════════════════════════════════
// Toast Notifications
// ══════════════════════════════════════════════════════════════════════════════
function showToast(message, type = 'success') {
  const container = $('#toast-container');
  const el = document.createElement('div');
  const color = type === 'error'
    ? 'bg-red-500/10 border-red-500/40 text-red-200'
    : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200';
  el.className = `px-4 py-3 rounded-lg border backdrop-blur-md shadow-lg text-sm transition-all duration-300 translate-y-8 opacity-0 ${color}`;
  el.innerText = message;
  container.appendChild(el);
  requestAnimationFrame(() => el.classList.remove('translate-y-8', 'opacity-0'));
  setTimeout(() => { el.classList.add('opacity-0', 'scale-95'); setTimeout(() => el.remove(), 300); }, 4000);
}

// ══════════════════════════════════════════════════════════════════════════════
// Confirm Modal
// ══════════════════════════════════════════════════════════════════════════════
function showConfirm(msg, callback) {
  $('#confirm-msg').innerText = msg;
  confirmCallback = callback;
  $('#confirm-modal').classList.add('open');
}

$('#btn-confirm-yes').addEventListener('click', () => {
  $('#confirm-modal').classList.remove('open');
  if (confirmCallback) confirmCallback();
  confirmCallback = null;
});

$('#btn-confirm-no').addEventListener('click', () => {
  $('#confirm-modal').classList.remove('open');
  confirmCallback = null;
});

// ══════════════════════════════════════════════════════════════════════════════
// API helpers
// ══════════════════════════════════════════════════════════════════════════════
async function api(url, opts = {}) {
  try {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed (${res.status})`);
    }
    return res.json();
  } catch (err) {
    showToast(err.message, 'error');
    throw err;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Service Status
// ══════════════════════════════════════════════════════════════════════════════
let isServiceRunning = false;

async function pollServiceStatus() {
  try {
    const data = await fetch('/api/service/status').then(r => r.json());
    isServiceRunning = data.running;
  } catch { isServiceRunning = false; }
  updateServiceUI();
}

function updateServiceUI() {
  const indicator = $('#service-indicator');
  const label = $('#service-label');
  const btn = $('#btn-toggle-service');
  if (isServiceRunning) {
    indicator.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)] transition-colors';
    label.innerText = 'Running';
    label.className = 'text-emerald-400';
    btn.innerText = 'Stop';
    btn.className = 'text-xs px-3 py-1.5 bg-red-600/80 hover:bg-red-500 text-white rounded transition-colors font-medium cursor-pointer';
  } else {
    indicator.className = 'w-2.5 h-2.5 rounded-full bg-slate-500 transition-colors';
    label.innerText = 'Stopped';
    label.className = 'text-slate-400';
    btn.innerText = 'Start';
    btn.className = 'text-xs px-3 py-1.5 bg-blue-600/90 hover:bg-blue-500 text-white rounded transition-colors font-medium cursor-pointer';
  }
}

$('#btn-toggle-service').addEventListener('click', async () => {
  const action = isServiceRunning ? 'stop' : 'start';
  const btn = $('#btn-toggle-service');
  btn.disabled = true; btn.innerText = '...';
  try {
    await api(`/api/service/${action}`, { method: 'POST' });
    showToast(`Service ${action}ed.`);
    setTimeout(pollServiceStatus, 1500);
  } catch {} finally { btn.disabled = false; }
});

// Poll service status every 30s
pollServiceStatus();
setInterval(pollServiceStatus, 30000);

// ══════════════════════════════════════════════════════════════════════════════
// Config
// ══════════════════════════════════════════════════════════════════════════════
async function loadConfig() {
  try {
    globalConfig = await fetch('/api/config').then(r => r.json());
    if (!globalConfig || Object.keys(globalConfig).length === 0) globalConfig = {};
    renderSettings();
    renderAreas();
    populateAreaFilter();
    checkAuthStatus();
  } catch (err) {
    showToast('Failed to load config.', 'error');
  }
}

async function saveConfig() {
  try {
    await api('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(globalConfig),
    });
    
    const { running } = await api('/api/service/status');
    if (running) {
      showConfirm('Configuration saved! The background service is currently running. Would you like to restart it to apply the new settings?', async () => {
        try {
          await api('/api/service/restart', { method: 'POST' });
          showToast('Service restarted successfully.');
          setTimeout(pollServiceStatus, 1500);
        } catch {
          showToast('Failed to restart service.', 'error');
        }
      });
    } else {
      showToast('Configuration saved!');
    }
  } catch {}
}

// ══════════════════════════════════════════════════════════════════════════════
// Telegram Auth
// ══════════════════════════════════════════════════════════════════════════════
async function checkAuthStatus() {
  try {
    const res = await api('/api/auth/status');
    updateAuthUI(res);
  } catch {
    updateAuthUI({ authenticated: false });
  }
}

function updateAuthUI(state) {
  const badge = $('#auth-status-badge');
  const msg = $('#auth-status-msg');
  const stepSend = $('#auth-step-send');
  const stepCode = $('#auth-step-code');
  const step2fa = $('#auth-step-2fa');
  const stepDone = $('#auth-step-done');

  stepSend?.classList.add('hidden');
  stepCode?.classList.add('hidden');
  step2fa?.classList.add('hidden');
  stepDone?.classList.add('hidden');

  if (state.authenticated) {
    if(badge) {
      badge.innerText = 'Authenticated';
      badge.className = 'text-[10px] px-2 py-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400';
    }
    if(msg) msg.innerText = '';
    const userEl = $('#auth-user-name');
    if(userEl) userEl.innerText = state.user;
    stepDone?.classList.remove('hidden');
  } else {
    if(badge) {
      badge.innerText = 'Not Authenticated';
      badge.className = 'text-[10px] px-2 py-0.5 rounded-full border border-slate-700 text-slate-500';
    }
    if(msg) msg.innerText = state.error || 'You must authenticate to use TeleFeed.';
    stepSend?.classList.remove('hidden');
  }
}

$('#btn-auth-send')?.addEventListener('click', async () => {
  const btn = $('#btn-auth-send');
  btn.disabled = true; btn.innerText = 'Sending...';
  try {
    const res = await api('/api/auth/start', { method: 'POST' });
    if (res.status === 'already_authorized') {
      updateAuthUI({ authenticated: true, user: res.user });
    } else {
      $('#auth-step-send').classList.add('hidden');
      $('#auth-step-code').classList.remove('hidden');
      $('#auth-code-input').focus();
    }
  } catch (err) {
    showToast(err.message || 'Failed to send code', 'error');
  } finally {
    btn.disabled = false; btn.innerText = 'Send Login Code';
  }
});

$('#btn-auth-verify')?.addEventListener('click', async () => {
  const code = $('#auth-code-input').value.trim();
  if (!code) return;
  const btn = $('#btn-auth-verify');
  btn.disabled = true; btn.innerText = '...';
  try {
    const res = await api('/api/auth/verify', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({code}) });
    if (res.status === '2fa_required') {
      $('#auth-step-code').classList.add('hidden');
      $('#auth-step-2fa').classList.remove('hidden');
      $('#auth-2fa-input').focus();
    } else {
      updateAuthUI({ authenticated: true, user: res.user });
    }
  } catch (err) {
    showToast(err.message || 'Verification failed', 'error');
  } finally {
    btn.disabled = false; btn.innerText = 'Verify';
  }
});

$('#btn-auth-2fa')?.addEventListener('click', async () => {
  const password = $('#auth-2fa-input').value.trim();
  if (!password) return;
  const btn = $('#btn-auth-2fa');
  btn.disabled = true; btn.innerText = '...';
  try {
    const res = await api('/api/auth/2fa', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({password}) });
    updateAuthUI({ authenticated: true, user: res.user });
  } catch (err) {
    showToast(err.message || '2FA failed', 'error');
  } finally {
    btn.disabled = false; btn.innerText = 'Submit';
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// Settings View
// ══════════════════════════════════════════════════════════════════════════════
function renderSettings() {
  if (!globalConfig) return;
  const c = globalConfig;

  // Matcher
  $('#cfg-matcher').value = c.matcher || 'keywords';
  $('#cfg-threshold').value = c.ai_threshold ?? 65;
  $('#cfg-threshold-val').innerText = c.ai_threshold ?? 65;

  // Telegram
  const tg = c.telegram || {};
  $('#cfg-api-id').value = tg.api_id || '';
  $('#cfg-api-hash').value = tg.api_hash || '';
  $('#cfg-phone').value = tg.phone || '';

  // AI
  const ai = c.ai || {};
  $('#cfg-ai-provider').value = ai.provider || 'gemini';
  $('#cfg-ai-model').value = ai.model || '';
  $('#cfg-ai-key').value = ai.api_key || '';
  $('#cfg-ai-base-url').value = ai.base_url || '';

  // Notifications
  const notif = c.notifications || {};
  const bot = notif.telegram_bot || {};
  $('#cfg-desktop').checked = notif.desktop !== false;
  $('#cfg-bot-enabled').checked = !!bot.enabled;
  $('#cfg-bot-token').value = bot.bot_token || '';
  $('#cfg-bot-chatid').value = bot.chat_id || '';
}

$('#cfg-threshold').addEventListener('input', (e) => {
  $('#cfg-threshold-val').innerText = e.target.value;
});

$('#btn-save-settings').addEventListener('click', () => {
  if (!globalConfig) globalConfig = {};

  globalConfig.matcher = $('#cfg-matcher').value;
  globalConfig.ai_threshold = parseInt($('#cfg-threshold').value, 10);

  globalConfig.telegram = {
    api_id: parseInt($('#cfg-api-id').value, 10) || 0,
    api_hash: $('#cfg-api-hash').value,
    phone: $('#cfg-phone').value,
  };

  globalConfig.ai = {
    provider: $('#cfg-ai-provider').value,
    model: $('#cfg-ai-model').value,
    api_key: $('#cfg-ai-key').value,
    base_url: $('#cfg-ai-base-url').value,
  };

  globalConfig.notifications = {
    desktop: $('#cfg-desktop').checked,
    telegram_bot: {
      enabled: $('#cfg-bot-enabled').checked,
      bot_token: $('#cfg-bot-token').value,
      chat_id: $('#cfg-bot-chatid').value,
    },
  };

  saveConfig();
});

$('#btn-test-notif')?.addEventListener('click', async () => {
  const btn = $('#btn-test-notif');
  btn.disabled = true; btn.innerText = 'Sending...';
  try {
    await api('/api/notifications/test', { method: 'POST' });
    showToast('Test notification sent!');
  } catch (err) {
    showToast(err.message || 'Failed to send test notification', 'error');
  } finally {
    btn.disabled = false; btn.innerText = '🔔 Send Test Notification';
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// Areas View
// ══════════════════════════════════════════════════════════════════════════════
function renderAreas() {
  const container = $('#areas-container');
  container.innerHTML = '';
  const areas = globalConfig?.areas || [];

  if (areas.length === 0) {
    container.innerHTML = `<div class="col-span-full glass-panel p-8 text-center text-slate-500 italic text-sm">No areas configured. Click "Add Area" to create your first one.</div>`;
    return;
  }

  areas.forEach((area, idx) => {
    const el = document.createElement('div');
    el.className = 'glass-panel p-5 relative group hover:border-slate-600 transition-colors';

    const kwHtml = (area.keywords || []).map(k => `<span class="badge badge-blue">${esc(k)}</span>`).join('');
    const negKwHtml = (area.negative_keywords || []).map(k => `<span class="badge badge-red">${esc(k)}</span>`).join('');
    const srcHtml = (area.sources || []).map(s => `<span class="badge badge-gray">${esc(s)}</span>`).join('');

    el.innerHTML = `
      <div class="flex justify-between items-start mb-2">
        <h3 class="font-bold text-base">${esc(area.name)}</h3>
        <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="btn-area-edit btn-icon" data-idx="${idx}" title="Edit">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
          </button>
          <button class="btn-area-del btn-icon" data-idx="${idx}" title="Delete">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
          </button>
        </div>
      </div>
      <p class="text-xs text-slate-400 mb-3 line-clamp-2">${esc(area.description || '')}</p>
      ${kwHtml ? `<div class="mb-2"><span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mr-2">Keywords</span><div class="flex flex-wrap gap-1 mt-1">${kwHtml}</div></div>` : ''}
      ${negKwHtml ? `<div class="mb-2"><span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mr-2">Negative</span><div class="flex flex-wrap gap-1 mt-1">${negKwHtml}</div></div>` : ''}
      ${srcHtml ? `<div><span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest mr-2">Sources</span><div class="flex flex-wrap gap-1 mt-1">${srcHtml}</div></div>` : `<div class="text-[10px] text-slate-500 italic">Watching all subscribed channels</div>`}
    `;
    container.appendChild(el);
  });

  // Bind edit/delete
  $$('.btn-area-edit').forEach(btn => btn.addEventListener('click', () => openAreaModal(parseInt(btn.dataset.idx, 10))));
  $$('.btn-area-del').forEach(btn => btn.addEventListener('click', () => {
    const idx = parseInt(btn.dataset.idx, 10);
    showConfirm(`Delete area "${globalConfig.areas[idx].name}"?`, () => {
      globalConfig.areas.splice(idx, 1);
      renderAreas();
      populateAreaFilter();
      saveConfig();
    });
  }));
}

// ── Area Modal ──
function openAreaModal(idx = -1) {
  editingAreaIdx = idx;
  const modal = $('#area-modal');
  const area = idx >= 0 ? globalConfig.areas[idx] : null;

  $('#area-modal-title').innerText = area ? 'Edit Area' : 'New Area';
  $('#area-name').value = area?.name || '';
  $('#area-desc').value = area?.description || '';
  $('#area-kw').value = (area?.keywords || []).join(', ');
  $('#area-neg-kw').value = (area?.negative_keywords || []).join(', ');
  $('#area-sources').value = (area?.sources || []).join(', ');

  modal.classList.add('open');
  modal.querySelector('.glass-panel').classList.remove('scale-95');
  setTimeout(() => $('#area-name').focus(), 100);
}

function closeAreaModal() {
  const modal = $('#area-modal');
  modal.querySelector('.glass-panel').classList.add('scale-95');
  modal.classList.remove('open');
  editingAreaIdx = -1;
}

$('#btn-add-area').addEventListener('click', () => openAreaModal(-1));
$('#btn-close-modal').addEventListener('click', closeAreaModal);
$('#btn-cancel-area').addEventListener('click', closeAreaModal);

$('#btn-save-area').addEventListener('click', () => {
  const name = $('#area-name').value.trim();
  if (!name) { showToast('Area name is required.', 'error'); return; }

  const parseTags = (v) => v.split(',').map(s => s.trim()).filter(Boolean);

  const area = {
    name,
    description: $('#area-desc').value.trim(),
    keywords: parseTags($('#area-kw').value),
    negative_keywords: parseTags($('#area-neg-kw').value),
    sources: parseTags($('#area-sources').value),
  };

  if (!globalConfig.areas) globalConfig.areas = [];

  if (editingAreaIdx >= 0) {
    globalConfig.areas[editingAreaIdx] = area;
  } else {
    globalConfig.areas.push(area);
  }

  closeAreaModal();
  renderAreas();
  populateAreaFilter();
  saveConfig();
});

// ══════════════════════════════════════════════════════════════════════════════
// Live Feed & WebSocket
// ══════════════════════════════════════════════════════════════════════════════
function updateWsStatus(status, text) {
  const el = $('#ws-status');
  const dot = status === 'connected' ? 'bg-emerald-400 animate-pulse' : status === 'disconnected' ? 'bg-red-500' : 'bg-amber-400 animate-pulse';
  const color = status === 'connected' ? 'text-emerald-400' : status === 'disconnected' ? 'text-red-500' : 'text-amber-400';
  el.innerHTML = `<span class="w-2 h-2 rounded-full ${dot}"></span><span class="${color}">${text}</span>`;
}

function renderMatchCard(match, prepend = true) {
  const placeholder = $('#feed-placeholder');
  if (placeholder) placeholder.remove();

  const el = document.createElement('div');
  el.className = 'glass-panel p-4 transition-all duration-300 hover:border-slate-600';
  if (prepend) el.classList.add('opacity-0', '-translate-x-3');

  const score = match.score != null ? Math.round(match.score) : null;
  let scoreColor = 'text-blue-400';
  if (score !== null) {
    if (score >= 85) scoreColor = 'text-emerald-400';
    else if (score < 50) scoreColor = 'text-slate-400';
  }

  const safeUrl = match.url && match.url !== 'null' ? match.url : null;
  const timeStr = match.matched_at ? new Date(match.matched_at).toLocaleString() : '';

  // Status badge
  const statusBadge = match.status === 'saved'
    ? '<span class="badge badge-green">Saved</span>'
    : match.status === 'archived'
      ? '<span class="badge badge-gray">Archived</span>'
      : '<span class="badge badge-blue">New</span>';

  el.innerHTML = `
    <div class="flex flex-wrap justify-between items-start gap-2 mb-2">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="badge badge-gray">${esc(match.area)}</span>
        <span class="text-xs text-slate-400">from <span class="font-medium">${esc(match.channel)}</span></span>
        <span class="text-[10px] text-slate-600">${timeStr}</span>
      </div>
      <div class="flex items-center gap-2">
        ${statusBadge}
        ${score !== null ? `<span class="font-mono font-bold text-sm ${scoreColor}">${score}</span>` : ''}
      </div>
    </div>
    <div class="text-sm leading-relaxed line-clamp-3 hover:line-clamp-none transition-all whitespace-pre-wrap mb-3">${esc(match.text)}</div>
    ${match.ai_reason ? `
      <div class="p-2.5 bg-slate-900/40 rounded-lg border border-slate-800/50 mb-3">
        <div class="flex items-center gap-1.5 mb-1">
          <svg class="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
          <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">AI Reasoning</span>
        </div>
        <p class="text-xs text-slate-300 italic">${esc(match.ai_reason)}</p>
      </div>` : ''}
    <div class="flex items-center justify-between pt-2 border-t border-slate-800/40">
      <div class="flex gap-1.5">
        <button class="btn-match-status text-[10px] px-2 py-1 rounded border transition-colors ${match.status === 'saved' ? 'border-emerald-500/30 text-emerald-400' : 'border-slate-700 text-slate-500 hover:text-emerald-400 hover:border-emerald-500/30'}" data-id="${match.id}" data-status="saved" title="Save">★ Save</button>
        <button class="btn-match-status text-[10px] px-2 py-1 rounded border transition-colors ${match.status === 'archived' ? 'border-slate-500/30 text-slate-300' : 'border-slate-700 text-slate-500 hover:text-slate-300 hover:border-slate-500/30'}" data-id="${match.id}" data-status="archived" title="Archive">✓ Archive</button>
      </div>
      ${safeUrl ? `<a href="${safeUrl}" target="_blank" rel="noopener" class="text-[11px] text-blue-400 hover:text-blue-300 flex items-center gap-1 transition-colors">Open in Telegram <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg></a>` : ''}
    </div>
  `;

  if (prepend) {
    $('#feed-container').insertBefore(el, $('#feed-container').firstChild);
    requestAnimationFrame(() => el.classList.remove('opacity-0', '-translate-x-3'));
  } else {
    $('#feed-container').appendChild(el);
  }

  // Bind status buttons
  el.querySelectorAll('.btn-match-status').forEach(b => b.addEventListener('click', async () => {
    try {
      await api(`/api/matches/${b.dataset.id}/status?new_status=${b.dataset.status}`, { method: 'POST' });
      showToast(`Match ${b.dataset.status}.`);
      // Reload
      await loadMatches();
    } catch {}
  }));
}

async function loadMatches(append = false) {
  if (!append) matchOffset = 0;
  const area = $('#filter-area').value;
  const status = $('#filter-status').value;
  let url = `/api/matches?limit=${MATCH_PAGE_SIZE}&offset=${matchOffset}`;
  if (area) url += `&area=${encodeURIComponent(area)}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;

  try {
    const matches = await fetch(url).then(r => r.json());

    if (!append) {
      $('#feed-container').innerHTML = '';
    }

    if (matches.length === 0 && matchOffset === 0) {
      $('#feed-container').innerHTML = `<div id="feed-placeholder" class="glass-panel p-10 text-center text-slate-500 italic text-sm">No matches found.</div>`;
      $('#btn-load-more').classList.add('hidden');
      return;
    }

    // Render oldest first so newest ends at top
    const ordered = [...matches].reverse();
    ordered.forEach(m => renderMatchCard(m, !append));

    // Show/hide load more
    if (matches.length >= MATCH_PAGE_SIZE) {
      matchOffset += matches.length;
      $('#btn-load-more').classList.remove('hidden');
    } else {
      $('#btn-load-more').classList.add('hidden');
    }
  } catch {}
}

$('#btn-load-more').addEventListener('click', () => loadMatches(true));
$('#filter-area').addEventListener('change', () => loadMatches());
$('#filter-status').addEventListener('change', () => loadMatches());

function populateAreaFilter() {
  const sel = $('#filter-area');
  const val = sel.value;
  sel.innerHTML = '<option value="">All Areas</option>';
  (globalConfig?.areas || []).forEach(a => {
    sel.innerHTML += `<option value="${esc(a.name)}">${esc(a.name)}</option>`;
  });
  sel.value = val;
}

function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${location.host}/api/live`);

  ws.onopen = () => updateWsStatus('connected', 'Live');
  ws.onmessage = (e) => {
    try { renderMatchCard(JSON.parse(e.data), true); } catch {}
  };
  ws.onclose = () => {
    updateWsStatus('disconnected', 'Reconnecting...');
    setTimeout(connectWebSocket, 5000);
  };
  ws.onerror = () => {};
}

// ══════════════════════════════════════════════════════════════════════════════
// System Tools
// ══════════════════════════════════════════════════════════════════════════════
async function actionService(action) {
  try {
    await api(`/api/service/${action}`, { method: 'POST' });
    showToast(`Service ${action} completed.`);
    setTimeout(pollServiceStatus, 1500);
    setTimeout(loadLogs, 2000);
  } catch {}
}

$('#btn-svc-install')?.addEventListener('click', () => showConfirm('Install the TeleFeed background service?', () => actionService('install')));
$('#btn-svc-uninstall')?.addEventListener('click', () => showConfirm('Uninstall the TeleFeed background service?', () => actionService('uninstall')));
$('#btn-svc-restart')?.addEventListener('click', () => actionService('restart'));

$('#btn-fetch')?.addEventListener('click', async () => {
  const limit = $('#fetch-limit').value || 50;
  const btn = $('#btn-fetch');
  btn.innerText = 'Running...'; btn.disabled = true;
  try {
    await api(`/api/fetch?limit=${limit}`, { method: 'POST' });
    showToast(`Fetch started (${limit} msgs/channel).`);
  } catch {} finally { btn.innerText = 'Run Fetch'; btn.disabled = false; }
});

// ── Logs ──
async function loadLogs() {
  const container = $('#logs-container');
  if (!container) return;
  try {
    const data = await fetch('/api/service/logs').then(r => r.json());
    if (data.logs?.length > 0) {
      container.innerHTML = data.logs.map(l => `<div>${esc(l)}</div>`).join('');
      container.scrollTop = container.scrollHeight;
    } else {
      container.innerHTML = '<span class="text-slate-500 italic">No logs found.</span>';
    }
  } catch { container.innerHTML = '<span class="text-red-400">Failed to load logs.</span>'; }
}

$('#btn-refresh-logs')?.addEventListener('click', loadLogs);

// Auto-refresh toggle
$('#log-auto-refresh')?.addEventListener('change', (e) => {
  if (e.target.checked) {
    loadLogs();
    logAutoRefreshTimer = setInterval(loadLogs, 5000);
  } else {
    clearInterval(logAutoRefreshTimer);
    logAutoRefreshTimer = null;
  }
});

// Load logs when switching to system tab
$('[data-view="system"]')?.addEventListener('click', loadLogs);

// ── Diagnostics ──
$('#btn-run-doctor')?.addEventListener('click', async () => {
  const container = $('#doctor-container');
  container.innerHTML = '<span class="text-slate-500 italic text-sm">Running diagnostics...</span>';
  try {
    const data = await api('/api/doctor');
    container.innerHTML = data.checks.map(c => `
      <div class="flex items-center gap-2 text-sm py-1.5 px-2 rounded ${c.ok ? '' : 'bg-red-500/5'}">
        <span class="${c.ok ? 'text-emerald-400' : 'text-red-400'} text-base">${c.ok ? '✓' : '✗'}</span>
        <span class="font-medium w-40 flex-shrink-0">${esc(c.label)}</span>
        <span class="text-slate-400 text-xs truncate">${esc(c.value)}</span>
      </div>
    `).join('');
  } catch { container.innerHTML = '<span class="text-red-400 text-sm">Diagnostics failed.</span>'; }
});

// ══════════════════════════════════════════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════════════════════════════════════════
function esc(str) {
  if (!str) return '';
  const d = document.createElement('div');
  d.innerText = String(str);
  return d.innerHTML;
}

// ══════════════════════════════════════════════════════════════════════════════
// Boot
// ══════════════════════════════════════════════════════════════════════════════
loadConfig();
loadMatches();
connectWebSocket();
