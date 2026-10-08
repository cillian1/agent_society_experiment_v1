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
// the world's calendar: one turn is one hour
const cal = () => S.st?.calendar || { start_hour: 6, hours_per_day: 24, days_per_month: 30, months: ['Thawing', 'Blossom', 'Sowing', 'Greening', 'Highsun', 'Longday', 'Ripening', 'Harvest', 'Leaffall', 'Mistmoon', 'Frost', 'Deepwinter'] };
function ts(tick, long) {
  if (typeof tick !== 'number') return '?';
  const c = cal(), h = tick + c.start_hour, days = Math.floor(h / c.hours_per_day), hour = h % c.hours_per_day;
  const day = days % c.days_per_month + 1, m = Math.floor(days / c.days_per_month) % 12, year = Math.floor(days / (c.days_per_month * 12)) + 1;
  const hh = String(hour).padStart(2, '0') + ':00';
  return long ? `${c.months[m]} ${day}, year ${year} · ${hh}` : `${c.months[m].slice(0, 3)} ${day} · ${hh}`;
}
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
  zoom: 1, disp: {}, offset: {}, head: {}, inside: new Set(), dark: 0, props: [], water: [], lastEvent: null, stats: [], hover: null, brainKey: '',
};

// ======================================================================= map (isometric)
// The world is drawn as diamonds: tile (x, y) sits at iso(x, y). The ground is painted once into `bg` (and repainted
// tile by tile when it changes); trees, rocks, buildings and people are drawn every frame, back to front.
const TW = 40, TH = 20, TOP = 80, PAD = 24;
const cv = $('map'), ctx = cv.getContext('2d');
const bg = document.createElement('canvas'), bctx = bg.getContext('2d');
const fogc = document.createElement('canvas'), fctx = fogc.getContext('2d');
const FOG_SCALE = 4, BG_SCALE = 2, SPRITE_SCALE = 4;   // ground cache and sprites are kept sharper than 1:1
let WW = 0, WH = 0;                                   // world size in world pixels; the canvas itself is screen-sized
S.cam = { x: 0, y: 0 };
const scroller = $('mapscroll');
const drawn = [];
const rnd = (x, y, k = 0) => { let h = (x * 374761393 + y * 668265263 + k * 2147483647) >>> 0; h = ((h ^ (h >>> 13)) * 1274126177) >>> 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967296; };
const hash = s => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
const iso = (x, y) => [(x - y) * TW / 2 + S.H * TW / 2 + PAD, (x + y) * TH / 2 + TOP];
const ground = (x, y) => iso(x + .5, y + .5);                       // centre of a tile on screen
function unIso(px, py) {                                             // screen pixel -> fractional tile
  const u = (px - S.H * TW / 2 - PAD) / (TW / 2), v = (py - TOP) / (TH / 2);
  return { fx: (u + v) / 2, fy: (v - u) / 2 };
}
function diamond(c, x, y, w = 1, h = 1, lift = 0) {
  const p = [iso(x, y), iso(x + w, y), iso(x + w, y + h), iso(x, y + h)];
  c.beginPath(); p.forEach(([a, b], i) => i ? c.lineTo(a, b - lift) : c.moveTo(a, b - lift)); c.closePath();
  return p;
}
const shade = (hex, k) => {                                          // lighten (k > 0) or darken (k < 0) a #rrggbb colour
  const n = parseInt(hex.slice(1), 16), f = v => Math.max(0, Math.min(255, Math.round(k > 0 ? v + (255 - v) * k : v * (1 + k))));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
};

// ---- ground
const GROUND = { grass: '#4f9a47', food: '#4f9a47', tree: '#478f40', sprout: '#7a5634', crop: '#7a5634', water: '#2f6fb5',
  sand: '#d8c68a', rock: '#8c8a80', structure: '#8f7a55' };
function paintTile(x, y, c = bctx) {
  const t = S.tiles[y][x], v = rnd(x, y), base = GROUND[t] || '#444';
  const col = shade(base, (v - .5) * .12);
  diamond(c, x, y); c.fillStyle = col; c.strokeStyle = col; c.lineWidth = .7; c.fill(); c.stroke();
  const [cx, cy] = ground(x, y);
  if (t === 'grass' || t === 'food' || t === 'tree') {
    c.strokeStyle = 'rgba(25,80,30,.32)'; c.lineWidth = .8;
    for (let i = 0; i < 3; i++) { const a = cx + (rnd(x, y, i + 1) - .5) * TW * .5, b = cy + (rnd(x, y, i + 9) - .5) * TH * .45; c.beginPath(); c.moveTo(a, b); c.lineTo(a - 1.5, b - 3); c.moveTo(a, b); c.lineTo(a + 1.5, b - 3); c.stroke(); }
    if (t === 'grass' && rnd(x, y, 20) > .92) { c.fillStyle = rnd(x, y, 21) > .5 ? '#fff3a0' : '#f8c8e0'; c.beginPath(); c.arc(cx + (rnd(x, y, 22) - .5) * TW * .4, cy + (rnd(x, y, 23) - .5) * TH * .4, 1.8, 0, 7); c.fill(); }
  }
  if (t === 'sand') { c.fillStyle = 'rgba(120,95,40,.35)'; for (let i = 0; i < 5; i++) c.fillRect(cx + (rnd(x, y, i + 30) - .5) * TW * .5, cy + (rnd(x, y, i + 40) - .5) * TH * .5, 1.5, 1.5); }
  if (t === 'rock') { c.fillStyle = 'rgba(60,60,60,.3)'; for (let i = 0; i < 4; i++) c.fillRect(cx + (rnd(x, y, i + 50) - .5) * TW * .5, cy + (rnd(x, y, i + 60) - .5) * TH * .5, 2, 1.5); }
  if (t === 'sprout' || t === 'crop') {                              // tilled furrows
    c.strokeStyle = 'rgba(50,30,15,.45)'; c.lineWidth = 1.2;
    for (let i = 1; i < 4; i++) { const [a1, b1] = iso(x + i / 4, y + .12), [a2, b2] = iso(x + i / 4, y + .88); c.beginPath(); c.moveTo(a1, b1); c.lineTo(a2, b2); c.stroke(); }
  }
  if (t === 'water') {
    c.fillStyle = 'rgba(10,40,90,.18)'; diamond(c, x + .15, y + .15, .7, .7); c.fill();
    const bank = (a, b) => { c.fillStyle = '#6e5a3c'; c.beginPath(); c.moveTo(...a); c.lineTo(...b); c.lineTo(b[0], b[1] + 5); c.lineTo(a[0], a[1] + 5); c.closePath(); c.fill(); };
    const up = S.tiles[y - 1]?.[x], left = S.tiles[y]?.[x - 1];       // land behind the water looks raised
    if (up && up !== 'water') bank(iso(x, y), iso(x + 1, y));
    if (left && left !== 'water') bank(iso(x, y + 1), iso(x, y));
    c.strokeStyle = 'rgba(220,240,255,.55)'; c.lineWidth = 2;                          // foam where water meets land
    const p = [iso(x, y), iso(x + 1, y), iso(x + 1, y + 1), iso(x, y + 1)];
    [[0, -1, 0, 1], [1, 0, 1, 2], [0, 1, 2, 3], [-1, 0, 3, 0]].forEach(([dx, dy, i, j]) => {
      const n = S.tiles[y + dy]?.[x + dx]; if (n && n !== 'water') { c.beginPath(); c.moveTo(...p[i]); c.lineTo(...p[j]); c.stroke(); } });
  }
}
function syncTiles(next) {
  S.tiles = next; let changed = false;
  for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) {
    if (!drawn[y]) drawn[y] = [];
    if (drawn[y][x] !== next[y][x]) { drawn[y][x] = next[y][x]; changed = true; }
  }
  if (changed) {                                                      // repaint back to front so seams stay clean
    for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) paintTile(x, y);
    S.props = []; S.water = [];
    for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) {
      const t = next[y][x];
      if (PROP[t]) S.props.push({ x, y, t, v: Math.floor(rnd(x, y, 7) * 3) });
      if (t === 'water' && rnd(x, y, 8) > .6) S.water.push({ x, y, ph: rnd(x, y, 9) * 6.3 });
    }
  }
}

