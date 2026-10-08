'use strict';
/* Agent Society hub — plain JS, no build step.
   Sections: helpers · state · map · top bar · people · profile · talk · world feed · stats · settings · toasts · keys · loop */

// ======================================================================= helpers
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const api = {
  get: p => fetch(p).then(r => r.json()),
  post: (p, body) => fetch(p, { method: 'POST', body: JSON.stringify(body || {}) }).then(r => r.json()),
};
const store = {                       // per-browser conveniences only; the page works without them
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
};
const fmt = n => n >= 1e6 ? (n / 1e6).toFixed(2) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n);
const hungerColor = h => h > 70 ? 'var(--bad)' : h > 40 ? 'var(--warn)' : 'var(--good)';
const TIER = { local: '🖥️', smart: '🧠', haiku: '🌱', sonnet: '⭐', opus: '👑', custom: '🔧' };
const STAGE = { baby: '🍼', child: '👶', adult: '', elder: '🧓' };
const SEX = { female: '♀', male: '♂' };
const extras = a => `${STAGE[a.stage] || ''}${a.pregnant ? '🤰' : ''}`;

// ======================================================================= state
const S = {
  st: null, W: 0, H: 0, tiles: [], agents: [], sel: null, detail: null,
  tab: 'people', ptab: 'overview', to: new Set(['*']), filter: 'all',
  zoom: 1, disp: {}, offset: {}, lastEvent: null, stats: [], hover: null, brainKey: '',
};

// ======================================================================= map
const T = 28;
const cv = $('map'), ctx = cv.getContext('2d');
const bg = document.createElement('canvas'), bctx = bg.getContext('2d');
const scroller = $('mapscroll');
const drawn = [];
const rnd = (x, y, k = 0) => { let h = (x * 374761393 + y * 668265263 + k * 2147483647) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };

function paintTile(x, y) {
  const t = S.tiles[y][x], px = x * T, py = y * T, c = bctx, v = rnd(x, y);
  const base = { grass: [78, 154, 71], food: [78, 154, 71], sprout: [78, 154, 71], crop: [78, 154, 71], water: [47, 111, 181],
    sand: [217, 200, 138], rock: [123, 127, 134], tree: [78, 154, 71], structure: [150, 118, 78] }[t] || [60, 60, 60];
  const k = (v - .5) * 14;
  c.fillStyle = `rgb(${base.map(n => Math.round(n + k)).join(',')})`; c.fillRect(px, py, T, T);
  if (t === 'grass' || t === 'food') {
    c.strokeStyle = 'rgba(30,90,35,.55)'; c.lineWidth = 1.4;
    for (let i = 0; i < 4; i++) { const a = px + 3 + rnd(x, y, i + 1) * (T - 6), b = py + 6 + rnd(x, y, i + 9) * (T - 9); c.beginPath(); c.moveTo(a, b); c.lineTo(a - 2, b - 4); c.moveTo(a, b); c.lineTo(a + 2, b - 4); c.stroke(); }
    if (t === 'grass' && rnd(x, y, 20) > .9) { c.fillStyle = rnd(x, y, 21) > .5 ? '#fff3a0' : '#f8c8e0'; c.beginPath(); c.arc(px + 6 + rnd(x, y, 22) * (T - 12), py + 6 + rnd(x, y, 23) * (T - 12), 2.2, 0, 7); c.fill(); }
  }
  if (t === 'food') {
    c.fillStyle = '#2b6a2f'; c.beginPath(); c.arc(px + T / 2, py + T / 2 + 2, T * .36, 0, 7); c.fill();
    c.fillStyle = '#37803b'; c.beginPath(); c.arc(px + T / 2 - 3, py + T / 2 - 1, T * .22, 0, 7); c.fill();
    c.fillStyle = '#e0334e'; [[-6, 3], [5, 0], [0, 8], [-1, -3], [7, 7]].forEach(([a, b]) => { c.beginPath(); c.arc(px + T / 2 + a, py + T / 2 + b, 2.6, 0, 7); c.fill(); });
  }
  if (t === 'tree') {
    c.fillStyle = 'rgba(0,0,0,.25)'; c.beginPath(); c.ellipse(px + T / 2, py + T - 4, T * .38, T * .13, 0, 0, 7); c.fill();
    c.fillStyle = '#5b3d22'; c.fillRect(px + T / 2 - 2.5, py + T - 12, 5, 9);
    [['#245c2a', T / 2, T / 2 - 1, T * .38], ['#2e7a35', T / 2 - 3, T / 2 - 4, T * .27], ['#3c9744', T / 2 + 3, T / 2 - 5, T * .2]]
      .forEach(([col, a, b, r]) => { c.fillStyle = col; c.beginPath(); c.arc(px + a, py + b, r, 0, 7); c.fill(); });
  }
  if (t === 'structure') { c.fillStyle = 'rgba(0,0,0,.12)'; for (let i = 0; i < 4; i++) c.fillRect(px, py + i * 7, T, 1); }
  if (t === 'sprout' || t === 'crop') {
    c.fillStyle = '#6b4a2b'; c.fillRect(px + 3, py + T - 9, T - 6, 6);
    if (t === 'sprout') {
      c.strokeStyle = '#8fe36b'; c.lineWidth = 2;
      [[-5, 0], [0, -3], [5, 0]].forEach(([a, b]) => { c.beginPath(); c.moveTo(px + T / 2, py + T - 9); c.quadraticCurveTo(px + T / 2 + a, py + T - 14 + b, px + T / 2 + a * 1.4, py + T - 17 + b); c.stroke(); });
    } else {
      for (let i = 0; i < 5; i++) { const a = px + 5 + i * 4.5; c.strokeStyle = '#d8b640'; c.lineWidth = 2; c.beginPath(); c.moveTo(a, py + T - 9); c.lineTo(a - 1, py + 7); c.stroke(); c.fillStyle = '#f3d35a'; c.beginPath(); c.ellipse(a - 1, py + 8, 2, 4, 0, 0, 7); c.fill(); }
    }
  }
  if (t === 'water') {
    c.strokeStyle = 'rgba(255,255,255,.22)'; c.lineWidth = 1.5;
    for (let i = 0; i < 2; i++) { const a = px + 4 + rnd(x, y, i + 3) * (T - 14), b = py + 7 + i * 11 + rnd(x, y, i + 5) * 4; c.beginPath(); c.moveTo(a, b); c.quadraticCurveTo(a + 4, b - 3, a + 8, b); c.quadraticCurveTo(a + 12, b + 3, a + 16, b); c.stroke(); }
    c.fillStyle = 'rgba(255,255,255,.3)';
    [[0, -1, px, py, T, 2], [0, 1, px, py + T - 2, T, 2], [-1, 0, px, py, 2, T], [1, 0, px + T - 2, py, 2, T]].forEach(([dx, dy, a, b, w, h]) => {
      const n = S.tiles[y + dy]?.[x + dx]; if (n && n !== 'water') c.fillRect(a, b, w, h); });
  }
  if (t === 'sand') { c.fillStyle = 'rgba(120,95,40,.35)'; for (let i = 0; i < 6; i++) c.fillRect(px + rnd(x, y, i + 30) * (T - 2), py + rnd(x, y, i + 40) * (T - 2), 1.6, 1.6); }
  if (t === 'rock') {
    c.fillStyle = 'rgba(0,0,0,.28)'; c.beginPath(); c.ellipse(px + T / 2, py + T - 5, T * .42, T * .14, 0, 0, 7); c.fill();
    c.fillStyle = '#8f949c'; c.beginPath(); c.moveTo(px + 4, py + T - 6); c.lineTo(px + 7, py + 9); c.lineTo(px + 15, py + 4); c.lineTo(px + 23, py + 9); c.lineTo(px + T - 3, py + T - 6); c.closePath(); c.fill();
    c.fillStyle = '#a9aeb6'; c.beginPath(); c.moveTo(px + 7, py + 9); c.lineTo(px + 15, py + 4); c.lineTo(px + 17, py + 13); c.lineTo(px + 9, py + 16); c.closePath(); c.fill();
  }
}

