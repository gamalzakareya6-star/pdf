// The document canvas: continuous scrolling pages, zoom, touch gestures and all editing tools.
import { S, addEdit, addEdits, replaceEdit, commitEdits } from './state.js';
import * as R from './render.js';
import { drawEdit, bboxOf, hitTest, translateEdit, RECT_LIKE, layoutText, PAD, norm, setImageLoadHandler, PENS, FONTS, stampShapes } from './draw.js';
import { askText, toast, h } from './ui.js';
import { t } from './i18n.js';

export const COLORS = ['#1c1c1e', '#ff3b30', '#ff9f0a', '#ffd60a', '#34c759', '#00c7be', '#4f9dff', '#2f4bff', '#af52de', '#ff6bb5', '#8e5a3c', '#8e8e93', '#ffffff'];
const DEFAULT_COLORS = { hl: '#ffd60a', ul: '#2f6bff', st: '#ff3b30', draw: '#2f4bff', text: '#1c1c1e', note: '#1c1c1e', stamp: '#e5484d' };
const LOCK_TOOLS = new Set(['hl', 'ul', 'st', 'ink', 'rect', 'ellipse', 'line', 'arrow', 'redact', 'erase']);
const SHAPES = new Set(['rect', 'ellipse', 'line', 'arrow', 'redact']);
const MARGIN = 10;
const GAP = 12;
const MIN_Z = 0.2, MAX_Z = 6;

export const V = {
  zoom: 1, fit: true, tool: 'hand', page: 0,
  colors: { ...DEFAULT_COLORS }, size: 16, font: 'sans', bold: false,
  pen: 'ballpoint', pens: JSON.parse(JSON.stringify(PENS)),
  shape: { w: 3, op: 1 }, dash: 0, fill: false, head: 'v', stamp: 'check', stampSize: 34,
  erasing: null,
  sel: null,            // selected edit {page, idx}
  tsel: null,           // selected text {page, a, b}
  draft: null, preview: null,
  search: { hits: {}, cur: null, list: [] },
  imageData: null,      // {data, kind, w, h} used by image / signature tools
  invert: false,
  on: {},               // callbacks: page, tool, selection, zoom, needImage
};
const emit = (name, ...a) => { if (V.on[name]) V.on[name](...a); };

export const colorFor = (tool = V.tool) => V.colors[tool === 'ink' ? 'draw' : (SHAPES.has(tool) ? 'draw' : tool)] || V.colors.draw;
export function setColor(c, tool = V.tool) {
  const k = ['hl', 'ul', 'st', 'text', 'note', 'stamp'].includes(tool) ? tool : 'draw';
  V.colors[k] = c;
}

let scroller, pagesEl, infos = [], els = [], io = null;
const dpr = Math.min(window.devicePixelRatio || 1, 3);
let down = null;
let pinch = null;
let lastTap = null;
let editor = null;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ------------------------------------------------------------------------------------------------
// setup
// ------------------------------------------------------------------------------------------------
export function initView(scrollerEl, pagesContainer) {
  scroller = scrollerEl; pagesEl = pagesContainer;
  scroller.addEventListener('scroll', onScroll, { passive: true });
  scroller.addEventListener('pointerdown', onDown);
  scroller.addEventListener('pointermove', onMove);
  scroller.addEventListener('pointerup', onUp);
  scroller.addEventListener('pointercancel', onCancel);
  scroller.addEventListener('touchstart', onTouchStart, { passive: false });
  scroller.addEventListener('touchmove', onTouchMove, { passive: false });
  scroller.addEventListener('touchend', onTouchEnd, { passive: false });
  scroller.addEventListener('touchcancel', onTouchEnd, { passive: false });
  scroller.addEventListener('wheel', onWheel, { passive: false });
  scroller.addEventListener('contextmenu', (e) => { if (down) e.preventDefault(); });
  window.addEventListener('resize', () => { if (V.fit && els.length) { fitWidth(); } });
  setImageLoadHandler(() => redrawAll());
}