// ---- props (cached sprites, anchored at the tile centre)
const SPR = {};
function sprite(key, w, h, draw) {
  if (!SPR[key]) {
    const c = document.createElement('canvas'); c.width = w * SPRITE_SCALE; c.height = h * SPRITE_SCALE;
    const g = c.getContext('2d'); g.scale(SPRITE_SCALE, SPRITE_SCALE); draw(g, w, h); SPR[key] = c;
  }
  return SPR[key];
}
const blob = (c, x, y, r, col) => { c.fillStyle = col; c.beginPath(); c.arc(x, y, r, 0, 7); c.fill(); };
const shadow = (c, x, y, rx, ry, a = .28) => { c.fillStyle = `rgba(0,0,0,${a})`; c.beginPath(); c.ellipse(x, y, rx, ry, 0, 0, 7); c.fill(); };
const PROP = {
  tree: { w: 46, h: 64, ax: 23, ay: 56, draw(c, v) {
    shadow(c, 23, 56, 15, 6);
    c.fillStyle = '#5b3d22'; c.fillRect(21, 38, 5, 18);
    if (v === 1) {                                                    // pine
      [[44, 15, '#1f5a2c'], [34, 12, '#27703a'], [24, 9, '#2f8645']].forEach(([y, r, col]) => {
        c.fillStyle = col; c.beginPath(); c.moveTo(23 - r, y); c.lineTo(23, y - 18); c.lineTo(23 + r, y); c.closePath(); c.fill(); });
    } else {
      const k = v === 2 ? 1.12 : 1;
      blob(c, 23, 32, 15 * k, '#245c2a'); blob(c, 18, 27, 11 * k, '#2e7a35'); blob(c, 28, 24, 9 * k, '#3c9744'); blob(c, 21, 20, 5 * k, '#4fae55');
    }
  } },
  rock: { w: 42, h: 36, ax: 21, ay: 28, draw(c, v) {
    shadow(c, 21, 28, 16, 6);
    c.fillStyle = '#7f848c'; c.beginPath(); c.moveTo(5, 27); c.lineTo(9, 13); c.lineTo(19, 6 + v * 2); c.lineTo(31, 10); c.lineTo(37, 26); c.closePath(); c.fill();
    c.fillStyle = '#a5aab2'; c.beginPath(); c.moveTo(9, 13); c.lineTo(19, 6 + v * 2); c.lineTo(22, 16); c.lineTo(12, 20); c.closePath(); c.fill();
    c.fillStyle = '#62666d'; c.beginPath(); c.moveTo(22, 16); c.lineTo(31, 10); c.lineTo(37, 26); c.lineTo(24, 28); c.closePath(); c.fill();
  } },
  food: { w: 36, h: 32, ax: 18, ay: 25, draw(c) {
    shadow(c, 18, 25, 13, 5);
    blob(c, 18, 17, 11, '#2b6a2f'); blob(c, 14, 14, 7, '#37803b'); blob(c, 22, 13, 6, '#3f8f44');
    c.fillStyle = '#e0334e'; [[-6, 3], [5, 0], [0, 6], [-1, -4], [7, 6], [-7, -2]].forEach(([a, b]) => blob(c, 18 + a, 16 + b, 2.3, '#e0334e'));
  } },
  sprout: { w: 30, h: 22, ax: 15, ay: 17, draw(c) {
    c.strokeStyle = '#8fe36b'; c.lineWidth = 2;
    [[-6, 0], [0, -3], [6, 0]].forEach(([a, b]) => { c.beginPath(); c.moveTo(15 + a * .5, 17); c.quadraticCurveTo(15 + a, 11 + b, 15 + a * 1.3, 7 + b); c.stroke(); });
  } },
  crop: { w: 34, h: 36, ax: 17, ay: 28, draw(c) {
    for (let i = 0; i < 6; i++) { const a = 6 + i * 4.4, b = 28 - (i % 2) * 3; c.strokeStyle = '#c9a63a'; c.lineWidth = 1.6; c.beginPath(); c.moveTo(a, b); c.lineTo(a - 1, b - 18); c.stroke(); c.fillStyle = '#f3d35a'; c.beginPath(); c.ellipse(a - 1, b - 19, 2, 4, 0, 0, 7); c.fill(); }
  } },
};
function drawProp(p, fade) {
  const P = PROP[p.t], img = sprite(p.t + p.v, P.w, P.h, c => P.draw(c, p.v)), [gx, gy] = ground(p.x, p.y);
  if (fade) ctx.globalAlpha = .45;
  ctx.drawImage(img, gx - P.ax, gy - P.ay, P.w, P.h);
  ctx.globalAlpha = 1;
}

// ---- buildings
const ICONS = [['bridge', '🌉'], ['dock', '⚓'], ['pier', '⚓'], ['house', '🏠'], ['hut', '🛖'], ['shelter', '🏕️'], ['home', '🏠'], ['wall', '🧱'],
  ['fence', '🧱'], ['sign', '🪧'], ['fire', '🔥'], ['hearth', '🔥'], ['storage', '📦'], ['store', '📦'], ['granary', '📦'], ['barn', '🏚️'], ['farm', '🌾'], ['garden', '🌷'],
  ['well', '⛲'], ['temple', '⛩️'], ['shrine', '⛩️'], ['school', '🏫'], ['market', '🏪'], ['tower', '🗼'], ['workshop', '🔨'], ['forge', '⚒️'], ['bed', '🛏️'], ['path', '🟫'],
  ['road', '🟫'], ['floor', '🟫'], ['bench', '🪑'], ['table', '🪑'], ['monument', '🗿'], ['statue', '🗿'], ['gate', '⛩️'], ['door', '🚪'], ['boat', '⛵'], ['raft', '⛵']];
const FUNC_ICON = { storage: '📦', home: '🏠', fire: '🔥', well: '⛲', workshop: '🔨' };
const iconFor = (k, f) => { k = (k || '').toLowerCase(); for (const [w, i] of ICONS) if (k.includes(w)) return i; return FUNC_ICON[f] || '🏗️'; };
const FLAT = ['bridge', 'path', 'road', 'floor', 'dock', 'pier', 'field', 'farm', 'garden', 'plaza', 'square', 'paving', 'track', 'trail', 'raft'];
const LOW = ['wall', 'fence', 'barrier', 'hedge'];
const STYLE = {                       // walls, roof
  storage: ['#a7754a', '#b5523b'], home: ['#e6d3a6', '#c0603f'], workshop: ['#9c8f80', '#56708a'],
  well: ['#9aa0a8', '#7b5a3a'], fire: ['#a08060', '#8a4a32'], '': ['#cdb88d', '#6f8f5a'],
};
const isFlat = s => FLAT.some(w => s.kind.toLowerCase().includes(w));
const isLow = s => !s.walkable && LOW.some(w => s.kind.toLowerCase().includes(w));
const wallH = s => isLow(s) ? 9 : 14 + 5 * Math.min(s.w, s.h);