function syncTiles(next) {
  S.tiles = next;
  for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) {
    if (!drawn[y]) drawn[y] = [];
    if (drawn[y][x] !== next[y][x]) { drawn[y][x] = next[y][x]; paintTile(x, y); }
  }
}

const ICONS = [['bridge', '🌉'], ['dock', '⚓'], ['pier', '⚓'], ['house', '🏠'], ['hut', '🛖'], ['shelter', '🏕️'], ['home', '🏠'], ['wall', '🧱'],
  ['fence', '🧱'], ['sign', '🪧'], ['fire', '🔥'], ['storage', '📦'], ['store', '📦'], ['barn', '🏚️'], ['farm', '🌾'], ['garden', '🌷'],
  ['well', '⛲'], ['temple', '⛩️'], ['shrine', '⛩️'], ['school', '🏫'], ['market', '🏪'], ['tower', '🗼'], ['bed', '🛏️'], ['path', '🟫'],
  ['road', '🟫'], ['floor', '🟫'], ['bench', '🪑'], ['table', '🪑'], ['monument', '🗿'], ['statue', '🗿'], ['gate', '⛩️'], ['door', '🚪'], ['boat', '⛵'], ['raft', '⛵']];
const iconFor = k => { k = (k || '').toLowerCase(); for (const [w, i] of ICONS) if (k.includes(w)) return i; return '🏗️'; };

function drawFrame() {
  ctx.drawImage(bg, 0, 0);
  const st = S.st;
  if (st) {
    if ($('fog').checked && st.fog) {
      ctx.fillStyle = 'rgba(6,8,12,.62)';
      st.fog.forEach((row, y) => { let x = 0; while (x < S.W) { if (row[x] === '0') { let e = x; while (e < S.W && row[e] === '0') e++; ctx.fillRect(x * T, y * T, (e - x) * T, T); x = e; } else x++; } });
    }
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const s of st.structures) { ctx.font = (s.walkable ? '17px' : '22px') + ' system-ui'; ctx.fillText(iconFor(s.kind), s.x * T + T / 2, s.y * T + T / 2 + 1); }
    ctx.globalAlpha = .85; ctx.font = '18px system-ui';
    for (const g of st.dead) ctx.fillText('🪦', g.x * T + T / 2, g.y * T + T / 2);
    ctx.globalAlpha = 1;
    for (const a of S.agents) drawAgent(a);
    if ($('bubbles').checked) {
      for (const a of S.agents) if (a.say) drawTalkLine(a);
      for (const a of S.agents) if (a.say) drawBubble(a);
    }
  }
  requestAnimationFrame(drawFrame);
}

function pos(a) {                       // smooth movement; agents sharing a tile fan out a little
  const d = S.disp[a.name] || (S.disp[a.name] = { x: a.x, y: a.y });
  const [ox, oy] = S.offset[a.name] || [0, 0];
  d.x += (a.x + ox - d.x) * .18; d.y += (a.y + oy - d.y) * .18;
  return d;
}
function spread(agents) {
  const groups = {};
  for (const a of agents) (groups[a.x + ',' + a.y] ||= []).push(a.name);
  S.offset = {};
  for (const names of Object.values(groups)) names.forEach((n, i) => {
    if (names.length > 1) { const ang = i / names.length * Math.PI * 2; S.offset[n] = [Math.cos(ang) * .28, Math.sin(ang) * .28]; }
  });
}

function drawAgent(a) {
  const d = pos(a), px = d.x * T + T / 2, py = d.y * T + T / 2, r = (T / 2 - 3) * (a.stage === 'baby' ? .55 : a.adult ? 1 : .72);
  ctx.fillStyle = 'rgba(0,0,0,.3)'; ctx.beginPath(); ctx.ellipse(px, py + r + 1, r * .9, r * .35, 0, 0, 7); ctx.fill();
  if (S.sel === a.name) { ctx.strokeStyle = '#ffd93d'; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(px, py, r + 5, 0, 7); ctx.stroke(); }
  ctx.fillStyle = a.color; ctx.strokeStyle = '#111'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(px, py, r, 0, 7); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#111'; ctx.font = 'bold 13px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(a.name[0], px, py + .5);
  ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(px - 11, py - r - 9, 22, 5);             // hunger bar
  ctx.fillStyle = a.hunger > 70 ? '#e0525e' : a.hunger > 40 ? '#e0a252' : '#5cc46e'; ctx.fillRect(px - 10, py - r - 8, 20 * (1 - a.hunger / 100), 3);
  if (a.heart) { ctx.font = '15px system-ui'; ctx.fillText('❤️', px + r + 2, py - r - 12); }
  if (a.pregnant) { ctx.font = '13px system-ui'; ctx.fillText('🤰', px + r + 3, py + 2); }
  if (a.stage === 'baby') { ctx.font = '12px system-ui'; ctx.fillText('🍼', px + r + 3, py + 2); }
  if (a.slow) { ctx.font = '14px system-ui'; ctx.fillText('💭', px - r - 4, py - r - 10); }
  ctx.font = 'bold 11px system-ui';
  const tag = `${a.name} · ${a.age}`, nw = ctx.measureText(tag).width + 10;
  ctx.fillStyle = 'rgba(10,12,16,.78)'; ctx.beginPath(); ctx.roundRect(px - nw / 2, py + r + 4, nw, 15, 6); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.fillText(tag, px, py + r + 11.5);
}

function drawTalkLine(a) {
  const d = S.disp[a.name], tg = a.say_to && a.say_to !== 'all' && a.say_to !== 'Human' ? S.disp[a.say_to] : null;
  if (!d || !tg) return;
  ctx.strokeStyle = a.color; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.globalAlpha = .8;
  ctx.beginPath(); ctx.moveTo(d.x * T + T / 2, d.y * T + T / 2); ctx.lineTo(tg.x * T + T / 2, tg.y * T + T / 2); ctx.stroke();
  ctx.setLineDash([]); ctx.globalAlpha = 1;
}

