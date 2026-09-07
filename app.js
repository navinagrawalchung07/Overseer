// ── Overseer Dashboard ─────────────────────────────────────────────────────
// Polls /api/state every 3s and connects to /api/events SSE stream.
// Falls back to a rich simulation when the backend is not reachable.

const API_BASE =
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? `http://${window.location.host}`
    : null; // static hosting → simulation only

// ── State ─────────────────────────────────────────────────────────────────
let state = { agents: {}, total_interventions: 0, total_tokens_saved: 0 };
let logEntries = [];
let simulationMode = true;

// ── DOM ───────────────────────────────────────────────────────────────────
const agentsList       = document.getElementById('agentsList');
const eventLog         = document.getElementById('eventLog');
const statusDot        = document.getElementById('statusDot');
const statusText       = document.getElementById('statusText');
const hdrInterventions = document.getElementById('hdrInterventions');
const hdrTokensSaved   = document.getElementById('hdrTokensSaved');
const sumAgents        = document.getElementById('sumAgents');
const sumHealthy       = document.getElementById('sumHealthy');
const sumLooping       = document.getElementById('sumLooping');
const sumDone          = document.getElementById('sumDone');
const sumSaved         = document.getElementById('sumSaved');
const agentCount       = document.getElementById('agentCount');
const modalOverlay     = document.getElementById('modalOverlay');
const modalBody        = document.getElementById('modalBody');
const modalTitle       = document.getElementById('modalTitle');

document.getElementById('clearLog').addEventListener('click', () => { logEntries = []; renderLog(); });
document.getElementById('modalClose').addEventListener('click', () => { modalOverlay.style.display = 'none'; });
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) modalOverlay.style.display = 'none'; });

// ── Connection ────────────────────────────────────────────────────────────
async function tryConnect() {
  if (!API_BASE) { startSimulation(); return; }
  try {
    const r = await fetch(`${API_BASE}/api/state`, { signal: AbortSignal.timeout(2000) });
    if (!r.ok) throw new Error();
    simulationMode = false;
    setStatus('connected', 'Live — connected to supervisor');
    startPolling();
    startSSE();
  } catch {
    startSimulation();
  }
}

function setStatus(cls, label) {
  statusDot.className = 'status-dot-sm ' + cls;
  statusText.textContent = label;
}

// ── Real backend ──────────────────────────────────────────────────────────
function startPolling() {
  poll();
  setInterval(poll, 3000);
}

async function poll() {
  try {
    const r = await fetch(`${API_BASE}/api/state`);
    state = await r.json();
    render();
  } catch {}
}

function startSSE() {
  const es = new EventSource(`${API_BASE}/api/events`);
  es.onmessage = e => {
    const ev = JSON.parse(e.data);
    if (ev.type === 'heartbeat') return;
    if (ev.type === 'intervention') addLogEntry('intervention', ev.agent_id, ev.analysis);
    else                            addLogEntry('action', ev.agent_id, null, ev.action || '');
  };
  es.onerror = () => es.close();
}

