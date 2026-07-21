import './style.css'

// ──────────────────────────────────────────────────────────────────────────────
// State & DOM Elements
// ──────────────────────────────────────────────────────────────────────────────
let globalConfig = null;

// Views
const views = {
  feed: document.getElementById('view-feed'),
  areas: document.getElementById('view-areas'),
  settings: document.getElementById('view-settings'),
  system: document.getElementById('view-system')
};
const navBtns = document.querySelectorAll('.nav-btn');

// Feed Elements
const feedContainer = document.getElementById('feed-container');
const wsStatus = document.getElementById('ws-status');
let oldestMatchId = Infinity;

// Service Elements
const serviceIndicator = document.getElementById('service-indicator');
const serviceLabel = document.getElementById('service-label');
const btnToggleService = document.getElementById('btn-toggle-service');
let isServiceRunning = false;

// ──────────────────────────────────────────────────────────────────────────────
// Navigation
// ──────────────────────────────────────────────────────────────────────────────
navBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    const target = btn.dataset.view;
    
    // Update active class
    navBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // Switch views
    Object.keys(views).forEach(v => {
      if (v === target) {
        views[v].classList.remove('hidden');
      } else {
        views[v].classList.add('hidden');
      }
    });
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// Toast Notifications
// ──────────────────────────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  
  const bgClass = type === 'error' ? 'bg-red-500/10 border-red-500/50 text-red-200' : 'bg-emerald-500/10 border-emerald-500/50 text-emerald-200';
  
  toast.className = `px-4 py-3 rounded-lg border backdrop-blur-md shadow-lg transform transition-all duration-300 translate-y-10 opacity-0 ${bgClass}`;
  toast.innerText = message;
  
  container.appendChild(toast);
  
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-10', 'opacity-0');
  });
  
  setTimeout(() => {
    toast.classList.add('opacity-0', 'scale-95');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ──────────────────────────────────────────────────────────────────────────────
// API: Service Control
// ──────────────────────────────────────────────────────────────────────────────
async function toggleService() {
  const action = isServiceRunning ? 'stop' : 'start';
  btnToggleService.disabled = true;
  btnToggleService.innerText = 'Working...';
  
  try {
    const res = await fetch(`/api/service/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error("Failed to toggle service");
    
    isServiceRunning = action === 'start';
    updateServiceUI();
    showToast(`Service ${action}ed successfully.`);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btnToggleService.disabled = false;
  }
}

function updateServiceUI() {
  if (isServiceRunning) {
    serviceIndicator.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]';
    serviceLabel.innerText = 'Running';
    serviceLabel.className = 'text-emerald-400';
    btnToggleService.innerText = 'Stop';
    btnToggleService.classList.replace('bg-blue-600/90', 'bg-red-600/80');
    btnToggleService.classList.replace('hover:bg-blue-500', 'hover:bg-red-500');
  } else {
    serviceIndicator.className = 'w-2.5 h-2.5 rounded-full bg-slate-500';
    serviceLabel.innerText = 'Stopped';
    serviceLabel.className = 'text-slate-400';
    btnToggleService.innerText = 'Start';
    btnToggleService.classList.replace('bg-red-600/80', 'bg-blue-600/90');
    btnToggleService.classList.replace('hover:bg-red-500', 'hover:bg-blue-500');
  }
}

btnToggleService.addEventListener('click', toggleService);

// ──────────────────────────────────────────────────────────────────────────────
// API: Config Management
// ──────────────────────────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    globalConfig = await res.json();
    renderSettings();
    renderAreas();
  } catch (err) {
    showToast("Failed to load configuration", "error");
  }
}

async function saveConfig() {
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(globalConfig)
    });
    if (!res.ok) throw new Error("Failed to save");
    showToast("Configuration saved!");
  } catch (err) {
    showToast("Failed to save configuration", "error");
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Settings View
// ──────────────────────────────────────────────────────────────────────────────
function renderSettings() {
  if (!globalConfig) return;
  
  if (!globalConfig.telegram) globalConfig.telegram = {};
  if (!globalConfig.ai) globalConfig.ai = {};
  
  document.getElementById('cfg-api-id').value = globalConfig.telegram.api_id || '';
  document.getElementById('cfg-api-hash').value = globalConfig.telegram.api_hash || '';
  document.getElementById('cfg-phone').value = globalConfig.telegram.phone || '';
  
  document.getElementById('cfg-ai-provider').value = globalConfig.ai.provider || 'gemini';
  document.getElementById('cfg-ai-model').value = globalConfig.ai.model || 'gemini-2.5-flash';
  document.getElementById('cfg-ai-key').value = globalConfig.ai.api_key || '';
  document.getElementById('cfg-ai-base-url').value = globalConfig.ai.base_url || '';
}

document.getElementById('btn-save-settings').addEventListener('click', () => {
  globalConfig.telegram.api_id = parseInt(document.getElementById('cfg-api-id').value, 10) || 0;
  globalConfig.telegram.api_hash = document.getElementById('cfg-api-hash').value;
  globalConfig.telegram.phone = document.getElementById('cfg-phone').value;
  
  globalConfig.ai.provider = document.getElementById('cfg-ai-provider').value;
  globalConfig.ai.model = document.getElementById('cfg-ai-model').value;
  globalConfig.ai.api_key = document.getElementById('cfg-ai-key').value;
  globalConfig.ai.base_url = document.getElementById('cfg-ai-base-url').value;
  
  saveConfig();
});

// ──────────────────────────────────────────────────────────────────────────────
// Areas View
// ──────────────────────────────────────────────────────────────────────────────
function renderAreas() {
  const container = document.getElementById('areas-container');
  container.innerHTML = '';
  
  if (!globalConfig || !globalConfig.areas || globalConfig.areas.length === 0) {
    container.innerHTML = `<div class="col-span-full p-8 text-center text-slate-500 italic glass-panel">No areas configured yet.</div>`;
    return;
  }
  
  globalConfig.areas.forEach((area, index) => {
    const el = document.createElement('div');
    el.className = 'glass-panel p-5 relative group';
    
    // Keywords badging
    const kwHtml = (area.keywords || []).map(k => `<span class="px-2 py-0.5 bg-blue-500/20 text-blue-300 rounded border border-blue-500/30 text-xs">${k}</span>`).join('');
    const negKwHtml = (area.negative_keywords || []).map(k => `<span class="px-2 py-0.5 bg-red-500/20 text-red-300 rounded border border-red-500/30 text-xs">${k}</span>`).join('');
    
    el.innerHTML = `
      <div class="flex justify-between items-start mb-2">
        <h3 class="font-bold text-lg text-slate-200">${area.name}</h3>
        <button class="btn-del-area text-slate-500 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100" data-idx="${index}">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
        </button>
      </div>
      <p class="text-sm text-slate-400 mb-4 line-clamp-2">${area.description}</p>
      
      <div class="space-y-3">
        <div>
          <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Sources</span>
          <div class="flex flex-wrap gap-1.5">
            ${(area.sources || []).map(s => `<span class="text-xs text-slate-300 bg-slate-800 px-1.5 py-0.5 rounded">${s}</span>`).join('') || '<span class="text-xs text-slate-500">All subscribed channels</span>'}
          </div>
        </div>
        
        ${kwHtml ? `<div>
          <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Required Keywords</span>
          <div class="flex flex-wrap gap-1.5">${kwHtml}</div>
        </div>` : ''}
        
        ${negKwHtml ? `<div>
          <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider block mb-1.5">Negative Keywords</span>
          <div class="flex flex-wrap gap-1.5">${negKwHtml}</div>
        </div>` : ''}
      </div>
    `;
    container.appendChild(el);
  });
  
  // Bind delete buttons
  document.querySelectorAll('.btn-del-area').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.dataset.idx, 10);
      globalConfig.areas.splice(idx, 1);
      renderAreas();
      saveConfig();
    });
  });
}

document.getElementById('btn-add-area').addEventListener('click', () => {
  if (!globalConfig.areas) globalConfig.areas = [];
  const name = prompt("Enter a name for the new Area of Concern:");
  if (!name) return;
  
  const desc = prompt("Enter a description to guide the AI for this area:");
  
  globalConfig.areas.push({
    name: name,
    description: desc || "",
    sources: [],
    keywords: [],
    negative_keywords: []
  });
  
  renderAreas();
  saveConfig();
});


// ──────────────────────────────────────────────────────────────────────────────
// Live Feed & Websocket
// ──────────────────────────────────────────────────────────────────────────────
function updateWsStatus(status, text) {
  if (status === 'connected') {
    wsStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span><span class="text-emerald-400">${text}</span>`;
  } else if (status === 'disconnected') {
    wsStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-red-500"></span><span class="text-red-500">${text}</span>`;
  } else {
    wsStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span><span class="text-amber-400">${text}</span>`;
  }
}

function renderMatchCard(match, prepend = true) {
  const placeholder = document.getElementById('feed-placeholder');
  if (placeholder) placeholder.remove();

  const el = document.createElement('div');
  el.className = 'glass-panel p-5 transform transition-all duration-500 hover:border-slate-600';
  
  if (prepend) {
    el.classList.add('opacity-0', '-translate-x-4');
  }
  
  let scoreColor = 'text-blue-400';
  if (match.score >= 85) scoreColor = 'text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.4)]';
  else if (match.score < 50) scoreColor = 'text-slate-400';

  el.innerHTML = `
    <div class="flex justify-between items-start mb-3">
      <div class="flex items-center gap-3">
        <span class="px-2 py-1 bg-slate-800 rounded text-xs font-semibold text-slate-300 border border-slate-700">${match.area}</span>
        <span class="text-sm font-medium text-slate-400">from <span class="text-slate-200">${match.channel}</span></span>
        <span class="text-xs text-slate-600">&bull;</span>
        <span class="text-xs text-slate-500">${new Date(match.matched_at).toLocaleTimeString()}</span>
      </div>
      <div class="flex items-center gap-2 bg-slate-900/50 px-3 py-1 rounded-full border border-slate-800">
        <span class="text-xs font-semibold text-slate-400">AI SCORE</span>
        <span class="font-mono font-bold ${scoreColor}">${match.score != null ? Math.round(match.score) : 'N/A'}</span>
      </div>
    </div>
    
    <div class="text-sm text-slate-300 whitespace-pre-wrap font-sans leading-relaxed line-clamp-4 hover:line-clamp-none transition-all">
      ${match.text}
    </div>
    
    ${match.ai_reason ? `
    <div class="mt-4 flex flex-col gap-2 p-3 bg-slate-900/40 rounded-lg border border-slate-800/50">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
        <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">AI Reasoning</span>
      </div>
      <p class="text-sm text-slate-300 italic">${match.ai_reason}</p>
    </div>` : ''}
    
    <div class="mt-4 flex justify-end gap-3 pt-4 border-t border-slate-800/50">
      <a href="${match.url}" target="_blank" class="px-4 py-1.5 bg-blue-600/10 hover:bg-blue-600/20 text-sm font-medium text-blue-400 rounded transition-colors border border-blue-500/20 hover:border-blue-500/40 flex items-center gap-2">
        Open in Telegram
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
      </a>
    </div>
  `;

  if (prepend) {
    feedContainer.insertBefore(el, feedContainer.firstChild);
    requestAnimationFrame(() => {
      el.classList.remove('opacity-0', '-translate-x-4');
    });
  } else {
    feedContainer.appendChild(el);
  }
}

async function loadHistoricalMatches() {
  try {
    const res = await fetch('/api/matches?limit=20');
    const matches = await res.json();
    matches.reverse().forEach(m => renderMatchCard(m, true));
  } catch(e) {
    console.error("Failed to load history");
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Use current host so it works when served by FastAPI
  const ws = new WebSocket(`${protocol}//${window.location.host}/api/live`);
  
  ws.onopen = () => {
    updateWsStatus('connected', 'Live');
  };
  
  ws.onmessage = (event) => {
    try {
      const match = JSON.parse(event.data);
      renderMatchCard(match, true);
    } catch(e) {
      console.error("Failed to parse match data:", e);
    }
  };
  
  ws.onclose = () => {
    updateWsStatus('disconnected', 'Disconnected. Retrying in 5s...');
    setTimeout(connectWebSocket, 5000);
  };
  
  ws.onerror = () => {};
}

// ──────────────────────────────────────────────────────────────────────────────
// System Tools & Logs
// ──────────────────────────────────────────────────────────────────────────────

async function actionService(action) {
  try {
    const res = await fetch(`/api/service/${action}`, { method: 'POST' });
    if (!res.ok) throw new Error(`Failed to ${action} service`);
    showToast(`Successfully ran ${action} on service.`);
    if (['start', 'stop', 'restart', 'install', 'uninstall'].includes(action)) {
      setTimeout(loadLogs, 1000);
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

document.getElementById('btn-svc-install')?.addEventListener('click', () => actionService('install'));
document.getElementById('btn-svc-uninstall')?.addEventListener('click', () => actionService('uninstall'));
document.getElementById('btn-svc-restart')?.addEventListener('click', () => actionService('restart'));

document.getElementById('btn-fetch')?.addEventListener('click', async () => {
  const limit = document.getElementById('fetch-limit').value || 50;
  const btn = document.getElementById('btn-fetch');
  btn.innerText = 'Starting...';
  try {
    const res = await fetch(`/api/fetch?limit=${limit}`, { method: 'POST' });
    if (!res.ok) throw new Error("Failed to trigger fetch");
    showToast(`Historical fetch started (${limit} messages). Matches will appear here.`);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.innerText = 'Run Fetch';
  }
});

async function loadLogs() {
  const container = document.getElementById('logs-container');
  if (!container) return;
  container.innerHTML = '<span class="text-slate-500 italic">Loading logs...</span>';
  try {
    const res = await fetch('/api/service/logs');
    const data = await res.json();
    if (data.logs && data.logs.length > 0) {
      container.innerHTML = data.logs.map(l => `<div>${l.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>`).join('');
      container.scrollTop = container.scrollHeight;
    } else {
      container.innerHTML = '<span class="text-slate-500 italic">No logs found.</span>';
    }
  } catch (err) {
    container.innerHTML = '<span class="text-red-400">Failed to load logs.</span>';
  }
}

document.getElementById('btn-refresh-logs')?.addEventListener('click', loadLogs);
// Load logs automatically when switching to the system view
document.querySelector('[data-view="system"]')?.addEventListener('click', loadLogs);


// ──────────────────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────────────────
loadConfig();
loadHistoricalMatches();
connectWebSocket();

// Initial service status guess (can be improved with a real status endpoint, but for now we assume it's stopped until toggled)
updateServiceUI();