function drawBubble(a) {
  const d = S.disp[a.name], px = d.x * T + T / 2, py = d.y * T + T / 2, r = (T / 2 - 3) * (a.stage === 'baby' ? .55 : a.adult ? 1 : .72);
  const label = `${a.name} → ${a.say_to === 'all' ? 'everyone' : a.say_to === 'Human' ? 'you' : a.say_to}`;
  const txt = a.say.length > 90 ? a.say.slice(0, 88) + '…' : a.say;
  ctx.font = '12px system-ui';
  const lines = []; let cur = '';
  for (const w of txt.split(' ')) { if (ctx.measureText(cur + ' ' + w).width > 200 && cur) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
  lines.push(cur);
  const w = Math.max(...lines.map(l => ctx.measureText(l).width), ctx.measureText(label).width) + 16, h = lines.length * 15 + 22;
  const bx = Math.min(Math.max(px - w / 2, 3), cv.width - w - 3), by = Math.max(3, py - r - h - 14);
  ctx.fillStyle = 'rgba(255,255,255,.5)'; ctx.beginPath(); ctx.roundRect(bx, by, w, h, 8); ctx.fill();   // see-through
  ctx.globalAlpha = .7; ctx.strokeStyle = a.color; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.moveTo(px - 6, by + h); ctx.lineTo(px, by + h + 8); ctx.lineTo(px + 6, by + h); ctx.fill();
  ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.fillStyle = '#556'; ctx.font = '10px system-ui'; ctx.fillText(label, bx + 8, by + 4);
  ctx.font = '12px system-ui'; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.75)'; ctx.lineJoin = 'round';
  lines.forEach((l, k) => { ctx.strokeText(l, bx + 8, by + 17 + k * 15); ctx.fillStyle = '#111'; ctx.fillText(l, bx + 8, by + 17 + k * 15); });
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
}

// zoom & pan
function setZoom(z, cx, cy) {
  const old = S.zoom; S.zoom = Math.min(2, Math.max(.25, z));
  const r = scroller.getBoundingClientRect();
  cx = cx ?? r.width / 2; cy = cy ?? r.height / 2;
  const wx = (scroller.scrollLeft + cx) / old, wy = (scroller.scrollTop + cy) / old;     // world px under the pointer
  cv.style.width = Math.round(S.W * T * S.zoom) + 'px'; cv.style.height = Math.round(S.H * T * S.zoom) + 'px';
  scroller.scrollLeft = wx * S.zoom - cx; scroller.scrollTop = wy * S.zoom - cy;
  store.set('zoom', S.zoom);
}
const fitZoom = () => setZoom(Math.min(scroller.clientWidth / (S.W * T), scroller.clientHeight / (S.H * T)));
function centerOn(name, smooth = true) {
  const a = S.agents.find(x => x.name === name); if (!a) return;
  const d = S.disp[a.name] || a;
  scroller.scrollTo({ left: (d.x + .5) * T * S.zoom - scroller.clientWidth / 2, top: (d.y + .5) * T * S.zoom - scroller.clientHeight / 2, behavior: smooth ? 'smooth' : 'auto' });
}
function worldAt(e) {
  const r = cv.getBoundingClientRect();
  return { fx: (e.clientX - r.left) / r.width * S.W, fy: (e.clientY - r.top) / r.height * S.H };
}
function agentAt(fx, fy, lim = 1.1) {
  let best = null, bd = lim;
  for (const a of S.agents) { const d = S.disp[a.name] || a, k = Math.hypot(d.x + .5 - fx, d.y + .5 - fy); if (k < bd) { bd = k; best = a; } }
  return best;
}
scroller.addEventListener('wheel', e => {
  e.preventDefault();
  const r = scroller.getBoundingClientRect();
  setZoom(S.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
}, { passive: false });
let drag = null;
scroller.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, sl: scroller.scrollLeft, st: scroller.scrollTop, moved: false }; });
window.addEventListener('pointermove', e => {
  if (drag) {
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; scroller.classList.add('dragging'); $('follow').checked = false; }
    if (drag.moved) { scroller.scrollLeft = drag.sl - dx; scroller.scrollTop = drag.st - dy; }
  }
});
window.addEventListener('pointerup', e => {
  if (drag && !drag.moved && e.target === cv) {
    const { fx, fy } = worldAt(e), a = agentAt(fx, fy);
    if (a) select(a.name);
  }
  drag = null; scroller.classList.remove('dragging');
});
cv.addEventListener('dblclick', e => { const { fx, fy } = worldAt(e), a = agentAt(fx, fy); if (a) { select(a.name); $('follow').checked = true; } });
cv.addEventListener('mousemove', e => {
  const { fx, fy } = worldAt(e), x = Math.floor(fx), y = Math.floor(fy), tip = $('tip');
  const t = S.tiles[y]?.[x], st = S.st;
  if (!t || !st || drag?.moved) { tip.hidden = true; return; }
  const names = { grass: 'Grass', water: 'Water — impassable', sand: 'Sand', rock: 'Rock — gather for stone', tree: 'Tree — gather for wood',
    food: 'Berry bush — food (slow to regrow)', sprout: 'Young plant — tend it to grow', crop: 'Ripe crop — 3 food + a seed', structure: 'Built structure' };
  const unseen = st.fog && st.fog[y][x] === '0';
  let html = `<div class="muted">(${x}, ${y}) · ${unseen ? 'Unexplored' : names[t]}</div>`;
  const a = agentAt(fx, fy, .8);
  if (a) html = `<b style="color:${a.color}">${esc(a.name)}</b> ${TIER[a.tier]} ${a.role ? '· ' + esc(a.role) : ''}${a.slow ? ' · 💭 still thinking' : ''}<div>${SEX[a.sex]} ${a.stage} ${extras(a)} · ${a.age} days old · hunger ${a.hunger} · ${a.food} food${a.pregnant ? ` · due day ${a.due}` : ''}</div><div class="muted">${esc(a.doing)}</div>` + html;
  const s = st.structures.find(q => q.x === x && q.y === y);
  if (s) html += `<div>${iconFor(s.kind)} <b>${esc(s.kind)}</b> by ${esc(s.by)}${s.function ? `<div style="color:var(--gold)">⚙️ ${esc(s.function)}</div>` : '<div class="muted">decorative</div>'}${s.stock ? `<div>📦 ${Object.entries(s.stock).map(([k, v]) => `${v} ${k}`).join(' · ')}</div>` : ''}${s.text ? `<div class="muted">“${esc(s.text)}”</div>` : ''}</div>`;
  const g = st.dead.find(q => q.x === x && q.y === y);
  if (g) html += `<div>🪦 ${esc(g.name)} — died of ${esc(g.cause)} at ${g.age} (day ${g.died})</div>`;
  tip.innerHTML = html; tip.hidden = false;
  tip.style.left = Math.min(e.clientX + 14, innerWidth - 290) + 'px'; tip.style.top = (e.clientY + 14) + 'px';
});
cv.addEventListener('mouseleave', () => { $('tip').hidden = true; });
$('z-in').onclick = () => setZoom(S.zoom * 1.25);
$('z-out').onclick = () => setZoom(S.zoom / 1.25);
$('z-fit').onclick = fitZoom;
$('fog').checked = store.get('fog', true);
$('fog').onchange = e => store.set('fog', e.target.checked);
$('bubbles').checked = store.get('bubbles', true);
$('bubbles').onchange = e => store.set('bubbles', e.target.checked);
setInterval(() => { if ($('follow').checked && S.sel) centerOn(S.sel); }, 1200);