// ── Simulation ────────────────────────────────────────────────────────────
const SIM_AGENTS = {
  'auth-fixer': {
    task: 'Fix token expiry bug in src/auth/token.ts',
    interceptAt: 9,
    actions: [
      { tool: 'Read',  key: 'src/auth/token.ts',            tokens: 1240 },
      { tool: 'Bash',  key: "grep -r 'tokenExpiry' src/",   tokens: 680  },
      { tool: 'Read',  key: 'src/auth/refresh.ts',          tokens: 980  },
      { tool: 'Bash',  key: "grep -r 'refreshToken' src/",  tokens: 720  },
      { tool: 'Read',  key: 'src/middleware/auth.ts',        tokens: 860  },
      { tool: 'Read',  key: 'src/auth/token.ts',            tokens: 1240, loop: true },
      { tool: 'Bash',  key: "grep -r 'tokenExpiry' src/",   tokens: 680,  loop: true },
      { tool: 'Read',  key: 'src/auth/token.ts',            tokens: 1240, loop: true },
      { tool: 'Read',  key: 'src/auth/refresh.ts',          tokens: 980,  loop: true },
      { tool: 'Bash',  key: "grep -r 'tokenExpiry' src/",   tokens: 680,  loop: true },
      { tool: 'Read',  key: 'src/auth/token.ts',            tokens: 1240, loop: true },
    ],
  },
  'test-writer': {
    task: 'Write integration tests for the auth module',
    actions: [
      { tool: 'Read',  key: 'src/auth/token.ts',                   tokens: 980  },
      { tool: 'Read',  key: 'src/auth/refresh.ts',                 tokens: 760  },
      { tool: 'Write', key: 'tests/auth/token.test.ts',            tokens: 400  },
      { tool: 'Bash',  key: 'npx jest tests/auth/token.test.ts',   tokens: 820  },
      { tool: 'Edit',  key: 'tests/auth/token.test.ts — add edge cases', tokens: 350 },
      { tool: 'Bash',  key: 'npx jest tests/auth/token.test.ts',   tokens: 820  },
      { tool: 'Write', key: 'tests/auth/refresh.test.ts',          tokens: 400  },
      { tool: 'Bash',  key: 'npx jest tests/auth/',                tokens: 900  },
      { tool: 'Write', key: 'tests/auth/middleware.test.ts',       tokens: 400  },
      { tool: 'Bash',  key: 'npx jest tests/auth/ --coverage',     tokens: 950  },
    ],
  },
  'doc-updater': {
    task: 'Update API docs for auth endpoints',
    actions: [
      { tool: 'Read',  key: 'docs/api/auth.md',    tokens: 640 },
      { tool: 'Read',  key: 'src/auth/token.ts',   tokens: 980 },
      { tool: 'Write', key: 'docs/api/auth.md',    tokens: 300 },
      { tool: 'Write', key: 'docs/api/refresh.md', tokens: 300 },
      { tool: 'Bash',  key: 'markdownlint docs/',  tokens: 420 },
    ],
  },
};

const simState = {};

function startSimulation() {
  simulationMode = true;
  setStatus('error', 'Demo — simulated agents');

  for (const [id, cfg] of Object.entries(SIM_AGENTS)) {
    simState[id] = {
      agent_id: id, task: cfg.task, status: 'warming_up',
      action_count: 0, interventions: 0, tokens_saved: 0,
      last_action: null, last_event: null,
      intercepted: false, completed: false, actionIdx: 0,
    };
    state.agents[id] = simState[id];
  }

  render();
  addLogEntry('info', 'overseer', null, 'Supervisor started — watching 3 agents');

  // Staggered start so agents are not all in sync
  tickAgent('doc-updater',  1100);
  tickAgent('test-writer',  1700);
  tickAgent('auth-fixer',   1400);
}

function tickAgent(agentId, interval) {
  const cfg = SIM_AGENTS[agentId];
  const s   = simState[agentId];

  setTimeout(function tick() {
    if (s.completed) return;

    const actions = cfg.actions;
    if (s.actionIdx >= actions.length) {
      s.status = 'completed';
      s.completed = true;
      render();
      addLogEntry('done', agentId, null, 'All tasks completed');
      return;
    }

    const action  = actions[s.actionIdx];
    s.actionIdx++;
    s.action_count++;
    s.last_action = `[${action.tool}] ${action.key}`;

    if (s.actionIdx <= 2)        s.status = 'warming_up';
    else if (!s.intercepted)     s.status = action.loop ? 'looping' : 'healthy';

    addLogEntry('action', agentId, null, s.last_action);

    // Trigger intervention
    if (cfg.interceptAt && s.actionIdx - 1 === cfg.interceptAt && !s.intercepted) {
      s.intercepted = true;
      const saved = 7200;
      s.tokens_saved  += saved;
      s.interventions++;
      state.total_interventions++;
      s.last_event = {
        type: 'inject_context',
        pattern: 'repeated_read + repeated_grep',
        confidence: 0.94,
        tokens_saved: saved,
        message: 'You have read src/auth/token.ts 4× with no edits and run the same grep 3×. You already know the issue: refreshBuffer is set to 30s instead of 300s at line 47. Stop investigating — write the fix now.',
      };

      setTimeout(() => {
        addLogEntry('intervention', agentId, {
          status: 'looping',
          intervention: 'inject_context',
          confidence: 0.94,
          pattern: 'repeated_read + repeated_grep',
          tokens_wasted_estimate: saved,
          message: s.last_event.message,
        });
        s.status = 'healthy';

        // Recovery: 2 productive actions then done
        setTimeout(() => {
          addLogEntry('action', agentId, null, '[Edit] src/auth/token.ts — refreshBuffer: 30 → 300');
          addLogEntry('action', agentId, null, '[Bash] npm test src/auth/');
          s.action_count += 2;
          s.status = 'completed';
          s.completed = true;
          addLogEntry('done', agentId, null, 'Fixed — tests passing after Overseer intervention');
          render();
        }, 2800);

        render();
      }, 1400);
    }

    render();
    if (!s.completed) setTimeout(tick, interval + (Math.random() * 500 - 250));
  }, interval);
}