function box(s, H, wall, alpha) {     // the two visible walls of a building's footprint
  const [, R, B, L] = [iso(s.x, s.y), iso(s.x + s.w, s.y), iso(s.x + s.w, s.y + s.h), iso(s.x, s.y + s.h)];
  ctx.globalAlpha = alpha;
  ctx.fillStyle = shade(wall, -.12); ctx.beginPath(); ctx.moveTo(...L); ctx.lineTo(...B); ctx.lineTo(B[0], B[1] - H); ctx.lineTo(L[0], L[1] - H); ctx.closePath(); ctx.fill();
  ctx.fillStyle = shade(wall, -.3); ctx.beginPath(); ctx.moveTo(...B); ctx.lineTo(...R); ctx.lineTo(R[0], R[1] - H); ctx.lineTo(B[0], B[1] - H); ctx.closePath(); ctx.fill();
  ctx.globalAlpha = 1;
  return { R, B, L };
}
function drawBuilding(s, t) {
  const func = s.func || '', [wall, roof] = STYLE[func] || STYLE[''], occupied = S.inside.has(s.x + ',' + s.y);
  const [cx, cy] = iso(s.x + s.w / 2, s.y + s.h / 2);
  if (!s.done) {                                                       // construction site: foundation, rising walls, scaffold
    const p = s.work ? Math.min(1, s.progress / s.work) : 0, H = wallH(s);
    diamond(ctx, s.x, s.y, s.w, s.h); ctx.fillStyle = 'rgba(160,125,80,.75)'; ctx.fill();
    ctx.setLineDash([4, 3]); ctx.strokeStyle = 'rgba(255,230,160,.8)'; ctx.lineWidth = 1.2; ctx.stroke(); ctx.setLineDash([]);
    if (!isFlat(s)) {
      box(s, H * p, wall, .85);
      ctx.strokeStyle = '#6b4a2b'; ctx.lineWidth = 2;
      [iso(s.x, s.y), iso(s.x + s.w, s.y), iso(s.x + s.w, s.y + s.h), iso(s.x, s.y + s.h)].forEach(([a, b]) => { ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(a, b - H - 4); ctx.stroke(); });
      ctx.lineWidth = 1; ctx.beginPath(); diamond(ctx, s.x, s.y, s.w, s.h, H * .6); ctx.stroke();
    }
    return;
  }
  if (isFlat(s)) {                                                      // paths, bridges, fields: on the ground
    diamond(ctx, s.x, s.y, s.w, s.h);
    const water = S.tiles[s.y]?.[s.x] === 'structure' && s.kind.toLowerCase().match(/bridge|dock|pier|raft/);
    ctx.fillStyle = water ? '#9a6b3f' : s.kind.toLowerCase().match(/field|farm|garden/) ? '#6f5232' : '#b39a6e'; ctx.fill();
    ctx.strokeStyle = 'rgba(0,0,0,.25)'; ctx.lineWidth = 1;
    if (water) for (let i = 1; i < 4; i++) { const [a1, b1] = iso(s.x + i / 4 * s.w, s.y), [a2, b2] = iso(s.x + i / 4 * s.w, s.y + s.h); ctx.beginPath(); ctx.moveTo(a1, b1); ctx.lineTo(a2, b2); ctx.stroke(); }
    ctx.stroke();
    return;
  }
  if (func === 'fire' && s.w * s.h === 1) {                           // camp fire: stone ring and flickering flames
    shadow(ctx, cx, cy, 13, 6, .3);
    for (let i = 0; i < 8; i++) { const a = i / 8 * 6.28; blob(ctx, cx + Math.cos(a) * 9, cy + Math.sin(a) * 4.5, 2.8, i % 2 ? '#8a8f96' : '#a3a8af'); }
    for (let i = 0; i < 3; i++) {
      const f = Math.sin(t * 9 + i * 2) * 2, hgt = 12 + f + (i === 1 ? 5 : 0), x0 = cx + (i - 1) * 4;
      ctx.fillStyle = ['#ff8a2a', '#ffd23f', '#ff6a1a'][i]; ctx.beginPath(); ctx.moveTo(x0 - 4, cy); ctx.quadraticCurveTo(x0 - 3, cy - hgt * .6, x0 + f * .3, cy - hgt); ctx.quadraticCurveTo(x0 + 3, cy - hgt * .6, x0 + 4, cy); ctx.fill();
    }
    return;
  }
  if (func === 'well' && s.w * s.h === 1) {
    shadow(ctx, cx, cy + 2, 12, 5, .3);
    ctx.fillStyle = '#8b9098'; ctx.fillRect(cx - 10, cy - 10, 20, 10); ctx.beginPath(); ctx.ellipse(cx, cy, 10, 4.5, 0, 0, 3.15); ctx.fill();
    ctx.fillStyle = '#a9aeb5'; ctx.beginPath(); ctx.ellipse(cx, cy - 10, 10, 4.5, 0, 0, 7); ctx.fill();
    ctx.fillStyle = '#25507f'; ctx.beginPath(); ctx.ellipse(cx, cy - 10, 7, 3, 0, 0, 7); ctx.fill();
    ctx.strokeStyle = '#5b3d22'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(cx - 9, cy - 10); ctx.lineTo(cx - 9, cy - 26); ctx.moveTo(cx + 9, cy - 10); ctx.lineTo(cx + 9, cy - 26); ctx.stroke();
    ctx.fillStyle = '#8a4a32'; ctx.beginPath(); ctx.moveTo(cx - 13, cy - 24); ctx.lineTo(cx, cy - 32); ctx.lineTo(cx + 13, cy - 24); ctx.closePath(); ctx.fill();
    return;
  }
  const H = wallH(s), alpha = occupied ? .55 : 1;
  shadow(ctx, cx + 4, cy + 2, (s.w + s.h) * TW / 4 + 2, (s.w + s.h) * TH / 4 + 1, .22);
  const { R, B, L } = box(s, H, wall, alpha);
  ctx.globalAlpha = alpha;
  // door on the left wall, windows on the right
  const dm = [(L[0] + B[0]) / 2, (L[1] + B[1]) / 2];
  if (!isLow(s)) {
    ctx.fillStyle = '#4a321e'; ctx.beginPath(); ctx.moveTo(dm[0] - 4, dm[1] - 2); ctx.lineTo(dm[0] + 4, dm[1] + 2); ctx.lineTo(dm[0] + 4, dm[1] + 2 - 11); ctx.lineTo(dm[0] - 4, dm[1] - 2 - 11); ctx.closePath(); ctx.fill();
    const night = S.dark > .2, wm = [(B[0] + R[0]) / 2, (B[1] + R[1]) / 2 - H * .55];
    ctx.fillStyle = night && (func === 'home' || func === 'fire') ? '#ffd27a' : '#2b3a4a';
    ctx.beginPath(); ctx.moveTo(wm[0] - 4, wm[1] + 2); ctx.lineTo(wm[0] + 4, wm[1] - 2); ctx.lineTo(wm[0] + 4, wm[1] - 7); ctx.lineTo(wm[0] - 4, wm[1] - 3); ctx.closePath(); ctx.fill();
  }
  ctx.globalAlpha = 1;
  if (isLow(s)) { diamond(ctx, s.x, s.y, s.w, s.h, H); ctx.fillStyle = shade(wall, .1); ctx.fill(); return; }
  // hip roof: four faces meeting at a peak; see-through when someone is inside
  const Tp = iso(s.x, s.y), lift = H, peak = [cx, cy - H - 8 - 4 * Math.max(s.w, s.h)], o = 3;
  const up = ([a, b]) => [a, b - lift], [t2, r2, b2, l2] = [up(Tp), up(R), up(B), up(L)].map(([a, b], i) => [a + [0, o, 0, -o][i], b + [-o / 2, 0, o / 2, 0][i]]);
  ctx.globalAlpha = occupied ? .3 : 1;
  [[t2, r2, -.05], [l2, t2, .12], [l2, b2, -.12], [b2, r2, -.3]].forEach(([p, q, k]) => {
    ctx.fillStyle = shade(roof, k); ctx.beginPath(); ctx.moveTo(...p); ctx.lineTo(...q); ctx.lineTo(...peak); ctx.closePath(); ctx.fill(); });
  if (func === 'fire' || func === 'workshop') {                        // chimney with a wisp of smoke
    const ch = [peak[0] + 8, peak[1] + 8];
    ctx.fillStyle = '#6b5a4a'; ctx.fillRect(ch[0] - 2.5, ch[1] - 9, 5, 9);
    ctx.fillStyle = 'rgba(220,220,220,.35)'; for (let i = 0; i < 3; i++) blob(ctx, ch[0] + Math.sin(t * 1.5 + i) * 3, ch[1] - 13 - i * 6 - (t * 6 % 6), 3 + i, 'rgba(220,220,220,.3)');
  }
  ctx.globalAlpha = 1;
}
function buildingOverlay(s) {
  const [wx, wy] = iso(s.x + s.w / 2, s.y + s.h / 2), small = s.w * s.h === 1 && (s.func === 'fire' || s.func === 'well');
  const [cx, top] = scr(wx, wy - (!s.done ? wallH(s) + 10 : isFlat(s) ? 6 : small ? 34 : wallH(s) + 14 + 4 * Math.max(s.w, s.h)));
  if (!s.done) {
    const p = s.work ? Math.min(1, s.progress / s.work) : 0;
    bar(cx, top - 8, 44, p, '#ffd93d');
    ctx.font = 'bold 10px system-ui'; ctx.fillStyle = '#fff'; ctx.strokeStyle = 'rgba(0,0,0,.7)'; ctx.lineWidth = 3;
    const label = `🏗️ ${s.kind} ${Math.round(p * 100)}%`; ctx.strokeText(label, cx, top - 18); ctx.fillText(label, cx, top - 18);
  } else if (!isFlat(s) && !small) { ctx.font = '13px system-ui'; ctx.fillText(iconFor(s.kind, s.func), cx, top - 4); }
}
function bar(x, y, w, frac, color) {
  ctx.fillStyle = 'rgba(0,0,0,.65)'; ctx.beginPath(); ctx.roundRect(x - w / 2 - 1, y - 1, w + 2, 6, 3); ctx.fill();
  ctx.fillStyle = color; ctx.beginPath(); ctx.roundRect(x - w / 2, y, Math.max(2, w * frac), 4, 2); ctx.fill();
}