export async function rebuild(keepPage = true) {
  const keep = keepPage ? V.page : 0;
  closeEditor(false);
  if (io) io.disconnect();
  els.forEach((r) => { try { r.task && r.task.cancel(); } catch (e) { /* ignore */ } });
  pagesEl.textContent = '';
  els = [];
  const n = S.pageCount;
  infos = await Promise.all(Array.from({ length: n }, (_, i) => R.info(i)));
  V.sel = null; V.tsel = null; V.draft = null; V.preview = null;
  V.search = { hits: {}, cur: null, list: [] };
  io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      const i = +en.target.dataset.i;
      const r = els[i];
      if (!r) continue;
      r.vis = en.isIntersecting;
      if (r.vis) ensure(i); else release(i);
    }
  }, { root: scroller, rootMargin: '110% 0px' });
  for (let i = 0; i < n; i++) {
    const pdf = h('canvas', { class: 'pdf' });
    const ov = h('canvas', { class: 'ov' });
    const wrap = h('div', { class: 'page', 'data-i': i }, pdf, ov);
    pagesEl.append(wrap);
    els.push({ wrap, pdf, ov, key: '', task: null, tok: 0, vis: false });
  }
  if (V.fit || !V.zoom) computeFit(Math.min(keep, n - 1));
  layout();
  els.forEach((r) => io.observe(r.wrap));
  V.page = clamp(keep, 0, Math.max(0, n - 1));
  requestAnimationFrame(() => goTo(V.page, false));
  emit('page', V.page);
  emit('zoom', V.zoom);
}

function computeFit(i = V.page) {
  if (!infos.length) return;
  const pw = infos[clamp(i, 0, infos.length - 1)].w;
  V.zoom = clamp((scroller.clientWidth - 2 * MARGIN) / pw, MIN_Z, MAX_Z);
}

function layout() {
  els.forEach((r, i) => {
    r.wrap.style.width = infos[i].w * V.zoom + 'px';
    r.wrap.style.height = infos[i].h * V.zoom + 'px';
  });
}

// ------------------------------------------------------------------------------------------------
// rendering
// ------------------------------------------------------------------------------------------------
async function ensure(i) {
  const r = els[i];
  if (!r || !r.vis) return;
  const key = V.zoom.toFixed(4) + '|' + R.version;
  if (r.key === key) { redraw(i); return; }
  r.key = key;
  const my = ++r.tok;
  try { r.task && r.task.cancel(); } catch (e) { /* ignore */ }
  let scale = V.zoom * dpr;
  const px = infos[i].w * infos[i].h * scale * scale;
  if (px > 12e6) scale *= Math.sqrt(12e6 / px);
  try {
    const task = await R.renderTo(i, r.pdf, scale);
    if (my !== r.tok) { task.cancel(); return; }
    r.task = task;
    await task.promise;
  } catch (e) {
    if (!e || e.name !== 'RenderingCancelledException') console.warn('render failed', e);
    if (my === r.tok) r.key = '';
    return;
  }
  if (my !== r.tok) return;
  r.wrap.classList.add('ready');
  redraw(i);
  R.getText(i).catch(() => {});
}

function release(i) {
  const r = els[i];
  if (!r) return;
  r.tok++; r.key = '';
  try { r.task && r.task.cancel(); } catch (e) { /* ignore */ }
  r.pdf.width = 1; r.pdf.height = 1; r.ov.width = 1; r.ov.height = 1;
  r.wrap.classList.remove('ready');
}

export function invalidateAll() { els.forEach((r, i) => { r.key = ''; if (r.vis) ensure(i); }); }
export function redrawAll() { els.forEach((r, i) => { if (r.vis) redraw(i); }); }

