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
  zoom: 1, disp: {}, adisp: {}, popups: [], lastAnim: {}, offset: {}, head: {}, inside: new Set(), dark: 0, props: [], water: [], lastEvent: null, stats: [], hover: null, brainKey: '',
};

// ======================================================================= map (isometric)
// The world is drawn as diamonds: tile (x, y) sits at iso(x, y). The ground is painted once into `bg` (and repainted
// tile by tile when it changes); trees, rocks, buildings and people are drawn every frame, back to front.
const TW = 40, TH = 20, TOP = 80, PAD = 24;
const cv = $('map'), ctx = cv.getContext('2d');
const bg = document.createElement('canvas'), bctx = bg.getContext('2d');
const fogc = document.createElement('canvas'), fctx = fogc.getContext('2d');
const FOG_SCALE = 4, SPRITE_SCALE = 4;
let BG_SCALE = 2;                                     // the ground cache is kept sharper than 1:1 (less on huge maps)
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

// ---- art: CC0 sprites by Kenney (assets/LICENSES.md); everything falls back to drawn shapes until it has loaded
const A = 'assets/';
const LAND = n => `${A}kenney-isometric-landscape/landscapeTiles_${String(n).padStart(3, '0')}.png`;
const NAT = n => `${A}kenney-isometric-nature/naturePack_${String(n).padStart(3, '0')}_0.png`;
const PACK = {        // how each pack's sprites sit on our 40x20 tile: scale, and the pixel that goes on the tile centre
  land: { k: TW / 132 }, nature: { k: TW / 182, ax: 110, ay: 304 }, mini: { k: TW / 256, ax: 128, ay: 436 },
};
const ART = {
  grass: [LAND(67), LAND(75)], sand: [LAND(59)], water: [LAND(66)], dirt: [LAND(83)], stone: [LAND(81)],
  farmland: `${A}kenney-isometric-miniature-farm/dirtFarmland_S.png`,
  green: [62, 63, 65, 70, 72, 73, 130, 151, 161, 64, 140].map(NAT),
  pine: [51, 53, 81, 84, 85, 87, 88, 89, 114].map(NAT),
  autumn: [66, 67, 68, 69, 139, 162, 94, 149].map(NAT),
  bare: [`${A}kenney-isometric-miniature-overworld/treeDeadLarge_S.png`, `${A}kenney-isometric-miniature-overworld/treeDeadSmall_S.png`],
  rock: [23, 24, 131, 134, 135, 136, 137, 152, 153, 171, 172, 173, 174, 60].map(NAT),
  bush: NAT(71), stump: NAT(79),
  sprout: `${A}kenney-isometric-miniature-farm/cornYoung_S.png`, crop: `${A}kenney-isometric-miniature-farm/corn_S.png`,
  campfire: NAT(77), tent: [NAT(75), NAT(95), NAT(107)], statue: NAT(156), obelisk: NAT(39), pillar: NAT(157),
  fence: `${A}kenney-isometric-miniature-farm/fenceLow_S.png`, hay: `${A}kenney-isometric-miniature-farm/hayBales_S.png`,
  sacks: `${A}kenney-isometric-miniature-farm/sacksCrate_S.png`, well: LAND(100),
  deer: `${A}kenney-cube-pets/animal-deer.png`, rabbit: `${A}kenney-cube-pets/animal-bunny.png`, boar: `${A}kenney-cube-pets/animal-hog.png`,
};
const IMG = {};
let artPending = 0;
function img(src) {                  // the image if it has loaded, else null (and start loading it)
  let i = IMG[src];
  if (!i) {
    i = IMG[src] = new Image(); artPending++;
    i.onload = () => { i.ok = true; if (--artPending === 0) drawn.length = 0; };   // repaint the ground once all is in
    i.onerror = () => { artPending--; };
    i.src = src;
  }
  return i.ok ? i : null;
}
Object.values(ART).flat().forEach(img);
const packOf = src => src.includes('landscape') ? PACK.land : src.includes('nature') ? PACK.nature : PACK.mini;
function put(c, src, gx, gy, alpha = 1, extra = 1) {   // draw a sprite with its anchor on (gx, gy)
  const i = img(src); if (!i) return false;
  const p = packOf(src), k = p.k * extra;
  const ax = p.ax ?? i.width / 2, ay = p.ay ?? i.height - 66;
  if (alpha !== 1) c.globalAlpha = alpha;
  c.drawImage(i, gx - ax * k, gy - ay * k, i.width * k, i.height * k);
  if (alpha !== 1) c.globalAlpha = 1;
  return true;
}
const pick = (list, x, y, k = 0) => list[Math.floor(rnd(x, y, k) * list.length) % list.length];

// ---- ground
const GROUND = { grass: '#4f9a47', food: '#4f9a47', tree: '#478f40', sprout: '#7a5634', crop: '#7a5634', water: '#2f6fb5',
  sand: '#d8c68a', rock: '#8c8a80', structure: '#8f7a55' };
const GROUND_ART = { grass: 'grass', food: 'grass', tree: 'grass', water: 'water', sand: 'sand', rock: 'grass', structure: 'dirt' };
const season = () => S.forceSeason || S.st?.season || 'summer';   // forceSeason: preview another season (console)
function paintTile(x, y, c = bctx) {
  const t = S.tiles[y][x], [cx, cy] = ground(x, y), sea = season();
  const src = t === 'sprout' || t === 'crop' ? ART.farmland : ART[GROUND_ART[t]] ? pick(ART[GROUND_ART[t]], x, y, 3) : null;
  if (!(src && put(c, src, cx, cy))) {                                   // fallback: a flat coloured diamond
    const col = shade(GROUND[t] || '#444', (rnd(x, y) - .5) * .12);
    diamond(c, x, y); c.fillStyle = col; c.strokeStyle = col; c.lineWidth = .7; c.fill(); c.stroke();
  }
  if (sea === 'winter' || sea === 'autumn') {                            // the season colours the land
    diamond(c, x, y);
    c.fillStyle = sea === 'winter' ? (t === 'water' ? 'rgba(220,240,255,.45)' : 'rgba(245,248,255,.62)') : 'rgba(214,140,40,.16)';
    if (t !== 'water' || sea === 'winter') c.fill();
  } else if (sea === 'spring' && (t === 'grass' || t === 'food') && rnd(x, y, 20) > .75) {
    c.fillStyle = rnd(x, y, 21) > .5 ? '#fff3a0' : '#f8c8e0';
    for (let i = 0; i < 3; i++) { c.beginPath(); c.arc(cx + (rnd(x, y, 22 + i) - .5) * TW * .5, cy + (rnd(x, y, 25 + i) - .5) * TH * .5, 1.3, 0, 7); c.fill(); }
  }
  if (t === 'water') {
    const p = [iso(x, y), iso(x + 1, y), iso(x + 1, y + 1), iso(x, y + 1)].map(([a, b]) => [a, b + 4]);
    c.strokeStyle = 'rgba(230,245,255,.6)'; c.lineWidth = 1.6;                      // foam where water meets land
    [[0, -1, 0, 1], [1, 0, 1, 2], [0, 1, 2, 3], [-1, 0, 3, 0]].forEach(([dx, dy, i, j]) => {
      const n = S.tiles[y + dy]?.[x + dx]; if (n && n !== 'water') { c.beginPath(); c.moveTo(...p[i]); c.lineTo(...p[j]); c.stroke(); } });
  }
}
function syncTiles(next) {
  S.tiles = next; let changed = false;
  if (S.paintedSeason !== season()) { S.paintedSeason = season(); drawn.length = 0; }
  for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) {
    if (!drawn[y]) drawn[y] = [];
    if (drawn[y][x] !== next[y][x]) { drawn[y][x] = next[y][x]; changed = true; }
  }
  if (changed) {                                                      // repaint back to front so tiles overlap correctly
    bctx.save(); bctx.setTransform(1, 0, 0, 1, 0, 0); bctx.clearRect(0, 0, bg.width, bg.height); bctx.restore();
    for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) paintTile(x, y);
    S.props = []; S.water = [];
    for (let y = 0; y < S.H; y++) for (let x = 0; x < S.W; x++) {
      const t = next[y][x];
      if (PROP[t]) S.props.push({ x, y, t, v: Math.floor(rnd(x, y, 7) * 3), pine: rnd(x, y, 11) < .35 });
      if (t === 'water' && rnd(x, y, 8) > .6) S.water.push({ x, y, ph: rnd(x, y, 9) * 6.3 });
    }
  }
}