// ======================================================================= top bar & banner
function renderTop(st) {
  $('p-day').textContent = `Day ${st.day}`;
  const B = st.backends || {};
  $('p-brain').textContent = B.mock ? '🎭 Mock (scripted)' : '🧠 ' + [B.local ? 'Local: ' + B.local_model : '', B.smart_local ? 'Smart: ' + B.smart_local : '', B.claude ? 'Claude' : ''].filter(Boolean).join(' + ');
  $('p-pop').textContent = `👥 ${st.agents.length} / ${st.limits.max_agents}` + (st.dead.length ? ` · 🪦 ${st.dead.length}` : '');
  $('p-explored').textContent = `🧭 ${st.explored}% explored`;
  $('p-speed').textContent = `⏱ ${st.day_seconds || 0}s / day` + (st.thinking ? ` · 💭 ${st.thinking} thinking` : '');
  $('p-speed').title = 'Seconds the last day took. 💭 = agents whose brain is still working (slow brains act a little later instead of holding everyone up).';
  const u = st.usage;
  $('p-usage').textContent = `💬 ${fmt(u.calls)} calls · ${fmt(u.input + u.output)} tokens` + (u.cost != null && u.cost > 0 ? ` · ~$${u.cost.toFixed(2)}` : '');
  $('p-usage').title = Object.entries(u.models).map(([m, x]) => `${m}: ${x.calls} calls, ${x.input} in / ${x.output} out`).join('\n') || 'No model calls yet';
  $('b-pause').textContent = st.paused ? '▶ Resume' : '⏸ Pause';
  $('b-pause').classList.toggle('primary', !st.paused);
  $('b-step').disabled = !st.paused;
  for (const b of $('speed').children) b.classList.toggle('on', +b.dataset.v === st.interval);
  const notes = (B.notes || []).filter(n => /unavailable|not reachable|isn.t installed/.test(n));
  const err = st.errors.length && st.day - st.errors[st.errors.length - 1].tick < 10 ? st.errors[st.errors.length - 1] : null;
  $('banner').innerHTML =
    (B.mock ? '<div class="bad">⚠ Mock mode — these agents are scripted and can\'t really think or reply. Start Ollama or set ANTHROPIC_API_KEY, then restart the hub.</div>' : '')
    + (!B.mock && notes.length ? `<div class="warn">ℹ ${esc(notes.join(' · '))}</div>` : '')
    + (err ? `<div class="bad">Brain error — ${esc(err.agent)} (${esc(err.model)}): ${esc(err.error)}</div>` : '');
}
$('b-pause').onclick = () => api.post('/api/control', { paused: !S.st?.paused }).then(poll);
$('b-step').onclick = () => api.post('/api/control', { step: true }).then(() => setTimeout(poll, 300));
for (const b of $('speed').children) b.onclick = () => api.post('/api/control', { interval: +b.dataset.v, max_wait: +b.dataset.w }).then(poll);

// ======================================================================= tabs
function showTab(name) {
  S.tab = name;
  for (const b of $('tabs').children) b.classList.toggle('on', b.dataset.tab === name);
  for (const s of document.querySelectorAll('.tab')) s.hidden = s.id !== 'tab-' + name;
  if (name === 'stats') loadStats();
  if (name === 'settings') loadSaves();
  if (name === 'talk') renderChat(true);
  store.set('tab', name);
}
for (const b of $('tabs').children) b.onclick = () => showTab(b.dataset.tab);

// ======================================================================= people
function renderList(st) {
  const q = $('search').value.trim().toLowerCase();
  const rows = st.agents.filter(a => !q || a.name.toLowerCase().includes(q) || (a.role || '').toLowerCase().includes(q));
  $('list').innerHTML = rows.map(a => `
    <div class="person ${S.sel === a.name ? 'sel' : ''}" data-name="${esc(a.name)}">
      <div class="avatar" style="background:${a.color}">${esc(a.name[0])}</div>
      <div><div class="name">${esc(a.name)} <span class="muted" title="${a.sex}">${SEX[a.sex]}</span> <span title="${a.stage === 'baby' ? 'babies don\'t use a brain' : a.tier}">${a.stage === 'baby' ? '' : TIER[a.tier]}</span> ${extras(a)}</div>
        <div class="sub">${a.role ? esc(a.role) : '<i>no role yet</i>'} · ${esc(a.doing) || 'getting started'}</div></div>
      <div class="right">🎂 ${a.age}d<br>🍎 ${a.food}</div>
      <div class="bar" title="Hunger ${a.hunger}/100"><div style="width:${a.hunger}%;background:${hungerColor(a.hunger)}"></div></div>
    </div>`).join('') || '<p class="muted">Nobody matches.</p>';
  $('graves').innerHTML = st.dead.length ? '<h3>In memory</h3>' + st.dead.map(g =>
    `<div class="grave" data-name="${esc(g.name)}">🪦 ${esc(g.name)} — ${esc(g.cause)} at ${g.age} days (day ${g.died})</div>`).join('') : '';
}
$('list').onclick = e => { const p = e.target.closest('.person'); if (p) select(p.dataset.name); };
$('graves').onclick = e => { const g = e.target.closest('.grave'); if (g) select(g.dataset.name, false); };
$('search').oninput = () => S.st && renderList(S.st);

function select(name, center = true) {
  S.sel = name; S.detail = null; S.brainKey = '';
  showTab('people');
  $('people-list').hidden = true; $('profile').hidden = false;
  $('profile').innerHTML = '<p class="muted">Loading…</p>';
  if (center) centerOn(name);
  loadDetail();
}
function closeProfile() {
  S.sel = null; S.detail = null;
  $('people-list').hidden = false; $('profile').hidden = true;
  if (S.st) renderList(S.st);
}

// ======================================================================= profile
async function loadDetail() {
  if (!S.sel) return;
  const d = await api.get('/api/agent?name=' + encodeURIComponent(S.sel));
  if (d.error || d.name !== S.sel) return;
  S.detail = d; renderProfile();
}