// ── Render ────────────────────────────────────────────────────────────────
function render() {
  renderAgents();
  renderSummary();
}

function renderAgents() {
  const agents = Object.values(state.agents);
  if (!agents.length) return;

  agentCount.textContent = `${agents.length} agent${agents.length !== 1 ? 's' : ''}`;

  const order = { looping: 0, drifting: 1, stalled: 1, healthy: 2, warming_up: 3, completed: 4 };
  const sorted = [...agents].sort((a, b) => (order[a.status] ?? 5) - (order[b.status] ?? 5));

  agentsList.innerHTML = '';
  for (const a of sorted) agentsList.appendChild(buildCard(a));
}

function buildCard(a) {
  const card = document.createElement('div');
  card.className = `agent-card ${a.status || ''}`;

  const statusLabel = { healthy: 'healthy', looping: 'looping', drifting: 'drifting', stalled: 'stalled', completed: 'done', warming_up: 'warming' };
  const tokSaved = a.tokens_saved || 0;
  const ivCount  = a.interventions || 0;

  const footerHtml = a.last_action
    ? `<div class="card-footer">↳ ${esc(a.last_action)}</div>` : '';

  const ivHtml = a.last_event ? `
    <div class="iv-block" data-agent="${a.agent_id}">
      <div class="iv-tag">
        <span class="iv-tag-dot"></span>
        ${esc(a.last_event.type || 'intervention')} &mdash; ${Math.round((a.last_event.confidence || 0) * 100)}% confidence
      </div>
      <div class="iv-msg">${esc((a.last_event.message || '').substring(0, 100))}${(a.last_event.message || '').length > 100 ? '…' : ''}</div>
    </div>` : '';

  card.innerHTML = `
    <div class="status-stripe"></div>
    <div class="card-header">
      <span class="pulse ${a.status || ''}"></span>
      <span class="card-id">${esc(a.agent_id)}</span>
      <span class="badge badge-${a.status || 'healthy'}">${statusLabel[a.status] || a.status}</span>
    </div>
    <div class="card-task">${esc(a.task || '')}</div>
    <div class="card-metrics">
      <div class="metric-cell">
        <span class="metric-n">${a.action_count || 0}</span>
        <span class="metric-k">Actions</span>
      </div>
      <div class="metric-cell">
        <span class="metric-n ${ivCount > 0 ? 'red' : ''}">${ivCount}</span>
        <span class="metric-k">Stops</span>
      </div>
      <div class="metric-cell">
        <span class="metric-n ${tokSaved > 0 ? 'green' : ''}">${tokSaved > 0 ? tokSaved.toLocaleString() : '—'}</span>
        <span class="metric-k">Tok Saved</span>
      </div>
    </div>
    ${footerHtml}
    ${ivHtml}
  `;

  const ivBlock = card.querySelector('.iv-block');
  if (ivBlock && a.last_event) {
    ivBlock.addEventListener('click', () => showModal(a));
  }

  return card;
}