// ---- people
const SKIN = ['#f1c7a3', '#e0ac85', '#c68863', '#8d5a3b', '#f5d6b8', '#b07850'];
const HAIR = ['#2b1d14', '#5a3a1e', '#a0522d', '#d9b26a', '#1a1a1a', '#7a4a2a'];
const scaleOf = a => a.stage === 'baby' ? .55 : a.adult ? 1 : .75;
function pos(a) {
  // Walk at a steady pace, timed so a move finishes about when the next hour starts; when staying put, shuffle
  // around a little (people don't stand frozen while they work, chat or wait).
  const d = S.disp[a.name] || (S.disp[a.name] = { x: a.x, y: a.y, wx: 0, wy: 0, next: 0 });
  const [ox, oy] = S.offset[a.name] || [0, 0], now = performance.now() / 1000;
  const still = a.asleep || a.stage === 'baby';
  if (d.tx !== a.x || d.ty !== a.y) { d.tx = a.x; d.ty = a.y; d.wx = d.wy = 0; d.next = now + 1 + Math.random() * 2; }
  else if (!still && now > d.next) {                  // a small wander within the tile
    const r = a.inside ? .35 : .22, ang = Math.random() * 6.283;
    d.wx = Math.cos(ang) * r * Math.random(); d.wy = Math.sin(ang) * r * Math.random();
    d.next = now + 1.5 + Math.random() * 3;
  }
  const tx = a.x + ox + d.wx, ty = a.y + oy + d.wy, dist = Math.hypot(tx - d.x, ty - d.y);
  if (dist > 6) { d.x = tx; d.y = ty; d.moving = false; return d; }       // teleports (e.g. loading a save)
  const hour = Math.max(.35, Math.min(4, S.st?.day_seconds || S.st?.interval || 1));
  const speed = Math.max(.5, d.leg ? d.leg / (hour * .85) : 1);           // tiles per second
  if (dist > .01) {
    if (!d.moving || dist > (d.leg || 0)) d.leg = dist;                    // length of the current walk
    const k = Math.min(1, speed * S.dt / dist);
    d.x += (tx - d.x) * k; d.y += (ty - d.y) * k;
  }
  d.moving = dist > .03; if (!d.moving) d.leg = 0;
  return d;
}
function spread(agents) {
  const groups = {};
  for (const a of agents) (groups[a.x + ',' + a.y] ||= []).push(a.name);
  S.offset = {};
  for (const names of Object.values(groups)) names.forEach((n, i) => {
    if (names.length > 1) { const ang = i / names.length * Math.PI * 2; S.offset[n] = [Math.cos(ang) * .25, Math.sin(ang) * .25]; }
  });
}
function drawPerson(a, t) {
  const d = pos(a), [gx, gy] = ground(d.x, d.y), s = scaleOf(a), h = hash(a.name);
  const skin = SKIN[h % SKIN.length], hair = a.stage === 'elder' ? '#d8d8d8' : HAIR[(h >> 3) % HAIR.length];
  if (S.sel === a.name) { ctx.strokeStyle = '#ffd93d'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.ellipse(gx, gy, 13 * s + 3, 6 * s + 2, 0, 0, 7); ctx.stroke(); }
  shadow(ctx, gx, gy, 9 * s, 4 * s, .3);
  let head;
  if (a.stage === 'baby') {                                            // swaddled
    ctx.fillStyle = '#f3ead8'; ctx.beginPath(); ctx.ellipse(gx, gy - 6, 7, 5, 0, 0, 7); ctx.fill(); ctx.strokeStyle = a.color; ctx.lineWidth = 1.5; ctx.stroke();
    blob(ctx, gx - 4, gy - 8, 3.5, skin); head = [gx, gy - 14];
  } else if (a.asleep) {                                               // lying down
    ctx.fillStyle = '#7a6a55'; ctx.beginPath(); ctx.ellipse(gx, gy - 2, 13 * s, 5 * s, 0, 0, 7); ctx.fill();
    ctx.fillStyle = a.color; ctx.beginPath(); ctx.ellipse(gx + 2 * s, gy - 4 * s, 9 * s, 4 * s, 0, 0, 7); ctx.fill();
    blob(ctx, gx - 9 * s, gy - 5 * s, 4.5 * s, skin); blob(ctx, gx - 10 * s, gy - 7 * s, 3.5 * s, hair);
    head = [gx, gy - 16 * s];
  } else {
    const busy = !d.moving && /^(gather|work|tend|build|plant|craft|care)/.test(a.doing || '');
    const ph = h % 7, step = d.moving ? Math.sin(t * 9 + ph) : 0, bob = Math.abs(step) * 1.8 * s + (busy ? (Math.sin(t * 7 + ph) + 1) * 1.4 * s : 0);
    ctx.strokeStyle = '#2a2a35'; ctx.lineWidth = 2.6 * s; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(gx - 2.5 * s, gy - 8 * s - bob); ctx.lineTo(gx - 2.5 * s + step * 2.5 * s, gy - 1);
    ctx.moveTo(gx + 2.5 * s, gy - 8 * s - bob); ctx.lineTo(gx + 2.5 * s - step * 2.5 * s, gy - 1); ctx.stroke(); ctx.lineCap = 'butt';
    const by = gy - 21 * s - bob;
    ctx.fillStyle = a.color; ctx.strokeStyle = 'rgba(0,0,0,.55)'; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.roundRect(gx - 6 * s, by, 12 * s, 14 * s, 4 * s); ctx.fill(); ctx.stroke();
    if (a.pregnant) { ctx.beginPath(); ctx.arc(gx + 4 * s, by + 9 * s, 4.5 * s, 0, 7); ctx.fill(); ctx.stroke(); }
    ctx.strokeStyle = shade(a.color, -.25); ctx.lineWidth = 2.4 * s; ctx.lineCap = 'round';      // arms
    ctx.beginPath(); ctx.moveTo(gx - 6 * s, by + 3 * s); ctx.lineTo(gx - 7.5 * s - step * 2 * s, by + 10 * s);
    ctx.moveTo(gx + 6 * s, by + 3 * s); ctx.lineTo(gx + 7.5 * s + step * 2 * s, by + 10 * s); ctx.stroke(); ctx.lineCap = 'butt';
    const hy = by - 5 * s;
    blob(ctx, gx, hy, 6 * s, skin);
    ctx.fillStyle = hair; ctx.beginPath(); ctx.arc(gx, hy - 1 * s, 6.2 * s, Math.PI * 1.05, Math.PI * 1.95); ctx.fill();
    ctx.fillStyle = '#1a1a1a'; ctx.fillRect(gx - 2.6 * s, hy, 1.4 * s, 1.6 * s); ctx.fillRect(gx + 1.3 * s, hy, 1.4 * s, 1.6 * s);
    head = [gx, hy - 7 * s];
  }
  S.head[a.name] = { x: gx, y: head[1], gy, s };
}
function personOverlay(a) {
  const H = S.head[a.name]; if (!H) return;
  const [x, y] = scr(H.x, H.y), gy = scr(H.x, H.gy)[1];
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  let top = y - 4;
  if (a.task) { bar(x, top - 4, 28, Math.min(1, a.task.progress / a.task.total), '#ffd93d'); top -= 8; }
  bar(x, top - 4, 20, 1 - a.hunger / 100, a.hunger > 70 ? '#e0525e' : a.hunger > 40 ? '#e0a252' : '#5cc46e');
  ctx.font = '12px system-ui';
  if (a.heart) ctx.fillText('❤️', x + 14, top - 8);
  if (a.slow) ctx.fillText('💭', x - 14, top - 8);
  if (a.asleep && a.stage !== 'baby') { ctx.globalAlpha = .9; ctx.fillText(a.dreaming ? '🌙' : '💤', x + 10 + Math.sin(performance.now() / 600) * 2, top - 10); ctx.globalAlpha = 1; }
  if (a.stage === 'baby') return;
  ctx.font = 'bold 10px system-ui';
  const tag = a.name, nw = ctx.measureText(tag).width + 10;
  ctx.fillStyle = S.sel === a.name ? 'rgba(90,70,0,.85)' : 'rgba(10,12,16,.7)'; ctx.beginPath(); ctx.roundRect(x - nw / 2, gy + 3, nw, 13, 6); ctx.fill();
  ctx.fillStyle = '#fff'; ctx.fillText(tag, x, gy + 10);
}
function drawTalkLine(a) {
  const d = S.disp[a.name], tg = a.say_to && a.say_to !== 'all' && a.say_to !== 'Human' ? S.disp[a.say_to] : null;
  if (!d || !tg) return;
  const [x1, y1] = scr(...ground(d.x, d.y)), [x2, y2] = scr(...ground(tg.x, tg.y));
  ctx.strokeStyle = a.color; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.globalAlpha = .7;
  ctx.beginPath(); ctx.moveTo(x1, y1 - 12 * S.zoom); ctx.lineTo(x2, y2 - 12 * S.zoom); ctx.stroke();
  ctx.setLineDash([]); ctx.globalAlpha = 1;
}
function drawBubble(a) {
  const H = S.head[a.name]; if (!H) return;
  const [px, hy] = scr(H.x, H.y), py = hy - 12;
  const label = `${a.name} → ${a.say_to === 'all' ? 'everyone' : a.say_to === 'Human' ? 'you' : a.say_to}`;
  const txt = a.say.length > 90 ? a.say.slice(0, 88) + '…' : a.say;
  ctx.font = '12px system-ui';
  const lines = []; let cur = '';
  for (const w of txt.split(' ')) { if (ctx.measureText(cur + ' ' + w).width > 200 && cur) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; }
  lines.push(cur);
  const w = Math.max(...lines.map(l => ctx.measureText(l).width), ctx.measureText(label).width) + 16, h = lines.length * 15 + 22;
  const bx = Math.min(Math.max(px - w / 2, 3), scroller.clientWidth - w - 3), by = Math.max(46, py - h - 8);
  ctx.fillStyle = 'rgba(255,255,255,.5)'; ctx.beginPath(); ctx.roundRect(bx, by, w, h, 8); ctx.fill();   // see-through
  ctx.globalAlpha = .7; ctx.strokeStyle = a.color; ctx.lineWidth = 2; ctx.stroke(); ctx.globalAlpha = 1;
  ctx.beginPath(); ctx.moveTo(px - 6, by + h); ctx.lineTo(px, by + h + 8); ctx.lineTo(px + 6, by + h); ctx.fill();
  ctx.textAlign = 'left'; ctx.textBaseline = 'top'; ctx.fillStyle = '#556'; ctx.font = '10px system-ui'; ctx.fillText(label, bx + 8, by + 4);
  ctx.font = '12px system-ui'; ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.75)'; ctx.lineJoin = 'round';
  lines.forEach((l, k) => { ctx.strokeText(l, bx + 8, by + 17 + k * 15); ctx.fillStyle = '#111'; ctx.fillText(l, bx + 8, by + 17 + k * 15); });
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
}
function drawGrave(g) {
  const [gx, gy] = ground(g.x, g.y);
  shadow(ctx, gx, gy, 7, 3);
  ctx.fillStyle = '#8d929a'; ctx.beginPath(); ctx.roundRect(gx - 5, gy - 13, 10, 13, [5, 5, 0, 0]); ctx.fill();
  ctx.fillStyle = '#6c7078'; ctx.fillRect(gx - 1, gy - 10, 2, 6); ctx.fillRect(gx - 3, gy - 8, 6, 2);
}