function renderProfile() {
  const a = S.detail, el = $('profile');
  if (!a) return;
  if (!el.querySelector('.profile-head')) {
    el.innerHTML = `<button class="back" id="back">← All people</button>
      <div class="profile-head" id="ph"></div><div class="actions" id="pa"></div>
      <div class="subtabs" id="pt">${['overview:Overview', 'mind:Thoughts', 'memory:Memory', 'relations:Relations', 'brain:Brain']
        .map(s => { const [k, l] = s.split(':'); return `<button data-k="${k}">${l}</button>`; }).join('')}</div><div id="pb"></div>`;
    $('back').onclick = closeProfile;
    $('pt').onclick = e => { const b = e.target.closest('button'); if (b) { S.ptab = b.dataset.k; S.brainKey = ''; renderProfile(); } };
    $('pa').onclick = e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.do === 'talk') { S.to = new Set([a.name]); showTab('talk'); renderTo(); $('msg').focus(); }
      if (b.dataset.do === 'locate') centerOn(S.sel);
      if (b.dataset.do === 'follow') { $('follow').checked = !$('follow').checked; centerOn(S.sel); }
      if (b.dataset.gift) api.post('/api/gift', { name: S.sel, what: b.dataset.gift }).then(r => { if (r.gift) toast(`🎁 You gave ${S.sel} ${r.gift}`, '#7dd3fc'); loadDetail(); });
    };
  }
  for (const b of $('pt').children) b.classList.toggle('on', b.dataset.k === S.ptab);
  $('ph').innerHTML = `<div class="avatar big" style="background:${a.color}">${esc(a.name[0])}</div>
    <div><h2>${esc(a.name)} ${!a.alive ? '🪦' : a.stage === 'baby' ? '' : TIER[a.tier]}</h2>
    <div class="muted">${SEX[a.sex]} ${a.adult ? (a.sex === 'female' ? 'woman' : 'man') : (a.sex === 'female' ? 'girl' : 'boy')} · ${a.role ? esc(a.role) : 'no role yet'} · ${a.age} days old · ${a.alive ? a.stage + ' ' + extras(a) : `died of ${esc(a.cause)} on day ${a.died}`}</div></div>`;
  $('pa').innerHTML = a.alive ? `<button class="btn" data-do="talk">💬 Talk</button><button class="btn" data-do="locate">📍 Find on map</button>
    <button class="btn" data-do="follow">${$('follow').checked ? '⏹ Stop following' : '👁 Follow'}</button>
    <button class="btn" data-gift="food" title="Give 3 food">🎁 🍎</button><button class="btn" data-gift="seeds" title="Give 3 seeds">🎁 🌱</button>
    <button class="btn" data-gift="wood" title="Give 3 wood">🎁 🪵</button><button class="btn" data-gift="stone" title="Give 3 stone">🎁 🪨</button>` : '';
  const body = $('pb');
  if (S.ptab === 'overview') body.innerHTML = overview(a);
  if (S.ptab === 'mind') body.innerHTML = timeline(a);
  if (S.ptab === 'memory') body.innerHTML = memory(a);
  if (S.ptab === 'relations') body.innerHTML = relations(a);
  if (S.ptab === 'brain') {
    const B = S.st?.backends || {}, key = a.name + a.model + B.local + B.smart_local + B.claude + B.mock + a.alive;
    if (key !== S.brainKey) { S.brainKey = key; body.innerHTML = brain(a, B); }
  }
}

const meter = (label, v, color) => `<div class="meter"><span>${label}</span><div class="bar"><div style="width:${v}%;background:${color}"></div></div><span>${v}</span></div>`;