// ---- props: trees by season, rocks, berry bushes, crops (drawn shapes are the fallback)
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
    blob(c, 23, 32, 15, '#245c2a'); blob(c, 18, 27, 11, '#2e7a35'); blob(c, 28, 24, 9, '#3c9744');
  } },
  rock: { w: 42, h: 36, ax: 21, ay: 28, draw(c) {
    shadow(c, 21, 28, 16, 6);
    c.fillStyle = '#7f848c'; c.beginPath(); c.moveTo(5, 27); c.lineTo(9, 13); c.lineTo(19, 6); c.lineTo(31, 10); c.lineTo(37, 26); c.closePath(); c.fill();
  } },
  food: { w: 36, h: 32, ax: 18, ay: 25, draw(c) { shadow(c, 18, 25, 13, 5); blob(c, 18, 17, 11, '#2b6a2f'); } },
  sprout: { w: 30, h: 22, ax: 15, ay: 17, draw(c) { c.strokeStyle = '#8fe36b'; c.lineWidth = 2; c.beginPath(); c.moveTo(15, 17); c.lineTo(15, 7); c.stroke(); } },
  crop: { w: 34, h: 36, ax: 17, ay: 28, draw(c) { c.fillStyle = '#f3d35a'; c.fillRect(8, 8, 18, 20); } },
};
const BERRIES = [[-6, -9], [5, -12], [0, -6], [-2, -15], [7, -7], [-8, -13]];
function drawProp(p, fade, t) {
  const [gx, gy] = ground(p.x, p.y), sea = season(), alpha = fade ? .45 : 1;
  let src = null;
  if (p.t === 'tree') src = p.pine ? pick(ART.pine, p.x, p.y, 4) : pick(sea === 'autumn' ? ART.autumn : sea === 'winter' ? ART.bare : ART.green, p.x, p.y, 5);
  else if (p.t === 'rock') src = pick(ART.rock, p.x, p.y, 6);
  else if (p.t === 'food') src = ART.bush;
  else if (p.t === 'sprout' || p.t === 'crop') src = ART[p.t];
  const burning = S.burning?.has(p.x + ',' + p.y);
  const ok = src && put(ctx, src, gx, gy, alpha, p.t === 'tree' ? .9 + p.v * .08 : p.t === 'food' ? .55 : 1);
  if (!ok) {
    const P = PROP[p.t], spr = sprite(p.t, P.w, P.h, c => P.draw(c, p.v));
    ctx.globalAlpha = alpha; ctx.drawImage(spr, gx - P.ax, gy - P.ay, P.w, P.h); ctx.globalAlpha = 1;
  }
  if (p.t === 'tree' && sea === 'winter' && p.pine) {                  // snow on the pines
    ctx.fillStyle = 'rgba(255,255,255,.75)'; ctx.beginPath(); ctx.ellipse(gx, gy - 30, 7, 3, 0, 0, 7); ctx.fill();
  }
  if (p.t === 'food' && sea !== 'winter') BERRIES.forEach(([a, b]) => blob(ctx, gx + a, gy + b, 1.9, '#e0334e'));
  if (burning) drawFlames(gx, gy - 14, t, 1.4);
}
function drawFlames(x, y, t, s = 1) {
  for (let i = 0; i < 4; i++) {
    const f = Math.sin(t * 9 + i * 1.7) * 2, h = (10 + f + (i % 2) * 6) * s, x0 = x + (i - 1.5) * 4 * s;
    ctx.fillStyle = ['#ff6a1a', '#ffd23f', '#ff8a2a', '#ffb02e'][i]; ctx.globalAlpha = .9;
    ctx.beginPath(); ctx.moveTo(x0 - 4 * s, y + 6); ctx.quadraticCurveTo(x0 - 3 * s, y - h * .4, x0 + f * .4, y - h); ctx.quadraticCurveTo(x0 + 3 * s, y - h * .4, x0 + 4 * s, y + 6); ctx.fill();
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = 'rgba(80,80,80,.25)';
  for (let i = 0; i < 3; i++) blob(ctx, x + Math.sin(t + i) * 4, y - 22 * s - ((t * 12 + i * 9) % 26), 4 + i, 'rgba(90,90,90,.22)');
}

// ---- animals
const ANIMAL_TINT = { goat: '#e8e2d6', sheep: '#f4f2ee' };
function drawAnimal(b, t) {
  const d = S.adisp[b[0]] || (S.adisp[b[0]] = { x: b[2], y: b[3] });
  d.x += (b[2] - d.x) * .06; d.y += (b[3] - d.y) * .06;
  const moving = Math.abs(b[2] - d.x) + Math.abs(b[3] - d.y) > .04;
  const [gx, gy] = ground(d.x, d.y), hop = moving ? Math.abs(Math.sin(t * 10 + b[0])) * 2.5 : 0;
  shadow(ctx, gx, gy, 7, 3, .25);
  const src = ART[b[1]];
  if (src && img(src)) {
    const i = img(src), w = b[1] === 'rabbit' ? 20 : 28;
    ctx.drawImage(i, gx - w / 2, gy - w * .85 - hop, w, w);
  } else {                                                              // sheep and goats: a woolly body, a head, legs
    const col = ANIMAL_TINT[b[1]] || '#a07850';
    ctx.strokeStyle = '#3a3a3a'; ctx.lineWidth = 1.6;
    for (const lx of [-4, -1, 2, 5]) { ctx.beginPath(); ctx.moveTo(gx + lx, gy - 5 - hop); ctx.lineTo(gx + lx, gy - hop * .3); ctx.stroke(); }
    if (b[1] === 'sheep') for (let i = 0; i < 5; i++) blob(ctx, gx - 5 + i * 2.6, gy - 9 - (i % 2) * 2 - hop, 4, col);
    else { ctx.fillStyle = col; ctx.beginPath(); ctx.ellipse(gx, gy - 9 - hop, 8, 4.5, 0, 0, 7); ctx.fill(); }
    blob(ctx, gx + 8, gy - 12 - hop, 3.2, b[1] === 'sheep' ? '#3a3a3a' : col);
    if (b[1] === 'goat') { ctx.strokeStyle = '#6b5a45'; ctx.beginPath(); ctx.moveTo(gx + 8, gy - 15 - hop); ctx.lineTo(gx + 6, gy - 19 - hop); ctx.stroke(); }
  }
  if (b[4]) { const o = S.agents.find(a => a.name === b[4]); if (o) blob(ctx, gx, gy - 2, 2, o.color); }   // a collar: it's tame
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
  const kind = s.kind.toLowerCase(), [gx, gy] = ground(s.x + (s.w - 1) / 2, s.y + (s.h - 1) / 2);
  if (s.w * s.h === 1) {                                                // small things drawn from the art packs
    const art = /tent/.test(kind) ? pick(ART.tent, s.x, s.y) : /statue|monument|idol|totem/.test(kind) ? ART.statue
      : /obelisk|marker|stone circle/.test(kind) ? ART.obelisk : /pillar|column/.test(kind) ? ART.pillar
      : /fence|pen|corral/.test(kind) ? ART.fence : /hay|stack/.test(kind) ? ART.hay : /crate|sack|supply/.test(kind) ? ART.sacks : null;
    if (art && put(ctx, art, gx, gy)) return;
  }
  if (func === 'well' && s.w * s.h === 1 && put(ctx, ART.well, gx, gy)) return;
  if (func === 'fire' && s.w * s.h === 1) {                           // camp fire: stone ring and flickering flames
    shadow(ctx, cx, cy, 13, 6, .3);
    if (!put(ctx, ART.campfire, gx, gy)) for (let i = 0; i < 8; i++) { const a = i / 8 * 6.28; blob(ctx, cx + Math.cos(a) * 9, cy + Math.sin(a) * 4.5, 2.8, i % 2 ? '#8a8f96' : '#a3a8af'); }
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
    head = drawBody(a, d, gx, gy, s, t, skin, hair, h);
  }
  S.head[a.name] = { x: gx, y: head[1], gy, s };
}
// ---- people at work: a tool for each job, swung toward what they're working on
const TOOL_KIND = { chop: 'axe', mine: 'pick', hammer: 'hammer', hoe: 'hoe', hunt: 'spear', fish: 'rod' };
function drawBody(a, d, gx, gy, s, t, skin, hair, h) {
  const an = a.anim?.length && !d.moving && (S.st?.day ?? 0) - a.anim[0] <= 1 ? a.anim : null;
  const kind = an?.[1] || '', ph = h % 7;
  if (an && S.lastAnim[a.name] !== an[0] + kind) {                     // something new got done: a little popup
    S.lastAnim[a.name] = an[0] + kind;
    if (POP[kind]) S.popups.push({ name: a.name, icon: POP[kind], born: performance.now() });
  }
  const side = an ? ((an[2] - an[3]) > 0 ? 1 : (an[2] - an[3]) < 0 ? -1 : (an[2] + an[3]) >= 0 ? 1 : -1) : 1;
  const swing = (Math.sin(t * 7 + ph) + 1) / 2;                        // 0..1, the rhythm of work
  const sitting = kind === 'rest';
  const bend = ['chop', 'mine', 'hoe', 'pick', 'hammer'].includes(kind) ? swing * 2.2 * s : 0;
  const step = d.moving ? Math.sin(t * 9 + ph) : 0, bob = Math.abs(step) * 1.8 * s + bend + (sitting ? 6 * s : 0);
  ctx.strokeStyle = '#2a2a35'; ctx.lineWidth = 2.6 * s; ctx.lineCap = 'round';      // legs
  ctx.beginPath();
  if (sitting) { ctx.moveTo(gx - 2.5 * s, gy - 3 * s); ctx.lineTo(gx + 5 * s, gy - 1); ctx.moveTo(gx + 2.5 * s, gy - 3 * s); ctx.lineTo(gx + 8 * s, gy - 1); }
  else { ctx.moveTo(gx - 2.5 * s, gy - 8 * s - bob); ctx.lineTo(gx - 2.5 * s + step * 2.5 * s, gy - 1);
         ctx.moveTo(gx + 2.5 * s, gy - 8 * s - bob); ctx.lineTo(gx + 2.5 * s - step * 2.5 * s, gy - 1); }
  ctx.stroke(); ctx.lineCap = 'butt';
  const by = gy - 21 * s - bob;
  ctx.fillStyle = a.color; ctx.strokeStyle = 'rgba(0,0,0,.55)'; ctx.lineWidth = 1.2;
  ctx.beginPath(); ctx.roundRect(gx - 6 * s, by, 12 * s, 14 * s, 4 * s); ctx.fill(); ctx.stroke();
  if (a.pregnant) { ctx.beginPath(); ctx.arc(gx + 4 * s, by + 9 * s, 4.5 * s, 0, 7); ctx.fill(); ctx.stroke(); }
  const hy = by - 5 * s;
  // the free arm, then the working arm
  const sh = [gx + side * 6 * s, by + 3 * s], other = [gx - side * 6 * s, by + 3 * s];
  ctx.strokeStyle = shade(a.color, -.25); ctx.lineWidth = 2.4 * s; ctx.lineCap = 'round';
  ctx.beginPath(); ctx.moveTo(...other); ctx.lineTo(other[0] - side * 1.5 * s - step * 2 * s, other[1] + 7 * s); ctx.stroke();
  let ang = Math.PI / 2 - side * 0.25 - step * .3;                     // arm angle (0 = pointing right, down is +)
  if (['chop', 'mine', 'hammer'].includes(kind)) ang = side > 0 ? -2.3 + swing * 2.6 : Math.PI + 2.3 - swing * 2.6;
  else if (kind === 'hoe') ang = side > 0 ? .2 + swing * .7 : Math.PI - .2 - swing * .7;
  else if (kind === 'pick') ang = side > 0 ? .5 + swing * .4 : Math.PI - .5 - swing * .4;
  else if (kind === 'fish') ang = side > 0 ? -.25 : Math.PI + .25;
  else if (kind === 'hunt') ang = side > 0 ? -.1 : Math.PI + .1;
  else if (kind === 'eat') ang = side > 0 ? -1.9 : Math.PI + 1.9;
  else if (['talk', 'give', 'tame', 'craft', 'care', 'love'].includes(kind)) ang = side > 0 ? -.2 - Math.sin(t * 5) * .5 : Math.PI + .2 + Math.sin(t * 5) * .5;
  const reach = (kind === 'hunt' ? 8 + Math.max(0, Math.sin(t * 6)) * 4 : 8) * s;
  const hand = [sh[0] + Math.cos(ang) * reach, sh[1] + Math.sin(ang) * reach];
  ctx.beginPath(); ctx.moveTo(...sh); ctx.lineTo(...hand); ctx.stroke(); ctx.lineCap = 'butt';
  drawTool(TOOL_KIND[kind], hand, ang, s, t, an, gx, gy, side);
  if (kind === 'pick' || kind === 'eat') blob(ctx, hand[0], hand[1], 1.8 * s, '#e0334e');
  if (kind === 'craft' && Math.sin(t * 9) > .6) blob(ctx, hand[0] + side * 3, hand[1] - 2, 1.5, '#ffe9a0');
  if ((kind === 'love' || kind === 'care') && Math.sin(t * 3) > 0) { ctx.font = `${9 * s}px system-ui`; ctx.fillText('❤', gx + side * 9 * s, hy - 8 * s - (t * 8 % 8)); }
  if (['chop', 'mine', 'hammer'].includes(kind) && swing > .93 && Math.random() < .5) spark(an, gx, gy, kind);
  if (d.moving && a.carry) carry(a.carry, gx, by, s, side);             // carrying a load home
  blob(ctx, gx, hy, 6 * s, skin);
  ctx.fillStyle = hair; ctx.beginPath(); ctx.arc(gx, hy - 1 * s, 6.2 * s, Math.PI * 1.05, Math.PI * 1.95); ctx.fill();
  ctx.fillStyle = '#1a1a1a';
  if (kind === 'rest' || a.mood === 'exhausted') { ctx.fillRect(gx - 2.8 * s, hy + .6 * s, 1.8 * s, .7 * s); ctx.fillRect(gx + 1.1 * s, hy + .6 * s, 1.8 * s, .7 * s); }
  else { ctx.fillRect(gx - 2.6 * s, hy, 1.4 * s, 1.6 * s); ctx.fillRect(gx + 1.3 * s, hy, 1.4 * s, 1.6 * s); }
  if (kind === 'talk' && Math.sin(t * 12) > 0) { ctx.fillStyle = '#5a2a2a'; ctx.fillRect(gx - 1 * s, hy + 3 * s, 2 * s, 1.2 * s); }
  return [gx, hy - 7 * s];
}
function drawTool(tool, hand, ang, s, t, an, gx, gy, side) {
  if (!tool) return;
  const dx = Math.cos(ang), dy = Math.sin(ang), at = l => [hand[0] + dx * l * s, hand[1] + dy * l * s];
  ctx.lineCap = 'round';
  if (tool === 'rod') {                                                 // a fishing rod, line and bobbing float
    const tip = [hand[0] + side * 12 * s, hand[1] - 12 * s];
    ctx.strokeStyle = '#7a5530'; ctx.lineWidth = 1.4 * s; ctx.beginPath(); ctx.moveTo(...hand); ctx.lineTo(...tip); ctx.stroke();
    const fx = gx + (an[2] - an[3]) * TW / 2 * .9, fy = gy + (an[2] + an[3]) * TH / 2 * .9 + Math.sin(t * 4) * 1.2;
    ctx.strokeStyle = 'rgba(255,255,255,.7)'; ctx.lineWidth = .7; ctx.beginPath(); ctx.moveTo(...tip); ctx.quadraticCurveTo(tip[0], fy - 4, fx, fy); ctx.stroke();
    blob(ctx, fx, fy, 1.8, '#e23b3b');
    return;
  }
  const len = { axe: 10, pick: 10, hammer: 8, hoe: 15, spear: 18 }[tool];
  const end = at(len), start = tool === 'spear' ? at(-6) : hand;
  ctx.strokeStyle = '#7a5530'; ctx.lineWidth = 1.8 * s; ctx.beginPath(); ctx.moveTo(...start); ctx.lineTo(...end); ctx.stroke();
  const nx = -dy, ny = dx;                                              // across the handle
  ctx.fillStyle = '#9aa1aa'; ctx.strokeStyle = '#9aa1aa'; ctx.lineWidth = 2 * s;
  if (tool === 'axe') { ctx.beginPath(); ctx.moveTo(end[0], end[1]); ctx.lineTo(end[0] + nx * 4 * s - dx * 2 * s, end[1] + ny * 4 * s - dy * 2 * s); ctx.lineTo(end[0] + nx * 4 * s + dx * 2 * s, end[1] + ny * 4 * s + dy * 2 * s); ctx.closePath(); ctx.fill(); }
  if (tool === 'pick') { ctx.beginPath(); ctx.moveTo(end[0] - nx * 4 * s, end[1] - ny * 4 * s); ctx.quadraticCurveTo(end[0] + dx * 2 * s, end[1] + dy * 2 * s, end[0] + nx * 4 * s, end[1] + ny * 4 * s); ctx.stroke(); }
  if (tool === 'hammer') { ctx.fillRect(end[0] - 2.5 * s, end[1] - 2.5 * s, 5 * s, 5 * s); }
  if (tool === 'hoe') { ctx.beginPath(); ctx.moveTo(...end); ctx.lineTo(end[0] + nx * 3 * s, end[1] + ny * 3 * s + 2 * s); ctx.stroke(); }
  if (tool === 'spear') { ctx.beginPath(); ctx.moveTo(...end); ctx.lineTo(...at(len + 3)); ctx.stroke(); }
  ctx.lineCap = 'butt';
}
function carry(what, gx, by, s, side) {
  if (what === 'wood') { ctx.save(); ctx.translate(gx, by); ctx.rotate(-.35 * side); ctx.fillStyle = '#8a5a2b'; ctx.fillRect(-9 * s, -3 * s, 18 * s, 4 * s);
    ctx.fillStyle = '#c8a06a'; ctx.beginPath(); ctx.arc(9 * s, -1 * s, 2 * s, 0, 7); ctx.fill(); ctx.restore(); }
  else if (what === 'stone') blob(ctx, gx + side * 7 * s, by + 9 * s, 3.2 * s, '#9aa0a8');
  else if (what === 'food') { ctx.fillStyle = '#b07c3c'; ctx.fillRect(gx + side * 5 * s, by + 7 * s, 6 * s, 4 * s);
    blob(ctx, gx + side * 7 * s, by + 7 * s, 1.5 * s, '#e0334e'); blob(ctx, gx + side * 9 * s, by + 7 * s, 1.5 * s, '#e0334e'); }
}
// wood chips and sparks fly from whatever is being worked on
S.parts = [];
function spark(an, gx, gy, kind) {
  const x = gx + an[2] * TW / 2 - an[3] * TW / 2, y = gy + (an[2] + an[3]) * TH / 2 - 8;
  for (let i = 0; i < 3; i++) S.parts.push({ x, y, vx: (Math.random() - .5) * 40, vy: -20 - Math.random() * 30, life: .6,
    c: kind === 'chop' ? '#c8954f' : kind === 'mine' ? '#ffe27a' : '#d8c8a8' });
}
function drawParts(dt) {
  S.parts = S.parts.filter(p => (p.life -= dt) > 0);
  for (const p of S.parts) { p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 80 * dt; ctx.globalAlpha = Math.min(1, p.life * 2); ctx.fillStyle = p.c; ctx.fillRect(p.x, p.y, 1.8, 1.8); }
  ctx.globalAlpha = 1;
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
  else if (a.mood_icon && !a.asleep && !['🙂', '😊'].includes(a.mood_icon)) { ctx.font = '11px system-ui'; ctx.fillText(a.mood_icon, x + 15, top - 2); ctx.font = '12px system-ui'; }
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
  const t = now / 1000, st = S.mapst || S.st, agents = S.mapst ? S.mapst.agents : S.agents, dpr = devicePixelRatio || 1;
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
    S.burning = new Set((st.burning || []).map(([x, y]) => x + ',' + y));
    drawTerritory(st);
    for (const f of st.floods || []) {                                // recent floods: water over the fields
      ctx.fillStyle = `rgba(70,140,220,${.25 + Math.sin(t * 2) * .08})`;
      for (let y = f.y - f.r; y <= f.y + f.r; y++) for (let x = f.x - f.r; x <= f.x + f.r; x++)
        if (S.tiles[y]?.[x] && S.tiles[y][x] !== 'water' && vis(x, y)) { diamond(ctx, x, y); ctx.fill(); }
    }
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
    for (const a of agents) { const d = S.disp[a.name] || a; spots.add(Math.round(d.x) + ',' + Math.round(d.y)); }
    const byTile = {};
    for (const s of st.structures) for (let i = 0; i < s.w; i++) for (let j = 0; j < s.h; j++) byTile[(s.x + i) + ',' + (s.y + j)] = s;
    for (const a of agents) {
      const b = a.inside && byTile[a.x + ',' + a.y];
      if (b) S.inside.add(b.x + ',' + b.y);
      const d = S.disp[a.name] || a;
      if (vis(d.x, d.y)) items.push([b && b.done && !isFlat(b) ? b.x + b.y + b.w + b.h - 1.4 : d.x + d.y + .5, () => drawPerson(a, t)]);
      else S.head[a.name] = null;
    }
    for (const p of S.props || []) if (vis(p.x, p.y)) items.push([p.x + p.y, () => drawProp(p, spots.has((p.x - 1) + ',' + (p.y - 1)) || spots.has(p.x + ',' + (p.y - 1)) || spots.has((p.x - 1) + ',' + p.y), t)]);
    for (const b of st.animals || []) { const d = S.adisp[b[0]] || { x: b[2], y: b[3] }; if (vis(d.x, d.y)) items.push([d.x + d.y + .45, () => drawAnimal(b, t)]); }
    for (const s of st.structures) if (vis(s.x + s.w / 2, s.y + s.h / 2)) items.push([isFlat(s) ? -1e6 + s.x + s.y : s.x + s.y + s.w + s.h - 1.5, () => drawBuilding(s, t)]);
    for (const g of st.dead) if (vis(g.x, g.y)) items.push([g.x + g.y + .2, () => drawGrave(g)]);
    items.sort((p, q) => p[0] - q[0]).forEach(([, f]) => f());
    drawParts(S.dt);
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
    for (const a of agents) personOverlay(a);
    drawPlaces(st);
    drawPopups(t);
    if ($('bubbles').checked) {
      for (const a of agents) if (a.say) drawTalkLine(a);
      for (const a of agents) if (a.say && S.head[a.name]) drawBubble(a);
    }
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawWeather(t);
  requestAnimationFrame(drawFrame);
}

// territory: each group's land, outlined in its colour (cached as a path per group)
const TERR = {};
function drawTerritory(st) {
  for (const g of st.groups || []) {
    const tiles = st.territory?.[g.id] || [], key = tiles.length + ':' + (tiles[0] || '') + (tiles[tiles.length - 1] || '');
    if (!tiles.length) continue;
    if (!TERR[g.id] || TERR[g.id].key !== key) {
      const set = new Set(tiles.map(([x, y]) => x + ',' + y)), edge = new Path2D(), fill = new Path2D();
      for (const [x, y] of tiles) {
        const p = [iso(x, y), iso(x + 1, y), iso(x + 1, y + 1), iso(x, y + 1)];
        fill.moveTo(...p[0]); p.slice(1).forEach(q => fill.lineTo(...q)); fill.closePath();
        [[0, -1, 0, 1], [1, 0, 1, 2], [0, 1, 2, 3], [-1, 0, 3, 0]].forEach(([dx, dy, i, j]) => {
          if (!set.has((x + dx) + ',' + (y + dy))) { edge.moveTo(...p[i]); edge.lineTo(...p[j]); } });
      }
      TERR[g.id] = { key, edge, fill };
    }
    ctx.globalAlpha = .1; ctx.fillStyle = g.color; ctx.fill(TERR[g.id].fill);
    ctx.globalAlpha = .75; ctx.strokeStyle = g.color; ctx.lineWidth = 1.6; ctx.setLineDash([6, 4]); ctx.stroke(TERR[g.id].edge);
    ctx.setLineDash([]); ctx.globalAlpha = 1;
  }
}
function drawPlaces(st) {
  ctx.font = 'italic 600 13px Georgia, serif'; ctx.textAlign = 'center';
  for (const p of st.places || []) {
    const [x, y] = scr(...ground(p.x, p.y));
    if (x < -80 || y < -20 || x > scroller.clientWidth + 80 || y > scroller.clientHeight + 20) continue;
    ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(20,20,30,.6)'; ctx.strokeText(p.name, x, y - 28);
    ctx.fillStyle = '#fff4d6'; ctx.fillText(p.name, x, y - 28);
  }
}
// "+wood" popups when someone gets something done, floating up and fading
const POP = { chop: '🪵', mine: '🪨', pick: '🫐', fish: '🐟', hunt: '🍖', hammer: '🔨', hoe: '🌱', craft: '🔧', care: '🍼', love: '❤️', tame: '🐐', give: '🎁' };
function drawPopups(t) {
  const now = performance.now();
  S.popups = S.popups.filter(p => now - p.born < 1600);
  ctx.font = '15px system-ui'; ctx.textAlign = 'center';
  for (const p of S.popups) {
    const H = S.head[p.name]; if (!H) continue;
    const k = (now - p.born) / 1600, [x, y] = scr(H.x, H.y);
    ctx.globalAlpha = 1 - k; ctx.fillText(p.icon, x + 14, y - 12 - k * 26); ctx.globalAlpha = 1;
  }
}
// weather: snow in winter, falling leaves in autumn, petals in spring
const FLAKES = Array.from({ length: 90 }, () => ({ x: Math.random(), y: Math.random(), s: .5 + Math.random(), p: Math.random() * 6 }));
function drawWeather(t) {
  const sea = season(), w = scroller.clientWidth, h = scroller.clientHeight;
  if (sea === 'summer') return;
  const n = sea === 'winter' ? 90 : sea === 'autumn' ? 30 : 14;
  for (let i = 0; i < n; i++) {
    const f = FLAKES[i], fall = sea === 'winter' ? 22 : 34;
    const y = ((f.y * h + t * fall * f.s) % (h + 20)) - 10, x = ((f.x * w + Math.sin(t * .7 + f.p) * 18 + (sea === 'autumn' ? t * 12 : 0)) % (w + 20)) - 10;
    if (sea === 'winter') blob(ctx, x, y, 1.2 + f.s, 'rgba(255,255,255,.8)');
    else { ctx.save(); ctx.translate(x, y); ctx.rotate(t * f.s + f.p); ctx.fillStyle = sea === 'autumn' ? ['#d9822b', '#c4492c', '#e0b03a'][i % 3] : '#f8c8e0';
      ctx.beginPath(); ctx.ellipse(0, 0, 3.5, 1.8, 0, 0, 7); ctx.fill(); ctx.restore(); }
  }
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
  const SE = { spring: '🌱', summer: '☀️', autumn: '🍂', winter: '❄️' };
  if (st.season) $('p-season').textContent = `${SE[st.season]} ${st.season[0].toUpperCase() + st.season.slice(1)} · 🏛️ ${st.age_name}`;
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
  if (name === 'history') loadHistory();
  if (name === 'world') renderWorld(S.st, true);
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
      <div><div class="name">${esc(a.name)} <span class="muted" title="${a.sex}">${SEX[a.sex]}</span> <span title="${a.stage === 'baby' ? 'babies don\'t use a brain' : a.tier}">${a.stage === 'baby' ? '' : TIER[a.tier]}</span> ${extras(a)}${a.asleep && a.stage !== 'baby' ? ' 💤' : ` <span title="${esc(a.mood || '')}">${a.mood_icon || ''}</span>`}${a.slow ? ' 💭' : ''}${groupDot(st, a)}</div>
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
    ${society(a)}
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
const FILTERS = { all: 'All', sol: '🧙 Sol', talk: '💬 Talk', life: '❤️ Life', society: '🤝 Society', culture: '📖 Culture', making: '🔨 Making', ideas: '💡 Ideas', nature: '🌿 Nature', explore: '🧭 Exploring', survival: '🍎 Food' };
const KIND_FILTER = { trade: 'society', group: 'society', law: 'society', contact: 'society', story: 'culture', nature: 'nature', dream: 'ideas', sol: 'sol', discovery: 'ideas', attempt: 'ideas', goal: 'ideas', care: 'life', birth: 'life', death: 'life', love: 'life', gift: 'life', build: 'making', craft: 'making', farm: 'making',
  idea: 'ideas', explore: 'explore', food: 'survival', role: 'life', brain: 'life' };
const KIND_ICON = { trade: '🤝', group: '👥', law: '⚖️', contact: '🌍', story: '📖', nature: '🌿', dream: '🌙', sol: '🧙', discovery: '💡', attempt: '✨', goal: '🎯', care: '🍼', birth: '👶', death: '🪦', love: '❤️', gift: '🎁', build: '🏗️', craft: '🔧', farm: '🌾', idea: '💡', explore: '🧭', food: '🍎', role: '🎭', brain: '🧠', talk: '💬' };
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
  ['structures', 'Structures'], ['farms', 'Farm plots'], ['objects', 'Objects'], ['ideas', 'Ideas'], ['discoveries', 'Discoveries'], ['techs', 'Breakthroughs'], ['animals', 'Wild animals'], ['groups', 'Groups']];
$('charts').innerHTML = METRICS.map(([k, l]) => `<div class="chart"><div class="title"><span>${l}</span><b id="v-${k}">–</b></div><canvas id="c-${k}" data-k="${k}"></canvas></div>`).join('');
async function loadStats() { S.stats = await api.get('/api/stats'); drawCharts(); }
function drawCharts() {
  const data = S.stats; if (!data.length) return;
  const css = getComputedStyle(document.documentElement), line = css.getPropertyValue('--accent').trim(), grid = '#2c343e', ink = '#8590a0';
  for (const [k] of METRICS) {
    const c = $('c-' + k), dpr = devicePixelRatio || 1, w = c.clientWidth, h = c.clientHeight;
    c.width = w * dpr; c.height = h * dpr;
    const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
    const ys = data.map(d => d[k] ?? 0), max = Math.max(1, ...ys), padL = 26, padB = 14, pw = w - padL - 6, ph = h - padB - 6;
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
  $('readout').innerHTML = `<b>${ts(d.day, true)}</b> — ` + METRICS.map(([k, l]) => `${l}: <b>${fmt(d[k] ?? 0)}${k === 'explored' ? '%' : ''}</b>`).join(' · ') + ` · Deaths so far: <b>${d.deaths}</b>`;
  if ($('stats-table').checked) {
    const step = Math.max(1, Math.ceil(data.length / 30)), rows = data.filter((_, i) => i % step === 0 || i === data.length - 1).reverse();
    $('table').innerHTML = `<table><tr><th>When</th>${METRICS.map(([, l]) => `<th>${l}</th>`).join('')}</tr>` +
      rows.map(r => `<tr><td>${ts(r.day)}</td>${METRICS.map(([k]) => `<td>${fmt(r[k] ?? 0)}</td>`).join('')}</tr>`).join('') + '</table>';
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
  const brains = B.mock ? '🎭 Mock (scripted, not real thinking)' : [B.local ? '🖥️ Local: ' + esc(B.local_model) : '', B.claude ? '🌱 Claude (Haiku / Sonnet / Opus)' : ''].filter(Boolean).join(' · ');
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
  else if ('123456'.includes(k) && k.length === 1) showTab(['people', 'talk', 'world', 'stats', 'history', 'settings'][+k - 1]);
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
    if (S.tab === 'world') renderWorld(st);
    S.mapst = S.replay ? replayState(S.replay, st) : null;
  } catch (e) { console.error(e); }
  polling = false;
  if (pollAgain) { pollAgain = false; poll(); }
}
async function loadWorld() {
  const w = await api.get('/api/world');
  S.W = w.width; S.H = w.height; S.tiles = w.tiles;
  WW = (S.W + S.H) * TW / 2 + PAD * 2; WH = (S.W + S.H) * TH / 2 + TOP + PAD;
  BG_SCALE = Math.min(2, 4600 / WW);
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


// ======================================================================= world: ages, groups, trade, culture, nature
const groupDot = (st, a) => { const g = (st.groups || []).find(g => g.id === a.group); return g ? ` <span class="dot" title="${esc(g.name)}" style="background:${g.color};margin:0 0 0 4px"></span>` : ''; };
let worldKey = '';
function renderWorld(st, force) {
  if (!st) return;
  const key = JSON.stringify([st.techs, st.groups, st.deals, st.promises, st.stories?.length, st.places, st.animals?.length, st.burning?.length, st.season]);
  if (key === worldKey && !force) return;
  worldKey = key;
  const left = st.tech_total - st.techs.length;
  $('techs').innerHTML = `<div class="card"><b>${esc(st.age_name)}</b> · ${st.techs.length} of ${st.tech_total} breakthroughs
      <div class="techs">${st.techs.map(x => `<span class="tech" title="${esc(x.what)}">✨ ${esc(x.name)}</span>`).join('')}${'<span class="tech locked" title="Undiscovered - agents find these by attempting things">❔</span>'.repeat(left)}</div>
      <div class="muted small">Nobody is told what's possible: breakthroughs are found by attempting things (fire, tools, farming, pottery, weaving, bronze…). Hover one to see what it does.</div></div>`;
  $('groups').innerHTML = (st.groups || []).map(g => `<div class="card" style="border-left:4px solid ${g.color}">
      <b style="color:${g.color}">${esc(g.name)}</b> <span class="muted small">led by ${esc(g.leader || 'nobody')}${g.purpose ? ' · ' + esc(g.purpose) : ''}</span>
      <div class="chips" style="margin:6px 0">${g.members.map(m => `<span class="chip" data-goto="${esc(m)}">${esc(m)}${m === g.leader ? ' 👑' : ''}</span>`).join('')}</div>
      ${g.plan ? `<div class="small">🗺️ ${esc(g.plan)}</div>` : ''}
      ${g.laws.length ? `<div class="small" style="margin-top:4px">⚖️ ${g.laws.map(l => `<div>“${esc(l.text)}”${l.rule ? '' : ' <span class="muted">(unwritten)</span>'}</div>`).join('')}</div>` : ''}
      ${g.proposals.length ? `<div class="small muted">Proposed: ${g.proposals.map(p => `“${esc(p.text)}” (${p.support.length}/${g.members.length})`).join(', ')}</div>` : ''}
      ${g.banned.length ? `<div class="small muted">Exiled: ${g.banned.map(esc).join(', ')}</div>` : ''}</div>`).join('')
    || '<p class="muted small">No groups yet. Agents can found a group, choose a leader, make laws and claim land.</p>';
  const bundle = b => Object.entries(b || {}).map(([k, v]) => `${v} ${k}`).join(', ') || 'nothing';
  const deals = (st.deals || []).slice().reverse().slice(0, 8).map(d => `<div class="small">🤝 ${esc(d.from)} → ${esc(d.to)}: ${bundle(d.give)} for ${bundle(d.want)} <span class="tag">${d.status}</span></div>`).join('');
  const proms = (st.promises || []).slice().reverse().slice(0, 8).map(p => `<div class="small">${p.status === 'broken' ? '💔' : p.status === 'kept' ? '✅' : '⏳'} ${esc(p.from)} promised ${esc(p.to)} ${bundle(p.what)} <span class="tag">${p.status}</span></div>`).join('');
  $('trade').innerHTML = deals || proms ? `<div class="card">${deals}${proms ? '<div style="margin-top:6px"></div>' + proms : ''}</div>` : '<p class="muted small">No trades yet. Agents can offer deals and make promises; broken promises cost trust.</p>';
  $('culture').innerHTML = ((st.stories || []).slice().reverse().map(x => `<div class="disc"><b>📖 ${esc(x.title)}</b>${x.version > 1 ? ` <span class="tag">retold ${x.version}×</span>` : ''}<div>${esc(x.text)}</div></div>`).join('')
    || '<p class="muted small">No stories yet. Sol turns memorable events into stories that spread around the fire.</p>')
    + ((st.places || []).length ? `<div class="small" style="margin-top:6px">📍 ${st.places.map(p => `<b>${esc(p.name)}</b> <span class="muted">(${p.x}, ${p.y}, named by ${esc(p.by)})</span>`).join(' · ')}</div>` : '');
  const count = {};
  for (const b of st.animals || []) { const k = b[1] + (b[4] ? ' (tame)' : ''); count[k] = (count[k] || 0) + 1; }
  $('nature').innerHTML = `<div class="card small">${Object.entries(count).map(([k, v]) => `${{ deer: '🦌', rabbit: '🐇', boar: '🐗', goat: '🐐', sheep: '🐑' }[k.split(' ')[0]] || '🐾'} ${v} ${k}`).join(' · ') || 'No animals left nearby.'}
    ${st.burning?.length ? `<div>🔥 A wildfire is burning (${st.burning.length} trees)</div>` : ''}${st.floods?.length ? '<div>🌊 Recent flooding</div>' : ''}
    <div class="muted">It is ${st.season}. ${{ winter: 'Bushes are bare, crops don’t grow, nights are freezing outside.', autumn: 'Winter is coming: time to store food.', spring: 'Crops grow fast; rivers may flood.', summer: 'Long days; dry woods can burn.' }[st.season] || ''}</div></div>`;
}
$('tab-world').addEventListener('click', e => { const g = e.target.closest('[data-goto]'); if (g) { showTab('people'); select(g.dataset.goto); } });

// ======================================================================= profile: feelings, skills, beliefs, society
function society(a) {
  if (!a.needs) return '';
  const NI = { rest: '😴 Rest', belonging: '🤝 Company', safety: '🛡️ Safety', status: '🏆 Respect', curiosity: '🔭 Curiosity' };
  const st = S.st || {}, g = (st.groups || []).find(g => g.id === a.group);
  const bundle = b => Object.entries(b || {}).map(([k, v]) => `${v} ${k}`).join(', ');
  return `<h3>Feelings</h3><div class="card">${a.mood_icon || ''} Feels <b>${esc(a.mood || 'content')}</b>${a.grief ? ' · grieving' : ''}${a.anger ? ' · angry' : ''}
      <div class="muted small">Each need rises over time; the strongest one (weighted by personality) sets the mood. Higher = wants it more.</div></div>
    ${Object.entries(a.needs).map(([k, v]) => `<div title="${esc(a.need_info?.[k] || '')}">${meter(NI[k] || k, v, v >= 70 ? 'var(--bad)' : v >= 45 ? 'var(--warn)' : 'var(--good)')}</div>`).join('')}
    <h3>Skills</h3>${Object.entries(a.skills).map(([k, v]) => `<div title="${esc(a.skill_info?.[k] || '')}">${meter(k[0].toUpperCase() + k.slice(1), v * 10, 'var(--accent)').replace(`<span>${v * 10}</span></div>`, `<span>${v}/10</span></div>`)}</div>`).join('')}
    <p class="muted small">Skills grow by doing (children learn twice as fast) and can be taught.</p>
    ${a.beliefs?.length ? `<h3>Beliefs <span class="muted small" style="text-transform:none;letter-spacing:0">— may be wrong</span></h3>${a.beliefs.map(b => `<div class="card small">💭 ${esc(b.text)} <span class="tag">${b.src || ''}</span></div>`).join('')}` : ''}
    <h3>In society</h3><div class="kv">
      <span>People</span><span>${esc(a.people || '—')}${Object.keys(a.fluency || {}).length ? ` · speaks some ${Object.entries(a.fluency).map(([p, n]) => `${esc(p)} (${Math.min(100, Math.round(n / 8 * 100))}%)`).join(', ')}` : ''}</span>
      <span>Group</span><span>${g ? `<b style="color:${g.color}">${esc(g.name)}</b>${g.leader === a.name ? ' 👑 leader' : ''}` : 'none'}</span>
      <span>Reputation</span><span>${esc(a.reputation || 'unknown')} <span class="muted">(kept ${a.kept}, broken ${a.broken})</span></span>
      ${a.promises?.length ? `<span>Promises</span><span>${a.promises.map(p => p.from === a.name ? `owes ${esc(p.to)} ${bundle(p.left)}` : `${esc(p.from)} owes ${bundle(p.left)}`).join('; ')}</span>` : ''}
      ${a.offenses?.length ? `<span>Offences</span><span>${a.offenses.map(o => `“${esc(o.law)}”${o.dealt ? ` (${o.dealt})` : o.seen.length ? ' (seen)' : ' (unseen)'}`).join('; ')}</span>` : ''}
      ${a.known_stories?.length ? `<span>Knows</span><span>${a.known_stories.map(t => `📖 ${esc(t)}`).join(', ')}</span>` : ''}
    </div>`;
}

// ======================================================================= history: chronicle, family tree, replay
async function loadHistory() {
  S.history = await api.get('/api/history');
  const H = S.history;
  $('chronicle').innerHTML = H.chronicle.length ? H.chronicle.slice().reverse().map(c => `<div class="chapter"><div class="tag">${esc(c.when)}</div><b>${esc(c.title)}</b><p>${esc(c.text)}</p></div>`).join('')
    : '<p class="muted small">Sol writes a chapter of the history book at the first review of each month.</p>';
  const kids = {};
  for (const p of H.family) for (const par of p.parents) (kids[par] ||= []).push(p);
  const known = new Set(H.family.map(p => p.name));
  const node = (p, depth) => `<div class="fam" style="margin-left:${depth * 16}px"><span class="dot" style="background:${p.color}"></span>
      <a href="#" data-goto="${esc(p.name)}" class="${p.alive ? '' : 'muted'}">${esc(p.name)}</a> ${p.sex === 'female' ? '♀' : '♂'}${p.alive ? '' : ' 🪦'}
      ${p.parents.length > 1 ? `<span class="muted small">(${esc(p.parents.join(' + '))})</span>` : ''} <span class="muted small">${esc(p.people || '')}</span></div>`
    + (kids[p.name] || []).filter(c => c.parents[0] === p.name || !known.has(c.parents[0])).map(c => node(c, depth + 1)).join('');
  $('family').innerHTML = H.family.filter(p => !p.parents.some(n => known.has(n))).map(p => node(p, 0)).join('') || '<p class="muted small">Nobody yet.</p>';
  const r = $('replay');
  r.max = Math.max(0, H.snapshots.length - 1);
  if (!S.replay) r.value = r.max;
}
$('family').onclick = e => { const g = e.target.closest('[data-goto]'); if (g) { e.preventDefault(); showTab('people'); select(g.dataset.goto); } };
$('replay').oninput = e => {
  const snap = S.history?.snapshots[+e.target.value];
  if (!snap) return;
  if (+e.target.value >= S.history.snapshots.length - 1) return backToLive();
  S.replay = snap; S.mapst = replayState(snap, S.st);
  $('replay-when').textContent = `${ts(snap.t, true)} · ${snap.pop} alive`;
  $('replay-live').hidden = false;
  document.body.classList.add('replaying');
};
function backToLive() {
  S.replay = null; S.mapst = null; $('replay-live').hidden = true; $('replay-when').textContent = 'drag to look back in time';
  document.body.classList.remove('replaying');
  if (S.history) $('replay').value = $('replay').max;
}
$('replay-live').onclick = backToLive;
function replayState(snap, live) {
  return { ...live, agents: snap.a.map(([name, x, y, color, stage]) => ({ name, x, y, color, stage, adult: stage !== 'child' && stage !== 'baby',
    hunger: 0, say: '', anim: [], asleep: false, mood_icon: '', task: null, inside: '', doing: '' })),
    structures: snap.b.map(([x, y, w, h, kind, func, done, group]) => ({ x, y, w, h, kind, func, done: !!done, progress: 0, work: 1, walkable: true, group })),
    animals: [], burning: [], floods: [], territory: {}, groups: [], dead: [] };
}
setInterval(() => { if (S.tab === 'history' && !S.replay) loadHistory(); }, 10000);

// where the Human is looking: agents far from it think less often (cheaper), see society/engine.py
let lastFocus = '';
setInterval(() => {
  if (!S.W) return;
  const { fx, fy } = unIso(S.cam.x + scroller.clientWidth / 2 / S.zoom, S.cam.y + scroller.clientHeight / 2 / S.zoom);
  const f = [Math.round(Math.max(0, Math.min(S.W - 1, fx))), Math.round(Math.max(0, Math.min(S.H - 1, fy)))], k = f.join(',');
  if (k !== lastFocus) { lastFocus = k; api.post('/api/control', { focus: f }); }
}, 4000);