// ---- fog, light and the frame
let fogKey = '';
function syncFog(fog) {
  const key = fog.join('');
  if (key === fogKey) return;
  fogKey = key;
  fctx.setTransform(1, 0, 0, 1, 0, 0); fctx.clearRect(0, 0, fogc.width, fogc.height);
  fctx.setTransform(1 / FOG_SCALE, 0, 0, 1 / FOG_SCALE, 0, 0);       // low resolution, scaled up = soft edges
  fctx.fillStyle = '#06080c';
  fog.forEach((row, y) => { for (let x = 0; x < S.W; x++) if (row[x] === '0') { diamond(fctx, x - .08, y - .08, 1.16, 1.16); fctx.fill(); } });
}
function darkness(h) {               // 0 = full day, ~.5 = deep night
  return h >= 22 || h < 5 ? .5 : h === 5 ? .38 : h === 6 ? .22 : h === 7 ? .08 : h < 18 ? 0 : h === 18 ? .08 : h === 19 ? .18 : h === 20 ? .3 : .42;
}
const scr = (wx, wy) => [(wx - S.cam.x) * S.zoom, (wy - S.cam.y) * S.zoom];   // world px -> screen px
function view() {                     // the part of the world on screen (world pixels), for culling
  const z = S.zoom, m = 90;
  return { x0: S.cam.x - m, y0: S.cam.y - m, x1: S.cam.x + scroller.clientWidth / z + m, y1: S.cam.y + scroller.clientHeight / z + m + 60 };
}
function resize() {
  const dpr = devicePixelRatio || 1, w = scroller.clientWidth, h = scroller.clientHeight;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
}
let lastFrame = 0;
function drawFrame(now) {
  const t = now / 1000, st = S.st, dpr = devicePixelRatio || 1;
  S.dt = Math.min(.1, (now - lastFrame) / 1000 || .016); lastFrame = now;
  resize();
  if (S.camTo) {                                       // smooth camera moves (find / follow)
    S.cam.x += (S.camTo.x - S.cam.x) * .14; S.cam.y += (S.camTo.y - S.cam.y) * .14;
    if (Math.hypot(S.camTo.x - S.cam.x, S.camTo.y - S.cam.y) < .5) S.camTo = null;
  }
  const V = view(), k = dpr * S.zoom;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = '#0b1220'; ctx.fillRect(0, 0, cv.width, cv.height);
  ctx.setTransform(k, 0, 0, k, -S.cam.x * k, -S.cam.y * k);
  ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  const vx = Math.max(0, V.x0), vy = Math.max(0, V.y0), vw = Math.min(WW, V.x1) - vx, vh = Math.min(WH, V.y1) - vy;
  const vis = (x, y) => { const [a, b] = ground(x, y); return a > V.x0 && a < V.x1 && b > V.y0 && b < V.y1; };
  if (vw > 0 && vh > 0) {
    if (k <= BG_SCALE + .01) ctx.drawImage(bg, vx * BG_SCALE, vy * BG_SCALE, vw * BG_SCALE, vh * BG_SCALE, vx, vy, vw, vh);
    else for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) if (vis(x, y)) paintTile(x, y, ctx);   // close up: draw sharp
  }
  if (st) {
    // water shimmer
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.3;
    for (const w of S.water || []) {
      if (!vis(w.x, w.y)) continue;
      const q = (Math.sin(t * 1.6 + w.ph) + 1) / 2, [a, b] = ground(w.x, w.y), o = Math.sin(t * .8 + w.ph) * 3;
      ctx.globalAlpha = q * .35; ctx.beginPath(); ctx.moveTo(a - 6 + o, b); ctx.quadraticCurveTo(a + o, b - 2.5, a + 6 + o, b); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    // everything that stands up, back to front
    S.inside = new Set(); const items = [], spots = new Set();
    for (const a of S.agents) { const d = S.disp[a.name] || a; spots.add(Math.round(d.x) + ',' + Math.round(d.y)); }
    const byTile = {};
    for (const s of st.structures) for (let i = 0; i < s.w; i++) for (let j = 0; j < s.h; j++) byTile[(s.x + i) + ',' + (s.y + j)] = s;
    for (const a of S.agents) {
      const b = a.inside && byTile[a.x + ',' + a.y];
      if (b) S.inside.add(b.x + ',' + b.y);
      const d = S.disp[a.name] || a;
      if (vis(d.x, d.y)) items.push([b && b.done && !isFlat(b) ? b.x + b.y + b.w + b.h - 1.4 : d.x + d.y + .5, () => drawPerson(a, t)]);
      else S.head[a.name] = null;
    }
    for (const p of S.props || []) if (vis(p.x, p.y)) items.push([p.x + p.y, () => drawProp(p, spots.has((p.x - 1) + ',' + (p.y - 1)) || spots.has(p.x + ',' + (p.y - 1)) || spots.has((p.x - 1) + ',' + p.y))]);
    for (const s of st.structures) if (vis(s.x + s.w / 2, s.y + s.h / 2)) items.push([isFlat(s) ? -1e6 + s.x + s.y : s.x + s.y + s.w + s.h - 1.5, () => drawBuilding(s, t)]);
    for (const g of st.dead) if (vis(g.x, g.y)) items.push([g.x + g.y + .2, () => drawGrave(g)]);
    items.sort((p, q) => p[0] - q[0]).forEach(([, f]) => f());
    // fog of war
    if ($('fog').checked && st.fog && vw > 0 && vh > 0) { syncFog(st.fog); ctx.globalAlpha = .62; ctx.drawImage(fogc, vx / FOG_SCALE, vy / FOG_SCALE, vw / FOG_SCALE, vh / FOG_SCALE, vx, vy, vw, vh); ctx.globalAlpha = 1; }
    // time of day: darken, warm dawn/dusk, and let fires and homes glow
    const hour = st.time?.hour ?? 12, target = darkness(hour);
    S.dark += (target - S.dark) * .03;
    if (S.dark > .01) {
      ctx.fillStyle = `rgba(12,18,52,${S.dark})`; ctx.fillRect(V.x0, V.y0, V.x1 - V.x0, V.y1 - V.y0);
      if (hour === 6 || hour === 7 || hour === 18 || hour === 19) { ctx.fillStyle = 'rgba(255,140,60,.08)'; ctx.fillRect(V.x0, V.y0, V.x1 - V.x0, V.y1 - V.y0); }
      ctx.globalCompositeOperation = 'lighter';
      for (const s of st.structures) {
        if (!s.done || (s.func !== 'fire' && s.func !== 'home')) continue;
        const [cx, cy] = iso(s.x + s.w / 2, s.y + s.h / 2), r = s.func === 'fire' ? 70 : 40, q = S.dark * (s.func === 'fire' ? .9 + Math.sin(t * 7) * .08 : .5);
        const g = ctx.createRadialGradient(cx, cy - 8, 2, cx, cy - 8, r); g.addColorStop(0, `rgba(255,170,70,${q * .7})`); g.addColorStop(1, 'rgba(255,170,70,0)');
        ctx.fillStyle = g; ctx.fillRect(cx - r, cy - 8 - r, r * 2, r * 2);
      }
      ctx.globalCompositeOperation = 'source-over';
    }
    // labels on top in screen pixels: the same readable size at every zoom
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const s of st.structures) if (vis(s.x + s.w / 2, s.y + s.h / 2)) buildingOverlay(s);
    for (const a of S.agents) personOverlay(a);
    if ($('bubbles').checked) {
      for (const a of S.agents) if (a.say) drawTalkLine(a);
      for (const a of S.agents) if (a.say && S.head[a.name]) drawBubble(a);
    }
  }
  requestAnimationFrame(drawFrame);
}