function overview(a) {
  const l = a.history.filter(h => h.action !== 'reply to Human').slice(-1)[0];
  const notes = (a.pregnancy ? `<div class="card">🤰 Pregnant by <a href="#" data-goto="${esc(a.pregnancy.father)}">${esc(a.pregnancy.father)}</a> — the baby is due on day ${a.pregnancy.due}.</div>` : '')
    + (a.stage === 'baby' ? `<div class="card">🍼 A baby: can't think or feed themselves yet, and stays with their mother. Others must <b>care</b> for them (or you can send food). A child from day 5, an adult from day 10.</div>` : '')
    + (a.stage === 'child' ? '<div class="card">👶 A child: thinks and acts on their own, an adult from day 10.</div>' : '');
  return notes + `${meter('Hunger', a.hunger, hungerColor(a.hunger))}${meter('Health', a.health, a.health < 40 ? 'var(--bad)' : 'var(--good)')}
    <div class="kv" style="margin-top:8px"><span>Carrying</span><span>🍎 ${a.food} food · 🌱 ${a.seeds} seeds · 🪵 ${a.wood} wood · 🪨 ${a.stone} stone</span>
    <span>Objects</span><span class="objs">${a.items.map(i => `<span class="obj" title="${esc(i.text)}">🔧 ${esc(i.name)}</span>`).join('') || '<span class="muted">none yet</span>'}</span>
    <span>Explored</span><span>${a.discoveries} tiles seen first</span>
    <span>Position</span><span>(${a.x}, ${a.y})</span></div>
    ${l ? `<div class="card thought">💭 ${esc(l.thought)}<div class="tag" style="margin-top:4px">▶ ${esc(l.action)} → ${esc(l.result)}</div></div>` : ''}
    ${a.advice && a.advice.length ? `<div class="card" style="border-left:3px solid var(--gold)">🧙 <b>Sol's advice</b> (day ${a.advice[a.advice.length - 1][0]}): ${esc(a.advice[a.advice.length - 1][1])}</div>` : ''}
    ${a.ambition ? `<div class="card" style="border-left:3px solid var(--gold)">🎯 <b>Ambition:</b> ${esc(a.ambition)}</div>` : ''}
    ${a.plan ? `<div class="card" style="border-left:3px solid var(--accent)">🗺️ <b>Plan:</b> ${esc(a.plan)}</div>` : ''}
    ${a.queue.length ? `<div class="card">⏭️ <b>Next up</b> (runs automatically): ${a.queue.map(q => esc(q.action + (q.target ? ' → ' + q.target : q.title ? ' ' + q.title : q.to && q.to !== 'all' ? ' → ' + q.to : ''))).join(' · ')}</div>` : ''}
    <h3>Abilities</h3>${Object.entries(a.abilities).map(([k, v]) => `<div title="${esc(a.ability_info[k])}">${meter(k[0].toUpperCase() + k.slice(1), v * 10, v >= 7 ? 'var(--good)' : v <= 3 ? 'var(--warn)' : 'var(--accent)').replace(`<span>${v * 10}</span></div>`, `<span>${v}/10</span></div>`)}</div>`).join('')}
    <p class="muted small">Hover an ability to see what it does. Expected lifespan: about ${a.lifespan} days.</p>
    ${a.orders.length ? `<h3>You asked</h3>${a.orders.map(o => `<div class="card">“${esc(o[1])}” <span class="tag">day ${o[0]}</span></div>`).join('')}` : ''}
    <h3>Personality</h3>${Object.entries(a.traits).map(([k, v]) => meter({ openness: 'Openness', conscientiousness: 'Diligence', extraversion: 'Outgoing', agreeableness: 'Kindness', neuroticism: 'Anxiety' }[k] || k, Math.round(v * 100), 'var(--accent)')).join('')}`;
}

function timeline(a) {
  return `<div class="tag">${a.history_total} turns in total · newest first</div><div class="timeline">` + a.history.slice().reverse().map(h => `
    <div class="entry"><div class="tag">day ${h.tick} · (${h.x}, ${h.y}) · hunger ${h.hunger}</div>
      ${h.heard?.length ? `<div class="heard">👂 ${h.heard.map(esc).join('<br>👂 ')}</div>` : ''}
      <div>💭 ${esc(h.thought)}</div><div>▶ <b>${esc(h.action)}</b> <span class="muted">→ ${esc(h.result)}</span></div></div>`).join('') + '</div>';
}

function memory(a) {
  return (a.summary ? `<div class="card" style="border-left:3px solid #9085e9"><b>Earlier life (summary)</b><br>${esc(a.summary)}</div>` : '')
    + `<div class="tag">${a.log_total} memories in total · newest first</div>`
    + a.log.slice().reverse().map(m => `<div style="padding:4px 0;border-top:1px solid var(--line);font-size:13px">${esc(m)}</div>`).join('');
}

function relations(a) {
  const love = S.st?.limits.love || 50, link = n => `<a href="#" data-goto="${esc(n)}">${esc(n)}</a>`;
  const bonds = Object.entries(a.bonds);
  return `<h3>Family</h3><div class="kv"><span>Parents</span><span>${a.parents.map(link).join(' & ') || '<span class="muted">none — a first settler</span>'}</span>
    <span>Children</span><span>${a.children.map(link).join(', ') || '<span class="muted">none yet</span>'}</span></div>
    <h3>Feelings toward others</h3>${bonds.length ? bonds.map(([n, v]) => `<div class="meter"><span>${v >= love ? '💖 ' : ''}${link(n)}</span>
      <div class="bar"><div style="width:${v}%;background:${v >= love ? '#f15bb5' : v >= 25 ? '#9085e9' : '#5f6b7a'}"></div></div><span>${v}</span></div>`).join('')
    : '<p class="muted">No strong feelings yet.</p>'}<p class="muted small">25+ = friend · ${love}+ = in love (two adults in love can have a child)</p>`;
}
$('profile').addEventListener('click', e => { const g = e.target.closest('[data-goto]'); if (g) { e.preventDefault(); select(g.dataset.goto); } });

function brain(a, B) {
  if (!a.alive) return '<p class="muted">They have passed away.</p>';
  const canL = B.local || B.mock, canC = B.claude || B.mock;
  const opt = (t, title, sub, ok, why) => `<button class="btn ${a.tier === t ? 'on' : ''}" data-model="${t}" ${ok ? '' : `disabled title="${why}"`}>${TIER[t]} ${title}<small>${sub}</small></button>`;
  return `<p>Thinks with <b>${TIER[a.tier]} ${esc(a.model === 'local' ? 'local model (' + (B.local_model || '?') + ')' : a.model || 'default')}</b></p>
    <div class="tiers" id="tiers">
      ${opt('local', 'Local', `free · ${esc(B.local_model || '')}`, canL, 'No local model server found')}
      ${opt('smart', 'Smart local', B.smart_local ? `free · ${esc(B.smart_local)}` : 'start the hub with --smart-local-model', !!B.smart_local || B.mock, 'Start the hub with --smart-local-model qwen2.5:14b-instruct')}
      ${opt('haiku', 'Haiku', 'cheap & quick', canC, 'Set ANTHROPIC_API_KEY to use Claude')}
      ${opt('sonnet', 'Sonnet', 'smarter', canC, 'Set ANTHROPIC_API_KEY to use Claude')}
      ${opt('opus', 'Enlighten', 'Opus — only one agent', canC, 'Set ANTHROPIC_API_KEY to use Claude')}
    </div>
    <h3>Or any model id</h3>
    <div class="composer"><input id="custom-model" placeholder="e.g. claude-sonnet-5-5 or local:llama3.2:3b"><button class="btn" id="set-model">Set</button></div>
    <p class="muted small">Enlightening someone drops the previously enlightened agent to Sonnet.</p>`;
}
$('profile').addEventListener('click', e => {
  const b = e.target.closest('[data-model]'), set = e.target.closest('#set-model');
  const model = b ? b.dataset.model : set ? $('custom-model').value.trim() : null;
  if (!model) return;
  api.post('/api/model', { name: S.sel, model }).then(r => { if (!r.model) toast('That model id is not valid', 'var(--bad)'); S.brainKey = ''; loadDetail(); });
});

// ======================================================================= talk
function renderTo() {
  const all = S.to.has('*'), agents = S.st?.agents || [];
  $('to').innerHTML = `<span class="chip ${all ? 'on' : ''}" data-n="*">Everyone</span><span class="chip ${!all && S.to.has('Sol') ? 'on' : ''}" data-n="Sol" title="Sol, the mentor: ask for advice or to pass something on">🧙 Sol</span>` + agents.map(a =>
    `<span class="chip ${!all && S.to.has(a.name) ? 'on' : ''}" data-n="${esc(a.name)}"><span class="dot" style="background:${a.color}"></span>${esc(a.name)}</span>`).join('');
}
$('to').onclick = e => {
  const c = e.target.closest('.chip'); if (!c) return;
  const n = c.dataset.n;
  if (n === '*') S.to = new Set(['*']);
  else { if (S.to.has('*')) S.to = new Set(); S.to.has(n) ? S.to.delete(n) : S.to.add(n); if (!S.to.size) S.to = new Set(['*']); }
  renderTo();
};
let chatKey = '';
function renderChat(force) {
  const c = S.st?.chat || [], el = $('chat'), key = JSON.stringify(c);
  if (key === chatKey && !force) return;
  chatKey = key;
  const stick = el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
  el.innerHTML = c.length ? c.map(m => m.from === 'You'
    ? `<div class="bub me"><b style="color:var(--you)">You → ${esc(m.to)}</b>${esc(m.text)}</div>`
    : m.review ? `<div class="bub" style="border-left:3px solid var(--gold)"><b style="color:var(--gold)">🧙 Sol's review · day ${m.tick}</b>${esc(m.text)}</div>`
    : `<div class="bub"><b style="color:${m.color}">${esc(m.from)}</b>${m.pending ? '<span class="muted typing">thinking</span>' : esc(m.text)}${(m.changes || []).map(c => `<div class="tag" style="margin-top:4px;color:var(--gold)">${esc(c)}</div>`).join('')}</div>`).join('')
    : '<p class="muted">Pick who to talk to below and say hello. Ask what they are up to, give them a task, or tell them a story.</p>';
  if (stick || force) el.scrollTop = el.scrollHeight;
}
async function send() {
  const m = $('msg').value.trim(); if (!m) return;
  $('msg').value = '';
  const r = await api.post('/api/speak', { to: S.to.has('*') ? 'all' : [...S.to], message: m });
  if (!r.delivered?.length) toast('Nobody received that — are they still alive?', 'var(--bad)');
  poll();
}
$('send').onclick = send;
$('msg').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
$('auth').onchange = e => api.post('/api/control', { authority: e.target.value });
$('gm').onchange = e => api.post('/api/control', { gm_model: e.target.value });
$('solm').onchange = e => api.post('/api/control', { sol_model: e.target.value });
$('discoveries').onclick = e => { const g = e.target.closest('[data-goto]'); if (g) select(g.dataset.goto); };

// ======================================================================= world feed
const FILTERS = { all: 'All', sol: '🧙 Sol', talk: '💬 Talk', life: '❤️ Life', making: '🔨 Making', ideas: '💡 Ideas', explore: '🧭 Exploring', survival: '🍎 Food' };
const KIND_FILTER = { sol: 'sol', discovery: 'ideas', attempt: 'ideas', goal: 'ideas', care: 'life', birth: 'life', death: 'life', love: 'life', gift: 'life', build: 'making', craft: 'making', farm: 'making',
  idea: 'ideas', explore: 'explore', food: 'survival', role: 'life', brain: 'life' };