function showModal(a) {
  const ev = a.last_event || {};
  modalTitle.textContent = `Intervention — ${a.agent_id}`;
  modalBody.innerHTML = `
    <div class="modal-field">
      <div class="modal-fk">Agent</div>
      <div class="modal-fv">${esc(a.agent_id)}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Task</div>
      <div class="modal-fv">${esc(a.task || '')}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Pattern detected</div>
      <div class="modal-fv red">${esc(ev.pattern || ev.status || '')}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Intervention strategy</div>
      <div class="modal-fv amber">${esc(ev.intervention || ev.type || '')}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Confidence</div>
      <div class="modal-fv">${ev.confidence ? Math.round(ev.confidence * 100) + '%' : '—'}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Tokens saved</div>
      <div class="modal-fv green">${(ev.tokens_wasted_estimate || ev.tokens_saved || 0).toLocaleString()}</div>
    </div>
    <div class="modal-field">
      <div class="modal-fk">Message injected</div>
      <div class="modal-msg">${esc(ev.message || '')}</div>
    </div>
  `;
  modalOverlay.style.display = 'flex';
}

function renderSummary() {
  const agents = Object.values(state.agents);
  sumAgents.textContent  = agents.length;
  sumHealthy.textContent = agents.filter(a => ['healthy','warming_up'].includes(a.status)).length;
  sumLooping.textContent = agents.filter(a => ['looping','drifting','stalled'].includes(a.status)).length;
  sumDone.textContent    = agents.filter(a => a.status === 'completed').length;

  const saved = simulationMode
    ? Object.values(simState).reduce((s, a) => s + (a.tokens_saved || 0), 0)
    : (state.total_tokens_saved || 0);

  const ivTotal = simulationMode
    ? Object.values(simState).reduce((s, a) => s + (a.interventions || 0), 0)
    : (state.total_interventions || 0);

  sumSaved.textContent         = saved > 0 ? saved.toLocaleString() : '0';
  hdrInterventions.textContent = ivTotal;
  hdrTokensSaved.textContent   = saved > 0 ? saved.toLocaleString() : '0';
}

// ── Log ───────────────────────────────────────────────────────────────────
function addLogEntry(type, agentId, analysis, message) {
  const ts = new Date().toTimeString().substring(0, 5);
  let body = '';

  if (type === 'intervention') {
    const a = analysis || {};
    body = `<span class="log-who">${esc(agentId)}</span> ` +
           `<span class="log-stop">loop detected</span> ` +
           `<span class="log-what">· ${esc(a.intervention || '')} · ${esc(a.pattern || '')} · ${Math.round((a.confidence || 0) * 100)}%</span>`;
  } else if (type === 'done') {
    body = `<span class="log-who">${esc(agentId)}</span> <span class="log-ok">✓ ${esc(message || 'completed')}</span>`;
  } else if (type === 'action') {
    body = `<span class="log-who">${esc(agentId)}</span> <span class="log-what">${esc(message || '')}</span>`;
  } else {
    body = `<span class="log-what">${esc(message || '')}</span>`;
  }

  logEntries.unshift({ type, ts, body, analysis, agentId });
  if (logEntries.length > 100) logEntries.pop();
  renderLog();
}

function renderLog() {
  if (!logEntries.length) {
    eventLog.innerHTML = '<div class="log-empty">Waiting for events…</div>';
    return;
  }
  eventLog.innerHTML = '';
  for (const entry of logEntries) {
    const el = document.createElement('div');
    el.className = `log-row ${entry.type === 'intervention' ? 'iv-row' : ''}`;
    el.innerHTML = `<span class="log-ts">${entry.ts}</span><span class="log-body">${entry.body}</span>`;
    if (entry.type === 'intervention' && entry.analysis) {
      const agentData = state.agents[entry.agentId] || { agent_id: entry.agentId, task: '', last_event: entry.analysis };
      el.addEventListener('click', () => showModal({ ...agentData, last_event: entry.analysis }));
    }
    eventLog.appendChild(el);
  }
}

// ── Util ──────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Boot ──────────────────────────────────────────────────────────────────
tryConnect();