export function redraw(i) {
  const r = els[i];
  if (!r || !r.vis || !infos[i]) return;
  const w = Math.round(infos[i].w * V.zoom * dpr), hh = Math.round(infos[i].h * V.zoom * dpr);
  if (r.ov.width !== w || r.ov.height !== hh) { r.ov.width = w; r.ov.height = hh; }
  const ctx = r.ov.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, w, hh);
  const s = V.zoom * dpr;
  ctx.setTransform(s, 0, 0, s, 0, 0);

  const hits = V.search.hits[i];
  if (hits) {
    hits.forEach((rects, k) => {
      const cur = V.search.cur && V.search.cur.page === i && V.search.cur.k === k;
      ctx.fillStyle = cur ? 'rgba(255,140,0,.55)' : 'rgba(255,214,10,.45)';
      for (const q of rects) ctx.fillRect(q[0], q[1], q[2] - q[0], q[3] - q[1]);
    });
  }
  const list = S.edits[i] || [];
  list.forEach((e, idx) => {
    if (V.erasing && V.erasing.page === i && V.erasing.set.has(idx)) return;
    const eff = V.preview && V.preview.page === i && V.preview.idx === idx ? V.preview.edit : e;
    drawEdit(ctx, eff);
  });
  if (V.draft && V.draft.page === i) drawEdit(ctx, V.draft.edit);

  if (V.tsel && V.tsel.page === i) {
    const words = textNow(i);
    ctx.fillStyle = 'rgba(79,107,237,.35)';
    if (words) for (const q of selRects(words, V.tsel)) ctx.fillRect(q[0], q[1], q[2] - q[0], q[3] - q[1]);
  }
  if (V.sel && V.sel.page === i) {
    const e = V.preview && V.preview.page === i && V.preview.idx === V.sel.idx ? V.preview.edit : list[V.sel.idx];
    if (e) {
      const b = bboxOf(e);
      ctx.save();
      ctx.strokeStyle = '#4f6bed'; ctx.lineWidth = 1.5 / V.zoom; ctx.setLineDash([5 / V.zoom, 4 / V.zoom]);
      ctx.strokeRect(b.x0 - 2, b.y0 - 2, b.x1 - b.x0 + 4, b.y1 - b.y0 + 4);
      if (RECT_LIKE.has(e.t)) {
        const n = norm(e);
        ctx.setLineDash([]); ctx.fillStyle = '#fff'; ctx.strokeStyle = '#4f6bed'; ctx.lineWidth = 2 / V.zoom;
        ctx.beginPath(); ctx.arc(n.x1, n.y1, 8 / V.zoom, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      ctx.restore();
    }
  }
}

// text cache (sync access for drawing); filled by R.getText
const textMem = new Map();
function textNow(i) { return textMem.get(i + ':' + R.version) || null; }
async function textFor(i) {
  const k = i + ':' + R.version;
  if (!textMem.has(k)) textMem.set(k, (await R.getText(i)).words);
  return textMem.get(k);
}

// ------------------------------------------------------------------------------------------------
// zoom / scroll / pages
// ------------------------------------------------------------------------------------------------
function anchorRef(cx, cy) {
  let best = 0, bd = Infinity;
  els.forEach((r, i) => {
    const b = r.wrap.getBoundingClientRect();
    const d = cy < b.top ? b.top - cy : (cy > b.bottom ? cy - b.bottom : 0);
    if (d < bd) { bd = d; best = i; }
  });
  const b = els[best].wrap.getBoundingClientRect();
  return { i: best, ox: (cx - b.left) / V.zoom, oy: (cy - b.top) / V.zoom };
}
function restoreAnchor(ref, cx, cy) {
  const b = els[ref.i].wrap.getBoundingClientRect();
  scroller.scrollTop += b.top + ref.oy * V.zoom - cy;
  scroller.scrollLeft += b.left + ref.ox * V.zoom - cx;
}

export function setZoom(z, cx, cy) {
  if (!els.length) return;
  z = clamp(z, MIN_Z, MAX_Z);
  if (Math.abs(z - V.zoom) < 1e-3) return;
  const sr = scroller.getBoundingClientRect();
  if (cx == null) { cx = sr.left + sr.width / 2; cy = sr.top + sr.height / 2; }
  const ref = anchorRef(cx, cy);
  V.fit = false; V.zoom = z;
  layout();
  restoreAnchor(ref, cx, cy);
  invalidateAll();
  emit('zoom', V.zoom);
}
export const zoomBy = (f) => setZoom(V.zoom * f);

export function fitWidth() {
  if (!els.length) return;
  const sr = scroller.getBoundingClientRect();
  const ref = anchorRef(sr.left + sr.width / 2, sr.top + 40);
  V.fit = true; computeFit(V.page);
  layout();
  restoreAnchor(ref, sr.left + sr.width / 2, sr.top + 40);
  invalidateAll();
  emit('zoom', V.zoom);
}

export function goTo(i, smooth = true) {
  if (!els.length) return;
  i = clamp(i, 0, els.length - 1);
  scroller.scrollTo({ top: els[i].wrap.offsetTop - MARGIN, behavior: smooth ? 'smooth' : 'auto' });
  if (V.page !== i) { V.page = i; emit('page', i); }
}

function onScroll() {
  if (!els.length) return;
  const mid = scroller.scrollTop + scroller.clientHeight * 0.4;
  let lo = 0, hi = els.length - 1;
  while (lo < hi) {
    const m = (lo + hi + 1) >> 1;
    if (els[m].wrap.offsetTop <= mid) lo = m; else hi = m - 1;
  }
  if (lo !== V.page) { V.page = lo; emit('page', lo); }
}

export function setInvert(on) { V.invert = on; scroller.classList.toggle('invert', on); }

function onWheel(e) {
  if (!e.ctrlKey) return;
  e.preventDefault();
  setZoom(V.zoom * Math.exp(-e.deltaY * 0.01), e.clientX, e.clientY);
}

// ------------------------------------------------------------------------------------------------
// tools
// ------------------------------------------------------------------------------------------------
export function setTool(tool) {
  V.tool = tool;
  cancelDown();
  closeEditor(false);
  if (tool !== 'select') { V.sel = null; }
  V.tsel = null;
  scroller.classList.toggle('lock', LOCK_TOOLS.has(tool));
  scroller.dataset.tool = tool;
  redrawAll();
  emit('tool', tool);
  emit('selection');
}

export function clearSelection() { V.sel = null; V.tsel = null; redrawAll(); emit('selection'); }
export function revalidate() {
  if (V.sel) {
    const list = S.edits[V.sel.page];
    if (!list || !list[V.sel.idx]) V.sel = null;
  }
  V.tsel = null;
  emit('selection');
}

export function selectEdit(page, idx) { V.sel = { page, idx }; V.tsel = null; redrawAll(); emit('selection'); }
export const selectedEdit = () => (V.sel ? (S.edits[V.sel.page] || [])[V.sel.idx] : null);

// ---- helpers ------------------------------------------------------------------------------------
const pageOf = (e) => { const w = e.target && e.target.closest ? e.target.closest('.page') : null; return w ? +w.dataset.i : -1; };
function toPt(e, i) {
  const r = els[i].wrap.getBoundingClientRect();
  return [(e.clientX - r.left) / V.zoom, (e.clientY - r.top) / V.zoom];
}
function clampPt(p, i) { return [clamp(p[0], 0, infos[i].w), clamp(p[1], 0, infos[i].h)]; }
const capture = (e) => { try { scroller.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ } };

function nearestWord(words, p) {
  let best = Infinity, bi = 0;
  words.forEach((w, k) => {
    const dx = Math.max(w.x0 - p[0], 0, p[0] - w.x1), dy = Math.max(w.y0 - p[1], 0, p[1] - w.y1);
    const d = dx * dx + dy * dy * 4;
    if (d < best) { best = d; bi = k; }
  });
  return bi;
}

function selRects(words, sel) {
  const a = Math.min(sel.a, sel.b), b = Math.max(sel.a, sel.b);
  const groups = new Map();
  for (let k = a; k <= b && k < words.length; k++) {
    const w = words[k];
    const g = groups.get(w.item);
    if (!g) groups.set(w.item, [w.x0, w.y0, w.x1, w.y1]);
    else { g[0] = Math.min(g[0], w.x0); g[1] = Math.min(g[1], w.y0); g[2] = Math.max(g[2], w.x1); g[3] = Math.max(g[3], w.y1); }
  }
  return [...groups.values()];
}

export function selectedText() {
  if (!V.tsel) return '';
  const words = textNow(V.tsel.page);
  if (!words) return '';
  const a = Math.min(V.tsel.a, V.tsel.b), b = Math.max(V.tsel.a, V.tsel.b);
  let out = '', last = null;
  for (let k = a; k <= b && k < words.length; k++) {
    out += (last === null ? '' : (words[k].item !== last ? '\n' : ' ')) + words[k].s;
    last = words[k].item;
  }
  return out;
}

export function applyMarkup(kind) {
  if (!V.tsel) { toast(t('Select some text first')); return; }
  const words = textNow(V.tsel.page);
  const rects = selRects(words, V.tsel);
  const page = V.tsel.page;
  V.tsel = null;
  if (rects.length) addEdit(page, { t: kind, rects, color: V.colors[kind] || V.colors.draw });
  redrawAll(); emit('selection');
}

// ---- pointer handling -----------------------------------------------------------------------------
function cancelDown() {
  if (down) { clearTimeout(down.timer); }
  down = null;
  if (V.draft || V.preview || V.erasing) { V.draft = null; V.preview = null; V.erasing = null; redrawAll(); }
}

function onDown(e) {
  if (e.pointerType === 'mouse' && e.button !== 0) return;
  if (pinch) return;
  if (e.target.closest && e.target.closest('.texted, .tbar')) return;
  const i = pageOf(e);
  down = { id: e.pointerId, x: e.clientX, y: e.clientY, i, moved: false, mode: null, time: performance.now() };
  if (i < 0) { if (V.tool === 'select') clearSelection(); return; }
  const p = toPt(e, i);
  down.p = p;
  const tool = V.tool;
  if (tool === 'select') {
    const s = V.sel;
    if (s && s.page === i) {
      const ed = (S.edits[i] || [])[s.idx];
      if (ed) {
        if (RECT_LIKE.has(ed.t)) {
          const n = norm(ed);
          if (Math.hypot(p[0] - n.x1, p[1] - n.y1) * V.zoom < 24) { down.mode = 'resize'; down.edit = ed; down.idx = s.idx; capture(e); return; }
        }
        const b = bboxOf(ed), tol = 6 / V.zoom;
        if (p[0] >= b.x0 - tol && p[0] <= b.x1 + tol && p[1] >= b.y0 - tol && p[1] <= b.y1 + tol) {
          down.mode = 'move'; down.edit = ed; down.idx = s.idx; capture(e); return;
        }
      }
    }
    const idx = hitTest(S.edits[i] || [], p[0], p[1], 10 / V.zoom);
    if (idx >= 0) {
      V.sel = { page: i, idx }; V.tsel = null;
      down.mode = 'move'; down.edit = S.edits[i][idx]; down.idx = idx;
      redrawAll(); emit('selection'); capture(e); return;
    }
    down.mode = 'lp';
    down.timer = setTimeout(async () => {
      if (!down || down.mode !== 'lp' || down.moved) return;
      const words = await textFor(i);
      if (!down || down.mode !== 'lp' || down.moved || !words.length) return;
      const k = nearestWord(words, p);
      V.sel = null; V.tsel = { page: i, a: k, b: k, anchor: k };
      down.mode = 'tsel';
      if (navigator.vibrate) navigator.vibrate(12);
      capture(e); redraw(i);
    }, 420);
    return;
  }
  if (tool === 'hl' || tool === 'ul' || tool === 'st') {
    capture(e);
    down.mode = 'tsel';
    textFor(i).then((words) => {
      if (!down || !words.length) return;
      const k = nearestWord(words, down.p);
      V.tsel = { page: i, a: k, b: k, anchor: k };
      redraw(i);
    });
    return;
  }
  const q = clampPt(p, i);
  if (tool === 'erase') {
    capture(e); down.mode = 'erase';
    V.erasing = { page: i, set: new Set() };
    eraseAt(i, p);
    return;
  }
  if (tool === 'ink') {
    capture(e); down.mode = 'draw';
    const P = V.pens[V.pen];
    down.lx = e.clientX; down.ly = e.clientY; down.lt = e.timeStamp; down.lf = 1;
    const first = P.vary ? [q[0], q[1], 1] : [q[0], q[1]];
    V.draft = { page: i, edit: { t: 'ink', pts: [first], color: colorFor('ink'), w: P.w, op: P.op, cap: P.cap, vary: P.vary, dash: P.vary ? 0 : V.dash, pen: V.pen } };
    redraw(i);
    return;
  }
  if (SHAPES.has(tool)) {
    capture(e); down.mode = 'shape';
    const ed = { t: tool, x0: q[0], y0: q[1], x1: q[0], y1: q[1], color: colorFor(tool), w: tool === 'redact' ? 0 : V.shape.w };
    if (tool !== 'redact') {
      ed.op = V.shape.op; ed.dash = V.dash;
      if ((tool === 'rect' || tool === 'ellipse') && V.fill) ed.fill = ed.color;
      if (tool === 'arrow') ed.head = V.head;
    }
    V.draft = { page: i, edit: ed };
  }
}

function eraseAt(i, p) {
  const list = S.edits[i] || [];
  const tol = 7 / V.zoom;
  let changed = false;
  list.forEach((e, k) => {
    if (!V.erasing.set.has(k) && hitTest([e], p[0], p[1], tol) === 0) { V.erasing.set.add(k); changed = true; }
  });
  if (changed) redraw(i);
}

function onMove(e) {
  if (!down || e.pointerId !== down.id) return;
  const dx = e.clientX - down.x, dy = e.clientY - down.y;
  if (!down.moved && Math.hypot(dx, dy) > 7) {
    down.moved = true;
    if (down.mode === 'lp') { clearTimeout(down.timer); down.mode = 'scroll'; }
  }
  if (!down.mode || down.mode === 'scroll' || down.mode === 'lp') return;
  const i = down.i;
  const p = toPt(e, i);
  switch (down.mode) {
    case 'move': {
      V.preview = { page: i, idx: down.idx, edit: translateEdit(down.edit, p[0] - down.p[0], p[1] - down.p[1]) };
      redraw(i); break;
    }
    case 'resize': {
      const n = norm(down.edit);
      const q = [Math.max(n.x0 + 12, p[0]), Math.max(n.y0 + 12, p[1])];
      let ed = { ...down.edit, x0: n.x0, y0: n.y0, x1: q[0], y1: q[1] };
      if (ed.t === 'text') ed = { ...ed, y1: Math.max(ed.y1, ed.y0 + layoutText(ed).height) };
      if (ed.t === 'img' && down.edit.keep) ed = { ...ed, y1: ed.y0 + (ed.x1 - ed.x0) * down.edit.keep };
      V.preview = { page: i, idx: down.idx, edit: ed };
      redraw(i); break;
    }
    case 'tsel': {
      const words = textNow(i);
      if (words && V.tsel) { V.tsel.b = nearestWord(words, p); redraw(i); }
      break;
    }
    case 'draw': {
      const q = clampPt(p, i), pts = V.draft.edit.pts, l = pts[pts.length - 1];
      if (Math.hypot(q[0] - l[0], q[1] - l[1]) * V.zoom >= 1.5) {
        if (V.draft.edit.vary) {
          const lo = V.draft.edit.vary === 2 ? 0.3 : 0.5, hi = V.draft.edit.vary === 2 ? 1.6 : 1.4;
          let f;
          if (e.pointerType === 'pen' && e.pressure > 0) f = 0.35 + e.pressure * 1.25;
          else {
            const dt = Math.max(1, e.timeStamp - down.lt), v = Math.hypot(e.clientX - down.lx, e.clientY - down.ly) / dt;
            f = 1.45 - v * 0.9;
          }
          f = clamp(down.lf * 0.6 + clamp(f, lo, hi) * 0.4, lo, hi);
          down.lf = f; down.lx = e.clientX; down.ly = e.clientY; down.lt = e.timeStamp;
          pts.push([q[0], q[1], f]);
        } else pts.push(q);
        redraw(i);
      }
      break;
    }
    case 'erase': eraseAt(i, p); break;
    case 'shape': {
      const q = clampPt(p, i);
      V.draft.edit.x1 = q[0]; V.draft.edit.y1 = q[1]; redraw(i); break;
    }
    default: break;
  }
}

function onUp(e) {
  if (!down || e.pointerId !== down.id) return;
  const d = down;
  clearTimeout(d.timer);
  down = null;
  const i = d.i;
  switch (d.mode) {
    case 'move': case 'resize': {
      if (V.preview && d.moved) { const pv = V.preview; V.preview = null; replaceEdit(pv.page, pv.idx, pv.edit); }
      else { V.preview = null; redraw(i); }
      emit('selection');
      return;
    }
    case 'tsel': {
      if (V.tool === 'select') { redraw(i); emit('selection'); }
      else if (V.tool === 'hl' || V.tool === 'ul' || V.tool === 'st') {
        if (d.moved && V.tsel) applyMarkup(V.tool); else { V.tsel = null; redrawAll(); }
      }
      return;
    }
    case 'draw': {
      const ed = V.draft && V.draft.edit; V.draft = null;
      if (ed) addEdit(i, ed);
      return;
    }
    case 'erase': {
      const er = V.erasing; V.erasing = null;
      if (er && er.set.size) commitEdits({ ...S.edits, [er.page]: (S.edits[er.page] || []).filter((_, k) => !er.set.has(k)) });
      else redrawAll();
      return;
    }
    case 'shape': {
      const ed = V.draft && V.draft.edit; V.draft = null;
      if (ed && Math.hypot(ed.x1 - ed.x0, ed.y1 - ed.y0) * V.zoom > 8) addEdit(i, ed); else redraw(i);
      return;
    }
    default: break;
  }
  if (!d.moved && i >= 0) onTap(e, d);
}

function onCancel(e) {
  if (down && e.pointerId === down.id) { clearTimeout(down.timer); if (['draw', 'shape', 'move', 'resize', 'erase'].includes(down.mode)) cancelDown(); else down = null; }
}

function onTap(e, d) {
  const i = d.i, p = d.p, tool = V.tool;
  const now = performance.now();
  if (tool === 'hand' || tool === 'select') {
    if (tool === 'select') { if (V.sel || V.tsel) { V.sel = null; V.tsel = null; redrawAll(); emit('selection'); } }
    if (lastTap && now - lastTap.t < 320 && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 30) {
      lastTap = null;
      const base = (() => { const z = V.zoom; computeFit(i); const f = V.zoom; V.zoom = z; return f; })();
      if (V.zoom > base * 1.15) fitWidth(); else setZoom(base * 2.2, e.clientX, e.clientY);
    } else lastTap = { t: now, x: e.clientX, y: e.clientY };
    return;
  }
  if (tool === 'text' || tool === 'note') {
    const pw = infos[i].w;
    const w = Math.max(120, Math.min(pw * 0.6, pw - p[0] - 6));
    openEditor(i, p[0], p[1], w, null);
  } else if (tool === 'edit') editText(i, p);
  else if (tool === 'img' || tool === 'sig') placeImage(i, p);
  else if (tool === 'stamp') placeStamp(i, p);
}

// ---- pinch zoom (touch) -----------------------------------------------------------------------------
const tdist = (a, b) => Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
function onTouchStart(e) {
  if (e.touches.length === 2 && els.length) {
    cancelDown();
    const a = e.touches[0], b = e.touches[1];
    const sr = scroller.getBoundingClientRect();
    const c = { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    pinch = { d0: tdist(a, b), c0: c, z0: V.zoom, sl: scroller.scrollLeft, st: scroller.scrollTop, s: 1, c1: c, ref: anchorRef(c.x, c.y) };
    pagesEl.style.transformOrigin = `${c.x - sr.left + pinch.sl}px ${c.y - sr.top + pinch.st}px`;
    e.preventDefault();
  }
}
function onTouchMove(e) {
  if (pinch) {
    if (e.touches.length < 2) return;
    e.preventDefault();
    const a = e.touches[0], b = e.touches[1];
    const c = { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 };
    pinch.s = clamp(tdist(a, b) / pinch.d0, MIN_Z / pinch.z0, MAX_Z / pinch.z0);
    pinch.c1 = c;
    pagesEl.style.transform = `scale(${pinch.s})`;
    scroller.scrollLeft = pinch.sl - (c.x - pinch.c0.x);
    scroller.scrollTop = pinch.st - (c.y - pinch.c0.y);
    return;
  }
  if (down && ['move', 'resize', 'tsel', 'draw', 'shape', 'erase'].includes(down.mode)) e.preventDefault();
}
function onTouchEnd(e) {
  if (pinch && e.touches.length < 2) {
    const p = pinch; pinch = null;
    pagesEl.style.transform = ''; pagesEl.style.transformOrigin = '';
    const z = clamp(p.z0 * p.s, MIN_Z, MAX_Z);
    V.fit = false; V.zoom = z;
    layout();
    restoreAnchor(p.ref, p.c1.x, p.c1.y);
    invalidateAll();
    emit('zoom', V.zoom);
  }
}

// ---- text editor (inline) ----------------------------------------------------------------------------------
function closeEditor(commit) {
  if (!editor) return;
  const ed = editor; editor = null;
  if (commit) {
    const text = ed.ta.value;
    if (text.trim()) {
      const size = ed.edit ? ed.edit.size : (ed.note ? 13 : V.size);
      const color = ed.edit ? ed.edit.color : colorFor(ed.note ? 'note' : 'text');
      const base = { t: 'text', x0: ed.x, y0: ed.y, x1: ed.x + ed.w, y1: ed.y + 20, text, size, color, font: ed.edit ? ed.edit.font : V.font, bold: ed.edit ? !!ed.edit.bold : V.bold };
      if (ed.note || (ed.edit && ed.edit.bg)) base.bg = '#fff4a3';
      base.y1 = base.y0 + layoutText(base).height;
      if (ed.idx != null) replaceEdit(ed.page, ed.idx, base);
      else {
        addEdit(ed.page, base);
        V.on.afterText && V.on.afterText(ed.page, (S.edits[ed.page] || []).length - 1);
      }
    }
  }
  ed.box.remove();
  redrawAll();
}

export function openEditor(page, x, y, w, existing, idx = null) {
  closeEditor(false);
  const wrap = els[page].wrap;
  const note = V.tool === 'note';
  const size = existing ? existing.size : (note ? 13 : V.size);
  const color = existing ? existing.color : colorFor(note ? 'note' : 'text');
  const ta = h('textarea', { class: 'texted', dir: 'auto', rows: 2, placeholder: t('Type here…') });
  ta.value = existing ? existing.text : '';
  const bg = (existing && existing.bg) || (note ? '#fff4a3' : 'rgba(255,255,255,.92)');
  Object.assign(ta.style, { fontSize: size * V.zoom + 'px', color, background: bg, width: w * V.zoom + 'px', lineHeight: '1.3',
    fontFamily: FONTS[existing ? existing.font : V.font] || FONTS.sans, fontWeight: (existing ? existing.bold : V.bold) ? '700' : '400' });
  const ok = h('button', { class: 'tb ok', type: 'button', 'aria-label': t('OK'), onPointerdown: (ev) => ev.preventDefault(), onClick: () => closeEditor(true) }, '✓');
  const no = h('button', { class: 'tb no', type: 'button', 'aria-label': t('Cancel'), onPointerdown: (ev) => ev.preventDefault(), onClick: () => closeEditor(false) }, '✕');
  const bar = h('div', { class: 'tbar' }, ok, no);
  const box = h('div', { class: 'texted-box' }, ta, bar);
  Object.assign(box.style, { left: x * V.zoom + 'px', top: y * V.zoom + 'px' });
  wrap.append(box);
  editor = { box, ta, page, x, y, w, edit: existing, idx, note };
  const grow = () => { ta.style.height = 'auto'; ta.style.height = ta.scrollHeight + 'px'; };
  ta.addEventListener('input', grow);
  setTimeout(() => { ta.focus(); grow(); box.scrollIntoView({ block: 'center', behavior: 'smooth' }); }, 50);
}

export function editSelectedText() {
  const e = selectedEdit();
  if (!e || e.t !== 'text') return;
  openEditor(V.sel.page, e.x0, e.y0, e.x1 - e.x0, e, V.sel.idx);
}

// ---- edit existing text / images -----------------------------------------------------------------------------
async function editText(i, p) {
  const items = await R.getItems(i);
  const tol = 3;
  const hit = items.find((it) => p[0] >= it.rect[0] - tol && p[0] <= it.rect[2] + tol && p[1] >= it.rect[1] - tol && p[1] <= it.rect[3] + tol);
  if (!hit) { toast(t('No text found here')); return; }
  const val = await askText({ title: t('Edit text'), label: t('Text:'), value: hit.s, multiline: true });
  if (val == null || val === hit.s) return;
  const r = hit.rect, pad = 1.5;
  const cover = { t: 'rect', x0: r[0] - pad, y0: r[1] - pad, x1: r[2] + pad, y1: r[3] + pad, color: '#ffffff', fill: '#ffffff', w: 0 };
  const items2 = [cover];
  if (val.trim()) {
    const size = Math.round(hit.size * 10) / 10;
    const wBox = Math.max(r[2] - r[0], 30) + 2 * PAD + 30;
    const rtl = hit.rtl;
    const te = { t: 'text', text: val, size, color: '#000000', x0: rtl ? r[2] + PAD - wBox : hit.bx - PAD, x1: rtl ? r[2] + PAD : hit.bx - PAD + wBox, y0: hit.by - size - PAD, y1: 0 };
    te.y1 = te.y0 + layoutText(te).height;
    items2.push(te);
  }
  addEdits(i, items2);
}

function placeStamp(i, p) {
  const sz = V.stampSize;
  const w = V.stamp === 'dot' ? sz * 0.8 : Math.max(2, sz * 0.13);
  const list = stampShapes(V.stamp, p[0], p[1], sz).map((pts) => ({ t: 'ink', pts, color: colorFor('stamp'), w, op: 1, raw: true }));
  addEdits(i, list);
}

function placeImage(i, p) {
  const d = V.imageData;
  if (!d) { emit('needImage'); return; }
  const pw = infos[i].w, ph = infos[i].h;
  let w = Math.min(pw * (V.tool === 'sig' ? 0.34 : 0.45), 260);
  let hh = w * d.h / d.w;
  if (hh > ph * 0.5) { hh = ph * 0.5; w = hh * d.w / d.h; }
  const x0 = clamp(p[0] - w / 2, 4, pw - w - 4), y0 = clamp(p[1] - hh / 2, 4, ph - hh - 4);
  addEdit(i, { t: 'img', x0, y0, x1: x0 + w, y1: y0 + hh, data: d.data, kind: d.kind, keep: d.h / d.w });
  V.on.afterImage && V.on.afterImage(i, (S.edits[i] || []).length - 1);
}

// ---- search overlay ---------------------------------------------------------------------------------------------------
export function setSearch(res) {
  V.search = { hits: res.hits, list: res.list, cur: res.list.length ? res.list[0] : null };
  redrawAll();
  if (V.search.cur) scrollToHit(V.search.cur);
}
export function stepSearch(d) {
  const s = V.search;
  if (!s.list.length) return 0;
  let k = s.list.findIndex((x) => s.cur && x.page === s.cur.page && x.k === s.cur.k);
  k = (k + d + s.list.length) % s.list.length;
  s.cur = s.list[k];
  redrawAll(); scrollToHit(s.cur);
  return k + 1;
}
function scrollToHit(c) {
  const rects = V.search.hits[c.page][c.k];
  const y = els[c.page].wrap.offsetTop + rects[0][1] * V.zoom;
  scroller.scrollTo({ top: y - scroller.clientHeight / 3, behavior: 'smooth' });
}
export function clearSearch() { V.search = { hits: {}, cur: null, list: [] }; redrawAll(); }

export const pageSize = (i) => infos[i];
export const pageCountView = () => els.length;