// zoom & pan: a camera over the world
function clampCam(c = S.cam) {
  const vw = scroller.clientWidth / S.zoom, vh = scroller.clientHeight / S.zoom;
  c.x = Math.max(-vw / 2, Math.min(WW - vw / 2, c.x)); c.y = Math.max(-vh / 2, Math.min(WH - vh / 2, c.y));
  return c;
}
function setZoom(z, cx, cy) {
  const old = S.zoom; S.zoom = Math.min(4, Math.max(.2, z));
  cx = cx ?? scroller.clientWidth / 2; cy = cy ?? scroller.clientHeight / 2;
  const wx = S.cam.x + cx / old, wy = S.cam.y + cy / old;                 // keep the world point under the pointer
  S.cam.x = wx - cx / S.zoom; S.cam.y = wy - cy / S.zoom; S.camTo = null; clampCam();
  store.set('zoom', S.zoom);
}
function lookAt(wx, wy, smooth = true) {
  const c = clampCam({ x: wx - scroller.clientWidth / 2 / S.zoom, y: wy - scroller.clientHeight / 2 / S.zoom });
  if (smooth) S.camTo = c; else { S.cam = c; S.camTo = null; }
}
const fitZoom = () => { setZoom(Math.min(scroller.clientWidth / WW, scroller.clientHeight / WH)); lookAt(WW / 2, WH / 2, false); };
function centerOn(name, smooth = true) {
  const a = S.agents.find(x => x.name === name); if (!a) return;
  const d = S.disp[a.name] || a, [px, py] = ground(d.x, d.y);
  lookAt(px, py - 15, smooth);
}
function canvasAt(e) {                 // pointer -> world pixels
  const r = cv.getBoundingClientRect();
  return { px: S.cam.x + (e.clientX - r.left) / S.zoom, py: S.cam.y + (e.clientY - r.top) / S.zoom };
}
function agentAt(px, py, lim = 22) {   // nearest agent to a world point, within `lim` screen pixels of the body
  let best = null, bd = lim;
  for (const a of S.agents) { const H = S.head[a.name]; if (!H) continue; const k = Math.hypot(H.x - px, (H.y + H.gy) / 2 - py) * S.zoom; if (k < bd) { bd = k; best = a; } }
  return best;
}
scroller.addEventListener('wheel', e => {
  e.preventDefault();
  const r = scroller.getBoundingClientRect();
  setZoom(S.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - r.left, e.clientY - r.top);
}, { passive: false });
let drag = null;
scroller.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, cx: S.cam.x, cy: S.cam.y, moved: false }; });
window.addEventListener('pointermove', e => {
  if (drag) {
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; scroller.classList.add('dragging'); $('follow').checked = false; S.camTo = null; }
    if (drag.moved) { S.cam.x = drag.cx - dx / S.zoom; S.cam.y = drag.cy - dy / S.zoom; clampCam(); }
  }
});
window.addEventListener('pointerup', e => {
  if (drag && !drag.moved && e.target === cv) { const { px, py } = canvasAt(e), a = agentAt(px, py); if (a) select(a.name); }
  drag = null; scroller.classList.remove('dragging');
});
cv.addEventListener('dblclick', e => { const { px, py } = canvasAt(e), a = agentAt(px, py); if (a) { select(a.name); $('follow').checked = true; } });
cv.addEventListener('mousemove', e => {
  const { px, py } = canvasAt(e), { fx, fy } = unIso(px, py), x = Math.floor(fx), y = Math.floor(fy), tip = $('tip');
  const t = S.tiles[y]?.[x], st = S.st;
  if (!t || !st || drag?.moved) { tip.hidden = true; return; }
  const names = { grass: 'Grass', water: 'Water — impassable', sand: 'Sand', rock: 'Rock — gather for stone', tree: 'Tree — gather for wood',
    food: 'Berry bush — food (slow to regrow)', sprout: 'Young plant — grows by itself', crop: 'Ripe crop — 3 food + a seed', structure: 'Built' };
  const unseen = st.fog && st.fog[y][x] === '0';
  let html = `<div class="muted">(${x}, ${y}) · ${unseen ? 'Unexplored' : names[t]}</div>`;
  const a = agentAt(px, py, 18);
  if (a) html = `<b style="color:${a.color}">${esc(a.name)}</b> ${TIER[a.tier]} ${a.role ? '· ' + esc(a.role) : ''}${a.slow ? ' · 💭 still thinking' : ''}<div>${SEX[a.sex]} ${a.stage} ${extras(a)} · ${esc(a.age_text)} old · hunger ${a.hunger} · ${a.food} food${a.pregnant ? ` · due ${ts(a.due)}` : ''}</div><div class="muted">${a.dreaming ? '🌙 dreaming' : a.asleep ? '💤 asleep' : esc(a.doing)}</div>` + html;
  const s = st.structures.find(q => x >= q.x && x < q.x + q.w && y >= q.y && y < q.y + q.h);
  if (s) html += `<div>${iconFor(s.kind, s.func)} <b>${esc(s.kind)}</b> <span class="muted">${s.w}×${s.h} · by ${esc(s.by)}</span>${!s.done ? `<div style="color:var(--gold)">🏗️ under construction: ${s.progress}/${s.work} hours of work</div>` : ''}${s.function ? `<div style="color:var(--gold)">⚙️ ${esc(s.function)}</div>` : '<div class="muted">decorative</div>'}${s.stock && Object.keys(s.stock).length ? `<div>📦 ${Object.entries(s.stock).map(([k, v]) => `${v} ${k}`).join(' · ')}</div>` : ''}${s.text ? `<div class="muted">“${esc(s.text)}”</div>` : ''}</div>`;
  const g = st.dead.find(q => q.x === x && q.y === y);
  if (g) html += `<div>🪦 ${esc(g.name)} — died of ${esc(g.cause)} aged ${g.age_text} (${ts(g.died)})</div>`;
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
  const tm = st.time || {}, PART = { morning: '🌅', afternoon: '☀️', evening: '🌇', night: '🌙' };
  $('p-day').textContent = `${PART[tm.part] || '☀️'} ${tm.stamp || ts(st.day, true)}`;
  const B = st.backends || {};
  $('p-pop').textContent = `👥 ${st.agents.length} / ${st.limits.max_agents}` + (st.dead.length ? ` · 🪦 ${st.dead.length}` : '');
  $('p-explored').textContent = `🧭 ${st.explored}% explored`;
  $('p-speed').hidden = !st.thinking;
  $('p-speed').textContent = `💭 ${st.thinking} thinking`;
  $('p-speed').title = `Agents whose brain is still working: they act as soon as it answers instead of holding everyone up. The last hour took ${st.day_seconds || 0}s.`;
  const u = st.usage;
  $('p-usage').textContent = `💬 ${fmt(u.calls)} calls` + (u.cost != null && u.cost > 0 ? ` · ~$${u.cost.toFixed(2)}` : '');
  $('p-usage').title = `${fmt(u.input + u.output)} tokens in total\n` + (Object.entries(u.models).map(([m, x]) => `${m}: ${x.calls} calls, ${x.input} in / ${x.output} out`).join('\n') || 'No model calls yet') + '\nClick for details';
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
$('p-usage').onclick = () => showTab('settings');
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
function talkToSol() { S.to = new Set(['Sol']); showTab('talk'); renderTo(); $('msg').focus(); }

function renderList(st) {
  const q = $('search').value.trim().toLowerCase();
  const rows = st.agents.filter(a => !q || a.name.toLowerCase().includes(q) || (a.role || '').toLowerCase().includes(q));
  $('list').innerHTML = `<div class="person" id="sol-row" title="Sol watches over everyone and gives advice. Click to talk to Sol.">
      <div class="avatar" style="background:#ffd93d">🧙</div><div><div class="name">Sol <span class="muted small">the mentor</span></div>
      <div class="sub">next review ${esc(st.sol.next_at)} · click to talk</div></div>
      <div class="right">${TIER[st.sol.model === 'local' ? 'local' : st.sol.model.startsWith('local:') ? 'smart' : 'haiku'] || ''}</div></div>` + rows.map(a => `
    <div class="person ${S.sel === a.name ? 'sel' : ''}" data-name="${esc(a.name)}">
      <div class="avatar" style="background:${a.color}">${esc(a.name[0])}</div>
      <div><div class="name">${esc(a.name)} <span class="muted" title="${a.sex}">${SEX[a.sex]}</span> <span title="${a.stage === 'baby' ? 'babies don\'t use a brain' : a.tier}">${a.stage === 'baby' ? '' : TIER[a.tier]}</span> ${extras(a)}${a.asleep && a.stage !== 'baby' ? ' 💤' : ''}${a.slow ? ' 💭' : ''}</div>
        <div class="sub">${a.role ? esc(a.role) : '<i>no role yet</i>'} · ${a.task ? '🏗️ ' + esc(a.task.label) : a.asleep ? 'asleep' : a.inside ? 'in the ' + esc(a.inside) + ' · ' + esc(a.doing) : esc(a.doing) || 'getting started'}</div></div>
      <div class="right">🎂 ${a.age_text}<br>🍎 ${a.food}</div>
      <div class="bar" title="Hunger ${a.hunger}/100"><div style="width:${a.hunger}%;background:${hungerColor(a.hunger)}"></div></div>
      ${a.task ? `<div class="bar task" title="${esc(a.task.label)}: ${a.task.progress}/${a.task.total} hours of work"><div style="width:${Math.min(100, a.task.progress / a.task.total * 100)}%;background:var(--gold)"></div></div>` : ''}
    </div>`).join('') || '<p class="muted">Nobody matches.</p>';
  $('graves').innerHTML = st.dead.length ? '<h3>In memory</h3>' + st.dead.map(g =>
    `<div class="grave" data-name="${esc(g.name)}">🪦 ${esc(g.name)} — ${esc(g.cause)}, aged ${g.age_text} (${ts(g.died)})</div>`).join('') : '';
}
$('list').onclick = e => { const p = e.target.closest('.person'); if (!p) return; p.id === 'sol-row' ? talkToSol() : select(p.dataset.name); };
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
    <div class="muted">${SEX[a.sex]} ${a.adult ? (a.sex === 'female' ? 'woman' : 'man') : (a.sex === 'female' ? 'girl' : 'boy')} · ${a.role ? esc(a.role) : 'no role yet'} · ${esc(a.age_text || a.age + ' hours')} old · ${a.alive ? a.stage + ' ' + extras(a) : `died of ${esc(a.cause)} on ${ts(a.died)}`}</div></div>`;
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
  const notes = (a.pregnancy ? `<div class="card">🤰 Pregnant by <a href="#" data-goto="${esc(a.pregnancy.father)}">${esc(a.pregnancy.father)}</a> — the baby is due on ${ts(a.pregnancy.due)}.</div>` : '')
    + (a.stage === 'baby' ? `<div class="card">🍼 A baby: can't think or feed themselves yet, and stays with their mother. Others must <b>care</b> for them (or you can send food). A child from day 5, an adult from day 10.</div>` : '')
    + (a.stage === 'child' ? '<div class="card">👶 A child: thinks and acts on their own, an adult from day 10.</div>' : '');
  const now = S.st?.agents.find(x => x.name === a.name);
  const doing = now ? (now.task ? `<div class="card" style="border-left:3px solid var(--gold)">🏗️ <b>${esc(now.task.label)}</b> — ${now.task.progress}/${now.task.total} hours of work
      <div class="bar" style="margin-top:6px"><div style="width:${Math.min(100, now.task.progress / now.task.total * 100)}%;background:var(--gold)"></div></div></div>` : '')
    + (now.asleep && now.stage !== 'baby' ? '<div class="card">💤 Asleep — back at work at 06:00.</div>' : now.inside ? `<div class="card">🏠 Inside the ${esc(now.inside)}.</div>` : '') : '';
  return notes + doing + `${meter('Hunger', a.hunger, hungerColor(a.hunger))}${meter('Health', a.health, a.health < 40 ? 'var(--bad)' : 'var(--good)')}
    <div class="kv" style="margin-top:8px"><span>Carrying</span><span>🍎 ${a.food} food · 🌱 ${a.seeds} seeds · 🪵 ${a.wood} wood · 🪨 ${a.stone} stone</span>
    <span>Objects</span><span class="objs">${a.items.map(i => `<span class="obj" title="${esc(i.text)}">🔧 ${esc(i.name)}</span>`).join('') || '<span class="muted">none yet</span>'}</span>
    <span>Explored</span><span>${a.discoveries} tiles seen first</span>
    <span>Position</span><span>(${a.x}, ${a.y})</span></div>
    ${l ? `<div class="card thought">💭 ${esc(l.thought)}<div class="tag" style="margin-top:4px">▶ ${esc(l.action)} → ${esc(l.result)}</div></div>` : ''}
    ${a.advice && a.advice.length ? `<div class="card" style="border-left:3px solid var(--gold)">🧙 <b>Sol's advice</b> (${ts(a.advice[a.advice.length - 1][0])}): ${esc(a.advice[a.advice.length - 1][1])}</div>` : ''}
    ${a.last_dream?.length ? `<div class="card" style="border-left:3px solid #9085e9">🌙 <b>Last dream</b> (${ts(a.last_dream[0])}): <i>${esc(a.last_dream[1])}</i></div>` : ''}
    ${a.ambition ? `<div class="card" style="border-left:3px solid var(--gold)">🎯 <b>Ambition:</b> ${esc(a.ambition)}</div>` : ''}
    ${a.plan ? `<div class="card" style="border-left:3px solid var(--accent)">🗺️ <b>Plan:</b> ${esc(a.plan)}</div>` : ''}
    ${a.queue.length ? `<div class="card">⏭️ <b>Next up</b> (runs automatically): ${a.queue.map(q => esc(q.action + (q.target ? ' → ' + q.target : q.title ? ' ' + q.title : q.to && q.to !== 'all' ? ' → ' + q.to : ''))).join(' · ')}</div>` : ''}
    <h3>Abilities</h3>${Object.entries(a.abilities).map(([k, v]) => `<div title="${esc(a.ability_info[k])}">${meter(k[0].toUpperCase() + k.slice(1), v * 10, v >= 7 ? 'var(--good)' : v <= 3 ? 'var(--warn)' : 'var(--accent)').replace(`<span>${v * 10}</span></div>`, `<span>${v}/10</span></div>`)}</div>`).join('')}
    <p class="muted small">Expected lifespan: about ${esc(a.lifespan_text || a.lifespan + ' days')}.</p>
    ${a.orders.length ? `<h3>You asked</h3>${a.orders.map(o => `<div class="card">“${esc(o[1])}” <span class="tag">${ts(o[0])}</span></div>`).join('')}` : ''}
    <h3>Personality</h3>${Object.entries(a.traits).map(([k, v]) => `<div title="${esc(a.trait_info?.[k] || '')}">${meter(k[0].toUpperCase() + k.slice(1), Math.round(v * 100), 'var(--gold)')}</div>`).join('')}
    <p class="muted small">Hover a trait or ability to see what it does.</p>`;
}

function timeline(a) {
  return `<div class="tag">${a.history_total} turns in total · newest first</div><div class="timeline">` + a.history.slice().reverse().map(h => `
    <div class="entry"><div class="tag">${ts(h.tick)} · (${h.x}, ${h.y}) · hunger ${h.hunger}</div>
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
    : m.review ? `<div class="bub review"><b style="color:var(--gold)">🧙 Sol's review · ${ts(m.tick)}</b>${m.text.length > 220 ? `<details><summary>${esc(m.text.slice(0, 200))}… <span class="more">more</span></summary>${esc(m.text.slice(200))}</details>` : esc(m.text)}</div>`
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
$('solm').onchange = e => api.post('/api/control', { sol_model: e.target.value });
$('thinkev').onchange = e => api.post('/api/control', { think_every: +e.target.value }).then(() => toast(`Agents now think every ${e.target.value === '1' ? 'hour' : e.target.value + ' hours'}`));
$('discoveries').onclick = e => { const g = e.target.closest('[data-goto]'); if (g) select(g.dataset.goto); };

// ======================================================================= world feed
const FILTERS = { all: 'All', sol: '🧙 Sol', talk: '💬 Talk', life: '❤️ Life', making: '🔨 Making', ideas: '💡 Ideas', explore: '🧭 Exploring', survival: '🍎 Food' };
const KIND_FILTER = { dream: 'ideas', sol: 'sol', discovery: 'ideas', attempt: 'ideas', goal: 'ideas', care: 'life', birth: 'life', death: 'life', love: 'life', gift: 'life', build: 'making', craft: 'making', farm: 'making',
  idea: 'ideas', explore: 'explore', food: 'survival', role: 'life', brain: 'life' };
const KIND_ICON = { dream: '🌙', sol: '🧙', discovery: '💡', attempt: '✨', goal: '🎯', care: '🍼', birth: '👶', death: '🪦', love: '❤️', gift: '🎁', build: '🏗️', craft: '🔧', farm: '🌾', idea: '💡', explore: '🧭', food: '🍎', role: '🎭', brain: '🧠', talk: '💬' };
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
  $('feed').innerHTML = items.map(i => `<div class="item ${i.kind === 'idea' ? 'idea' : ''}"><span class="day">${ts(i.tick)}</span>
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
    g.textAlign = 'left'; g.fillText(ts(data[0].day), padL, h - 2); g.textAlign = 'right'; g.fillText(ts(data[data.length - 1].day), w - 6, h - 2);
    g.strokeStyle = line; g.lineWidth = 2; g.lineJoin = 'round'; g.beginPath();
    ys.forEach((v, i) => i ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v))); g.stroke();
    const i = S.hover ?? data.length - 1;
    if (S.hover != null) { g.strokeStyle = '#b4bcc8'; g.lineWidth = 1; g.beginPath(); g.moveTo(X(i), 6); g.lineTo(X(i), 6 + ph); g.stroke(); }
    g.fillStyle = line; g.strokeStyle = '#20262e'; g.lineWidth = 2; g.beginPath(); g.arc(X(i), Y(ys[i]), 4.5, 0, 7); g.fill(); g.stroke();
    $('v-' + k).textContent = fmt(ys[i]) + (k === 'explored' ? '%' : '');
  }
  const d = data[S.hover ?? data.length - 1];
  $('readout').innerHTML = `<b>${ts(d.day, true)}</b> — ` + METRICS.map(([k, l]) => `${l}: <b>${fmt(d[k])}${k === 'explored' ? '%' : ''}</b>`).join(' · ') + ` · Deaths so far: <b>${d.deaths}</b>`;
  if ($('stats-table').checked) {
    const step = Math.max(1, Math.ceil(data.length / 30)), rows = data.filter((_, i) => i % step === 0 || i === data.length - 1).reverse();
    $('table').innerHTML = `<table><tr><th>When</th>${METRICS.map(([, l]) => `<th>${l}</th>`).join('')}</tr>` +
      rows.map(r => `<tr><td>${ts(r.day)}</td>${METRICS.map(([k]) => `<td>${fmt(r[k])}</td>`).join('')}</tr>`).join('') + '</table>';
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
  $('saves').innerHTML = saves.length ? saves.map(s => `<div class="save"><span><b>${esc(s.name)}</b><br><span class="muted small">${ts(s.day ?? '?')} · ${esc(s.saved)} · ${s.size_kb} KB</span></span>
    <button class="btn" data-load="${esc(s.name)}">Load</button></div>`).join('') : '<p class="muted">No saves yet.</p>';
  renderUsage();
}
$('saves').onclick = async e => {
  const b = e.target.closest('[data-load]'); if (!b) return;
  if (!confirm(`Load "${b.dataset.load}"? The current world will be replaced (save it first if you want to keep it).`)) return;
  const r = await api.post('/api/load', { name: b.dataset.load });
  if (r.error) return toast(r.error, 'var(--bad)');
  resetView(); toast(`Loaded "${b.dataset.load}" (${ts(r.day)})`, 'var(--good)');
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
  const rows = Object.entries(u.models), B = S.st.backends || {};
  const brains = B.mock ? '🎭 Mock (scripted, not real thinking)' : [B.local ? '🖥️ Local: ' + esc(B.local_model) : '', B.smart_local ? '🧠 Smart local: ' + esc(B.smart_local) : '', B.claude ? '🌱 Claude (Haiku / Sonnet / Opus)' : ''].filter(Boolean).join(' · ');
  $('usage').innerHTML = `<div class="card small">Available brains: ${brains || 'none'}</div>` + (rows.length
    ? `<table><tr><th>Model</th><th>Calls</th><th title="Average tokens sent + received per call">Per call</th><th>Input</th><th title="Input read from Claude's prompt cache at a tenth of the price">Cached</th><th>Output</th><th>Cost</th></tr>` +
      rows.map(([m, x]) => { const all = x.input + (x.cached || 0) + (x.written || 0);
        return `<tr><td>${esc(m)}</td><td>${fmt(x.calls)}</td><td>${fmt(Math.round((all + x.output) / Math.max(1, x.calls)))}</td><td>${fmt(all)}</td><td>${fmt(x.cached || 0)}</td><td>${fmt(x.output)}</td><td>${x.cost != null ? '$' + x.cost.toFixed(3) : '–'}</td></tr>`; }).join('') + '</table>'
      + '<p class="muted small">Local models are free. For Claude cost estimates start the hub with --price MODEL=IN,OUT (USD per million tokens).</p>'
    : '<p class="muted">No model calls yet.</p>');
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
    if (S.centerOnce && st.agents.length) {          // first visit: look at where the people are
      S.centerOnce = false;
      const [px, py] = ground(st.agents.reduce((n, a) => n + a.x, 0) / st.agents.length, st.agents.reduce((n, a) => n + a.y, 0) / st.agents.length);
      lookAt(px, py, false);
    }
    if (st.tiles.length === S.H) syncTiles(st.tiles);
    renderTop(st);
    if (!S.sel) renderList(st);
    if ($('to').children.length !== st.agents.length + 2) renderTo();
    if (document.activeElement !== $('auth')) $('auth').value = st.authority;
    if (document.activeElement !== $('thinkev') && st.think_every) $('thinkev').value = st.think_every;
    renderChat(); renderFeed(st); toastNewEvents(st.events);
    $('discoveries').innerHTML = st.discoveries.length ? st.discoveries.slice().reverse().map(d => `<div class="disc"><b>${esc(d.name)}</b>
      <span class="muted">by <span class="who" data-goto="${esc(d.by)}" style="color:${d.color};cursor:pointer">${esc(d.by)}</span>, ${ts(d.tick)}</span>
      <div>${esc(d.description)}</div><span class="eff">⚡ ${esc(d.meaning)}</span></div>`).join('')
      : '<p class="muted small">Nothing yet. When an agent attempts or invents something genuinely useful, it shows up here and changes the rules for everyone.</p>';
    const so = st.sol;
    const last = so.log.length ? so.log[so.log.length - 1] : null, note = last ? (last.note || last.speech || '') : '';
    $('solcard').innerHTML = `<div class="solhead"><div class="avatar" style="background:#ffd93d">🧙</div>
        <div class="solmeta"><b>Sol</b> <span class="small">${TIER[so.model === 'local' ? 'local' : so.model.startsWith('local:') ? 'smart' : 'haiku'] || ''}</span> <span class="muted small">mentor &amp; referee</span>
        <div class="muted small" title="Sol decides when to look again">next review ${so.next_in ? ts(st.day + so.next_in) : 'soon'}</div></div>
        <div class="solbtns"><button class="btn primary" id="sol-talk">💬 Talk</button><button class="btn" id="sol-now" title="Ask Sol to review the society now">🔍 Review now</button></div></div>
      ${note ? `<div class="small clamp" title="${esc(note)}">${esc(note)}</div>` : '<div class="small muted">No review yet. Sol looks over everyone, gives advice and decides when to look again.</div>'}`;
    $('sol-now').onclick = () => api.post('/api/sol').then(() => toast('🧙 Sol is reviewing the society…', '#ffd93d'));
    $('sol-talk').onclick = talkToSol;
    if (document.activeElement !== $('solm')) $('solm').value = { 'claude-haiku-5-5': 'haiku', 'claude-sonnet-5-5': 'sonnet', 'claude-opus-5-5': 'opus' }[so.model] || (so.model.startsWith('local:') ? 'smart' : 'local');
    $('blueprints').innerHTML = st.blueprints.length ? st.blueprints.slice().reverse().map(b => `<div class="disc" style="background:var(--panel-2);border-color:var(--line)">${iconFor(b.kind)} <b>${esc(b.kind)}</b>
      <span class="muted">${b.by ? 'designed by ' + esc(b.by) : ''}</span><div>${esc(b.description)}</div>
      <span class="eff" style="color:var(--text-2)">needs ${Object.entries(b.cost).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing'}</span></div>`).join('')
      : '<p class="muted small">No blueprints yet. The first time someone builds a new kind of building, its cost and purpose are worked out and shared here.</p>';
    if (S.tab === 'settings') renderUsage();
  } catch (e) { console.error(e); }
  polling = false;
  if (pollAgain) { pollAgain = false; poll(); }
}
async function loadWorld() {
  const w = await api.get('/api/world');
  S.W = w.width; S.H = w.height; S.tiles = w.tiles;
  WW = (S.W + S.H) * TW / 2 + PAD * 2; WH = (S.W + S.H) * TH / 2 + TOP + PAD;
  bg.width = WW * BG_SCALE; bg.height = WH * BG_SCALE; bctx.setTransform(BG_SCALE, 0, 0, BG_SCALE, 0, 0);
  fogc.width = Math.ceil(WW / FOG_SCALE); fogc.height = Math.ceil(WH / FOG_SCALE); fogKey = '';
  drawn.length = 0; resize();
  syncTiles(w.tiles);
}
(async () => {
  if (innerWidth < 1000) document.querySelector('.legend').open = false;
  await loadWorld();
  const z = store.get('zoom', null);
  setZoom(z || 1.5); S.centerOnce = true;
  showTab(store.get('tab', 'people'));
  await poll();
  requestAnimationFrame(drawFrame);
  setInterval(poll, 700);
  setInterval(() => { if (S.sel && S.tab === 'people') loadDetail(); }, 1500);
  setInterval(() => { if (S.tab === 'stats') loadStats(); }, 4000);
  if (!store.get('seenHelp', false)) help(true);
})();