const KIND_ICON = { sol: '🧙', discovery: '💡', attempt: '✨', goal: '🎯', care: '🍼', birth: '👶', death: '🪦', love: '❤️', gift: '🎁', build: '🏗️', craft: '🔧', farm: '🌾', idea: '💡', explore: '🧭', food: '🍎', role: '🎭', brain: '🧠', talk: '💬' };
$('filters').innerHTML = Object.entries(FILTERS).map(([k, l]) => `<span class="chip ${k === 'all' ? 'on' : ''}" data-f="${k}">${l}</span>`).join('');
$('filters').onclick = e => { const c = e.target.closest('.chip'); if (!c) return; S.filter = c.dataset.f; for (const x of $('filters').children) x.classList.toggle('on', x === c); renderFeed(S.st, true); };
let feedKey = '';
function renderFeed(st, force) {
  const items = [...st.events.map(e => ({ ...e, f: KIND_FILTER[e.kind] || 'all' })),
    ...st.talk.map(t => ({ tick: t.tick, agent: t.from, color: t.color, kind: 'talk', f: 'talk', text: `→ ${t.to === 'all' ? 'everyone' : t.to === 'Human' ? 'you' : t.to}: “${t.text}”` }))]
    .filter(i => S.filter === 'all' || i.f === S.filter).sort((a, b) => b.tick - a.tick).slice(0, 120);
  const key = S.filter + JSON.stringify(items.slice(0, 5)) + items.length;
  if (key === feedKey && !force) return;
  feedKey = key;
  $('feed').innerHTML = items.map(i => `<div class="item ${i.kind === 'idea' ? 'idea' : ''}"><span class="day">day ${i.tick}</span>
    <div>${KIND_ICON[i.kind] || '•'} <span class="who" data-goto="${esc(i.agent)}" style="color:${i.color}">${esc(i.agent)}</span> ${esc(i.text)}</div></div>`).join('')
    || '<p class="muted">Nothing here yet.</p>';
}
$('feed').onclick = e => { const g = e.target.closest('[data-goto]'); if (g) select(g.dataset.goto); };

// ======================================================================= stats (small multiples, one measure each, shared crosshair)
const METRICS = [['population', 'Population'], ['hunger', 'Average hunger'], ['food', 'Food carried'], ['explored', 'Explored %'],
  ['structures', 'Structures'], ['farms', 'Farm plots'], ['objects', 'Objects'], ['ideas', 'Ideas'], ['discoveries', 'Discoveries']];
$('charts').innerHTML = METRICS.map(([k, l]) => `<div class="chart"><div class="title"><span>${l}</span><b id="v-${k}">–</b></div><canvas id="c-${k}" data-k="${k}"></canvas></div>`).join('');
async function loadStats() { S.stats = await api.get('/api/stats'); drawCharts(); }
function drawCharts() {
  const data = S.stats; if (!data.length) return;
  const css = getComputedStyle(document.documentElement), line = css.getPropertyValue('--accent').trim(), grid = '#2c343e', ink = '#8590a0';
  for (const [k] of METRICS) {
    const c = $('c-' + k), dpr = devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr; c.height = h * dpr;
    const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    const ys = data.map(d => d[k]), max = Math.max(1, ...ys), padL = 26, padB = 14, pw = w - padL - 6, ph = h - padB - 6;
    const X = i => padL + (data.length === 1 ? pw : i / (data.length - 1) * pw), Y = v => 6 + ph - v / max * ph;
    g.font = '10px system-ui'; g.fillStyle = ink; g.strokeStyle = grid; g.lineWidth = 1;
    (max >= 4 ? [0, .5, 1] : [0, 1]).forEach(f => { const y = Y(max * f); g.beginPath(); g.moveTo(padL, y); g.lineTo(w - 6, y); g.stroke(); g.textAlign = 'right'; g.fillText(fmt(Math.round(max * f)), padL - 4, y + 3); });
    g.textAlign = 'left'; g.fillText('day ' + data[0].day, padL, h - 2); g.textAlign = 'right'; g.fillText('day ' + data[data.length - 1].day, w - 6, h - 2);
    g.strokeStyle = line; g.lineWidth = 2; g.lineJoin = 'round'; g.beginPath();
    ys.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))); g.stroke();
    const i = S.hover ?? data.length - 1;
    if (S.hover != null) { g.strokeStyle = '#b4bcc8'; g.lineWidth = 1; g.beginPath(); g.moveTo(X(i), 6); g.lineTo(X(i), 6 + ph); g.stroke(); }
    g.fillStyle = line; g.strokeStyle = '#20262e'; g.lineWidth = 2; g.beginPath(); g.arc(X(i), Y(ys[i]), 4.5, 0, 7); g.fill(); g.stroke();
    $('v-' + k).textContent = fmt(ys[i]) + (k === 'explored' ? '%' : '');
  }
  const d = data[S.hover ?? data.length - 1];
  $('readout').innerHTML = `<b>Day ${d.day}</b> — ` + METRICS.map(([k, l]) => `${l}: <b>${fmt(d[k])}${k === 'explored' ? '%' : ''}</b>`).join(' · ') + ` · Deaths so far: <b>${d.deaths}</b>`;
  if ($('stats-table').checked) {
    const step = Math.max(1, Math.ceil(data.length / 30)), rows = data.filter((_, i) => i % step === 0 || i === data.length - 1).reverse();
    $('table').innerHTML = `<table><tr><th>Day</th>${METRICS.map(([, l]) => `<th>${l}</th>`).join('')}</tr>` +
      rows.map(r => `<tr><td>${r.day}</td>${METRICS.map(([k]) => `<td>${fmt(r[k])}</td>`).join('')}</tr>`).join('') + '</table>';
  } else $('table').innerHTML = '';
}
$('charts').addEventListener('pointermove', e => {
  const c = e.target.closest('canvas'); if (!c || !S.stats.length) return;
  const r = c.getBoundingClientRect(), f = Math.min(1, Math.max(0, (e.clientX - r.left - 26) / (r.width - 32)));
  S.hover = Math.round(f * (S.stats.length - 1)); drawCharts();
});
$('charts').addEventListener('pointerleave', () => { S.hover = null; drawCharts(); });
$('stats-table').onchange = drawCharts;

// ======================================================================= settings
async function loadSaves() {
  const saves = await api.get('/api/saves');
  $('saves').innerHTML = saves.length ? saves.map(s => `<div class="save"><span><b>${esc(s.name)}</b><br><span class="muted small">day ${s.day ?? '?'} · ${esc(s.saved)} · ${s.size_kb} KB</span></span>
    <button class="btn" data-load="${esc(s.name)}">Load</button></div>`).join('') : '<p class="muted">No saves yet.</p>';
  renderUsage();
}
$('saves').onclick = async e => {
  const b = e.target.closest('[data-load]'); if (!b) return;
  if (!confirm(`Load "${b.dataset.load}"? The current world will be replaced (save it first if you want to keep it).`)) return;
  const r = await api.post('/api/load', { name: b.dataset.load });
  if (r.error) return toast(r.error, 'var(--bad)');
  resetView(); toast(`Loaded "${b.dataset.load}" (day ${r.day})`, 'var(--good)');
};
$('save').onclick = async () => {
  const r = await api.post('/api/save', { name: $('save-name').value.trim() });
  $('save-name').value = ''; toast(`💾 Saved as "${r.saved}"`, 'var(--good)'); loadSaves();
};
$('new').onclick = async () => {
  if (!confirm('Start a brand-new world? The current one will be replaced (save it first if you want to keep it).')) return;
  await api.post('/api/new', { seed: $('seed').value.trim() });
  resetView(); toast('🌍 A new world begins', 'var(--good)');
};
function renderUsage() {
  const u = S.st?.usage; if (!u) return;
  const rows = Object.entries(u.models);
  $('usage').innerHTML = rows.length ? `<table><tr><th>Model</th><th>Calls</th><th>Input</th><th>Output</th><th>Cost</th></tr>` +
    rows.map(([m, x]) => `<tr><td>${esc(m)}</td><td>${fmt(x.calls)}</td><td>${fmt(x.input)}</td><td>${fmt(x.output)}</td><td>${x.cost != null ? '$' + x.cost.toFixed(3) : '–'}</td></tr>`).join('') + '</table>'
    + '<p class="muted small">Local models are free. For Claude cost estimates start the hub with --price MODEL=IN,OUT (USD per million tokens).</p>'
    : '<p class="muted">No model calls yet.</p>';
}
async function resetView() {
  S.disp = {}; S.lastEvent = null; S.stats = []; closeProfile(); drawn.length = 0;
  await loadWorld(); poll();
}

// ======================================================================= toasts
function toast(text, color = 'var(--accent)', name) {
  const t = document.createElement('div');
  t.className = 'toast'; t.style.borderLeftColor = color; t.textContent = text;
  if (name) t.onclick = () => select(name);
  $('toasts').appendChild(t);
  setTimeout(() => t.remove(), 6000);
  while ($('toasts').children.length > 4) $('toasts').firstChild.remove();
}
const TOAST_KINDS = { discovery: '#ffd93d', birth: '#f15bb5', death: '#8590a0', idea: '#ffd93d', brain: '#9085e9' };
function toastNewEvents(events) {
  const key = e => `${e.tick}|${e.agent}|${e.text}`;
  if (S.lastEvent === null) { S.lastEvent = events.length ? key(events[events.length - 1]) : ''; return; }
  const i = events.findIndex(e => key(e) === S.lastEvent);
  const fresh = i >= 0 ? events.slice(i + 1) : events.slice(-3);
  if (events.length) S.lastEvent = key(events[events.length - 1]);
  for (const e of fresh) if (TOAST_KINDS[e.kind]) toast(`${KIND_ICON[e.kind]} ${e.agent} ${e.text}`, TOAST_KINDS[e.kind], e.agent);
}

// ======================================================================= keyboard & help
function help(open) { $('help').hidden = !open; if (!open) store.set('seenHelp', true); }
$('b-help').onclick = () => help(true);
$('help-close').onclick = () => help(false);
$('help').onclick = e => { if (e.target === $('help')) help(false); };
document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea, select')) { if (e.key === 'Escape') e.target.blur(); return; }
  const k = e.key;
  if (k === ' ') { e.preventDefault(); $('b-pause').click(); }
  else if (k === 'n' || k === 'N') $('b-step').click();
  else if (k === '+' || k === '=') setZoom(S.zoom * 1.25);
  else if (k === '-' || k === '_') setZoom(S.zoom / 1.25);
  else if (k === '0') fitZoom();
  else if (k === 'f' || k === 'F') { $('follow').checked = !$('follow').checked; if (S.sel) centerOn(S.sel); }
  else if (k === '/') { e.preventDefault(); showTab('talk'); $('msg').focus(); }
  else if (k === '?') help(true);
  else if (k === 'Escape') { if (!$('help').hidden) help(false); else if (S.sel) closeProfile(); }
  else if ('12345'.includes(k) && k.length === 1) showTab(['people', 'talk', 'world', 'stats', 'settings'][+k - 1]);
});

// ======================================================================= main loop
let polling = false, pollAgain = false;
async function poll() {
  if (polling) { pollAgain = true; return; }          // one more right after the one in flight (e.g. after a button press)
  polling = true;
  try {
    const st = await api.get('/api/state');
    S.st = st; S.agents = st.agents; spread(st.agents);
    if (st.tiles.length === S.H) syncTiles(st.tiles);
    renderTop(st);
    if (!S.sel) renderList(st);
    if ($('to').children.length !== st.agents.length + 2) renderTo();
    if (document.activeElement !== $('auth')) $('auth').value = st.authority;
    renderChat(); renderFeed(st); toastNewEvents(st.events);
    $('discoveries').innerHTML = st.discoveries.length ? st.discoveries.slice().reverse().map(d => `<div class="disc"><b>${esc(d.name)}</b>
      <span class="muted">by <span class="who" data-goto="${esc(d.by)}" style="color:${d.color};cursor:pointer">${esc(d.by)}</span>, day ${d.tick}</span>
      <div>${esc(d.description)}</div><span class="eff">⚡ ${esc(d.meaning)}</span></div>`).join('')
      : '<p class="muted small">Nothing yet. When an agent attempts or invents something genuinely useful, it shows up here and changes the rules for everyone.</p>';
    const so = st.sol;
    $('solcard').innerHTML = `<b style="color:var(--gold)">🧙 Sol, the mentor</b> <span class="muted small">reviews everyone every 20 days · next in ${so.next_in} days</span>
      <button class="btn" id="sol-now" style="float:right;padding:3px 10px">Review now</button>
      <div class="small" style="margin-top:6px">${so.log.length ? esc(so.log[so.log.length - 1].note || so.log[so.log.length - 1].speech) : 'Sol hasn\'t reviewed the society yet. Pick 🧙 Sol below to talk to Sol.'}</div>`;
    $('sol-now').onclick = () => api.post('/api/sol').then(() => toast('🧙 Sol is reviewing the society…', '#ffd93d'));
    if (document.activeElement !== $('solm')) $('solm').value = { 'claude-haiku-5-5': 'haiku', 'claude-sonnet-5-5': 'sonnet', 'claude-opus-5-5': 'opus' }[so.model] || (so.model.startsWith('local:') ? 'smart' : 'local');
    $('blueprints').innerHTML = st.blueprints.length ? st.blueprints.slice().reverse().map(b => `<div class="disc" style="background:var(--panel-2);border-color:var(--line)">${iconFor(b.kind)} <b>${esc(b.kind)}</b>
      <span class="muted">${b.by ? 'designed by ' + esc(b.by) : ''}</span><div>${esc(b.description)}</div>
      <span class="eff" style="color:var(--text-2)">needs ${Object.entries(b.cost).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing'}</span></div>`).join('')
      : '<p class="muted small">No blueprints yet. The first time someone builds a new kind of building, its cost and purpose are worked out and shared here.</p>';
    if (document.activeElement !== $('gm')) $('gm').value = { 'claude-haiku-5-5': 'haiku', 'claude-sonnet-5-5': 'sonnet', 'claude-opus-5-5': 'opus' }[st.gm_model] || (st.gm_model.startsWith('local:') ? 'smart' : 'local');
    if (S.tab === 'settings') renderUsage();
  } catch (e) { console.error(e); }
  polling = false;
  if (pollAgain) { pollAgain = false; poll(); }
}
async function loadWorld() {
  const w = await api.get('/api/world');
  S.W = w.width; S.H = w.height; S.tiles = w.tiles;
  cv.width = bg.width = S.W * T; cv.height = bg.height = S.H * T;
  syncTiles(w.tiles);
}
(async () => {
  if (innerWidth < 1000) document.querySelector('.legend').open = false;
  await loadWorld();
  const z = store.get('zoom', null);
  z ? setZoom(z) : fitZoom();
  showTab(store.get('tab', 'people'));
  await poll();
  requestAnimationFrame(drawFrame);
  setInterval(poll, 700);
  setInterval(() => { if (S.sel && S.tab === 'people') loadDetail(); }, 1500);
  setInterval(() => { if (S.tab === 'stats') loadStats(); }, 4000);
  if (!store.get('seenHelp', false)) help(true);
})();
