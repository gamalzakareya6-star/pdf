// Drawing of edits (shared by the on-screen overlay and by the exporter) + geometry helpers.

export const FONT = '"Segoe UI","Noto Sans Arabic","Noto Naskh Arabic","Droid Arabic Naskh",Tahoma,Roboto,Arial,sans-serif';
export const FONTS = {
  sans: FONT,
  serif: '"Times New Roman","Noto Serif","Noto Naskh Arabic","Droid Serif",Georgia,serif',
  mono: '"Courier New","Noto Sans Mono","Droid Sans Mono",monospace',
};
export const fontCss = (e) => `${e.bold ? 'bold ' : ''}${e.size}px ${FONTS[e.font] || FONT}`;

// pen presets: w = width (pt), op = opacity, vary = variable width (1 fountain, 2 brush), cap = line cap
export const PENS = {
  ballpoint: { w: 2, op: 1 },
  fine: { w: 1, op: 1 },
  fountain: { w: 3.5, op: 1, vary: 1 },
  brush: { w: 9, op: 1, vary: 2 },
  pencil: { w: 2.4, op: 0.72 },
  marker: { w: 10, op: 0.5, cap: 'square' },
  highlighter: { w: 20, op: 0.35, cap: 'butt' },
};

export function dashOf(e) {
  const w = Math.max(e.w || 1, 1.2);
  if (e.dash === 1) return [w * 3.2, w * 2.2];
  if (e.dash === 2) return [0.01, w * 2.4];
  return null;
}

// arrow heads in view space: [{tip, a, b, tri}]
export function arrowHeads(e) {
  if (e.t !== 'arrow') return [];
  const head = e.head || 'v';
  const len = Math.max(9, (e.w || 2) * 4.5);
  const mk = (x0, y0, x1, y1) => {
    const ang = Math.atan2(y1 - y0, x1 - x0);
    return { tip: [x1, y1], a: [x1 - len * Math.cos(ang - 0.45), y1 - len * Math.sin(ang - 0.45)], b: [x1 - len * Math.cos(ang + 0.45), y1 - len * Math.sin(ang + 0.45)], tri: head === 'tri' };
  };
  const out = [mk(e.x0, e.y0, e.x1, e.y1)];
  if (head === 'both') out.push(mk(e.x1, e.y1, e.x0, e.y0));
  return out;
}

// vector stamps made of polylines (view space), centred at (cx, cy)
export function stampShapes(kind, cx, cy, s) {
  const P = (a) => a.map(([x, y]) => [cx + x * s, cy + y * s]);
  switch (kind) {
    case 'check': return [P([[-0.42, 0.02], [-0.12, 0.36], [0.46, -0.38]])];
    case 'cross': return [P([[-0.38, -0.38], [0.38, 0.38]]), P([[0.38, -0.38], [-0.38, 0.38]])];
    case 'star': {
      const pts = [];
      for (let i = 0; i <= 10; i++) { const r = i % 2 ? 0.21 : 0.5; const a = -Math.PI / 2 + i * Math.PI / 5; pts.push([r * Math.cos(a), r * Math.sin(a) + 0.03]); }
      return [P(pts)];
    }
    case 'heart': {
      const pts = [];
      for (let i = 0; i <= 48; i++) { const t = i / 48 * Math.PI * 2; pts.push([16 * Math.sin(t) ** 3 / 36, -(13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 36 + 0.02]); }
      return [P(pts)];
    }
    case 'circle': {
      const pts = [];
      for (let i = 0; i <= 36; i++) { const t = i / 36 * Math.PI * 2; pts.push([0.45 * Math.cos(t), 0.45 * Math.sin(t)]); }
      return [P(pts)];
    }
    default: return [P([[0, 0]])]; // dot
  }
}

export const LH = 1.3;   // line height factor
export const PAD = 3;    // inner padding of text boxes (pt)
export const RECT_LIKE = new Set(['rect', 'ellipse', 'redact', 'text', 'img']);

const RTL_RE = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
const LATIN_RE = /[A-Za-z]/;

export function isRTL(s) {
  for (const ch of s) {
    if (LATIN_RE.test(ch)) return false;
    if (RTL_RE.test(ch)) return true;
  }
  return false;
}

export function wrapLines(measure, text, maxW) {
  const out = [];
  for (const para of String(text).split(/\r?\n/)) {
    if (!para.trim()) { out.push(''); continue; }
    let line = '';
    for (const w of para.split(/\s+/).filter(Boolean)) {
      const test = line ? line + ' ' + w : w;
      if (line && measure(test) > maxW) { out.push(line); line = w; } else line = test;
    }
    out.push(line);
  }
  return out;
}

let mctx = null;
function measureCtx() {
  if (!mctx) mctx = document.createElement('canvas').getContext('2d');
  return mctx;
}

export function layoutText(e) {
  const ctx = measureCtx();
  ctx.font = fontCss(e);
  const maxW = Math.max(10, e.x1 - e.x0 - 2 * PAD);
  const lines = wrapLines((s) => ctx.measureText(s).width, e.text, maxW);
  return { lines, rtl: isRTL(e.text), height: lines.length * e.size * LH + 2 * PAD };
}

export function norm(e) {
  return { x0: Math.min(e.x0, e.x1), y0: Math.min(e.y0, e.y1), x1: Math.max(e.x0, e.x1), y1: Math.max(e.y0, e.y1) };
}

export function bboxOf(e) {
  switch (e.t) {
    case 'ink': {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [x, y] of e.pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
      const r = e.w / 2 + 1;
      return { x0: x0 - r, y0: y0 - r, x1: x1 + r, y1: y1 + r };
    }
    case 'hl': case 'ul': case 'st': {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const r of e.rects) { x0 = Math.min(x0, r[0]); y0 = Math.min(y0, r[1]); x1 = Math.max(x1, r[2]); y1 = Math.max(y1, r[3]); }
      return { x0, y0, x1, y1 };
    }
    case 'line': case 'arrow': {
      const b = norm(e); const r = (e.w || 2) / 2 + 2 + (e.t === 'arrow' ? Math.max(9, (e.w || 2) * 4.5) : 0);
      return { x0: b.x0 - r, y0: b.y0 - r, x1: b.x1 + r, y1: b.y1 + r };
    }
    default: return norm(e);
  }
}

function distToSegment(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const l2 = dx * dx + dy * dy;
  let t = l2 ? ((px - ax) * dx + (py - ay) * dy) / l2 : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

// topmost edit under (x, y); tol in points
export function hitTest(list, x, y, tol) {
  for (let i = list.length - 1; i >= 0; i--) {
    const e = list[i];
    if (e.t === 'ink') {
      for (let k = 1; k < e.pts.length; k++) {
        if (distToSegment(x, y, e.pts[k - 1][0], e.pts[k - 1][1], e.pts[k][0], e.pts[k][1]) <= tol + e.w / 2) return i;
      }
      if (e.pts.length === 1 && Math.hypot(x - e.pts[0][0], y - e.pts[0][1]) <= tol + e.w) return i;
    } else if (e.t === 'line' || e.t === 'arrow') {
      if (distToSegment(x, y, e.x0, e.y0, e.x1, e.y1) <= tol + (e.w || 2) / 2) return i;
    } else if ((e.t === 'rect' || e.t === 'ellipse') && !e.fill) {
      const b = norm(e);
      const inside = x >= b.x0 - tol && x <= b.x1 + tol && y >= b.y0 - tol && y <= b.y1 + tol;
      const inner = x > b.x0 + tol && x < b.x1 - tol && y > b.y0 + tol && y < b.y1 - tol;
      if (inside && !inner) return i;
    } else {
      const b = bboxOf(e);
      if (x >= b.x0 - tol && x <= b.x1 + tol && y >= b.y0 - tol && y <= b.y1 + tol) return i;
    }
  }
  return -1;
}

export function translateEdit(e, dx, dy) {
  switch (e.t) {
    case 'ink': return { ...e, pts: e.pts.map((q) => (q.length > 2 ? [q[0] + dx, q[1] + dy, q[2]] : [q[0] + dx, q[1] + dy])) };
    case 'hl': case 'ul': case 'st': return { ...e, rects: e.rects.map((r) => [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy]) };
    default: return { ...e, x0: e.x0 + dx, y0: e.y0 + dy, x1: e.x1 + dx, y1: e.y1 + dy };
  }
}

// ---- images ---------------------------------------------------------------
const images = new WeakMap();
let onImageLoad = () => {};
export const setImageLoadHandler = (fn) => { onImageLoad = fn; };

function imageFor(e) {
  let rec = images.get(e.data);
  if (!rec) {
    rec = { img: new Image(), ok: false };
    rec.img.onload = () => { rec.ok = true; onImageLoad(); };
    rec.img.src = URL.createObjectURL(new Blob([e.data], { type: e.kind === 'jpg' ? 'image/jpeg' : 'image/png' }));
    images.set(e.data, rec);
  }
  return rec.ok ? rec.img : null;
}

// ---- text -------------------------------------------------------------------
export function drawTextBlock(ctx, e) {
  const w = e.x1 - e.x0, h = e.y1 - e.y0;
  if (e.bg) { ctx.fillStyle = e.bg; ctx.fillRect(e.x0, e.y0, w, h); }
  const { lines, rtl } = layoutText(e);
  ctx.font = fontCss(e);
  ctx.fillStyle = e.color;
  ctx.textBaseline = 'alphabetic';
  ctx.direction = rtl ? 'rtl' : 'ltr';
  ctx.textAlign = rtl ? 'right' : 'left';
  const x = rtl ? e.x1 - PAD : e.x0 + PAD;
  lines.forEach((ln, i) => ctx.fillText(ln, x, e.y0 + PAD + e.size + i * e.size * LH));
}

// ---- shapes -------------------------------------------------------------------
function drawHeads(ctx, e) {
  const heads = arrowHeads(e);
  if (!heads.length) return;
  ctx.setLineDash([]);
  ctx.fillStyle = e.color;
  for (const h of heads) {
    ctx.beginPath();
    if (h.tri) { ctx.moveTo(h.tip[0], h.tip[1]); ctx.lineTo(h.a[0], h.a[1]); ctx.lineTo(h.b[0], h.b[1]); ctx.closePath(); ctx.fill(); }
    else { ctx.moveTo(h.a[0], h.a[1]); ctx.lineTo(h.tip[0], h.tip[1]); ctx.lineTo(h.b[0], h.b[1]); ctx.stroke(); }
  }
}

export function drawEdit(ctx, e) {
  ctx.save();
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  switch (e.t) {
    case 'ink': {
      const p = e.pts;
      ctx.strokeStyle = e.color; ctx.lineWidth = e.w; ctx.globalAlpha = e.op ?? 1;
      if (e.cap) ctx.lineCap = e.cap;
      if (e.vary) {
        ctx.globalAlpha = 1; ctx.lineCap = 'round';
        if (p.length === 1) { ctx.lineWidth = e.w * (p[0][2] ?? 1); ctx.beginPath(); ctx.moveTo(p[0][0], p[0][1]); ctx.lineTo(p[0][0] + 0.01, p[0][1]); ctx.stroke(); break; }
        for (let i = 1; i < p.length; i++) {
          ctx.lineWidth = e.w * ((p[i - 1][2] ?? 1) + (p[i][2] ?? 1)) / 2;
          ctx.beginPath(); ctx.moveTo(p[i - 1][0], p[i - 1][1]); ctx.lineTo(p[i][0], p[i][1]); ctx.stroke();
        }
        break;
      }
      const d = dashOf(e); if (d) ctx.setLineDash(d);
      ctx.beginPath();
      ctx.moveTo(p[0][0], p[0][1]);
      if (p.length === 1) ctx.lineTo(p[0][0] + 0.01, p[0][1]);
      else if (e.raw) for (let i = 1; i < p.length; i++) ctx.lineTo(p[i][0], p[i][1]);
      else {
        for (let i = 1; i < p.length - 1; i++) ctx.quadraticCurveTo(p[i][0], p[i][1], (p[i][0] + p[i + 1][0]) / 2, (p[i][1] + p[i + 1][1]) / 2);
        ctx.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
      }
      ctx.stroke();
      break;
    }
    case 'rect': case 'ellipse': {
      const b = norm(e);
      ctx.globalAlpha = e.op ?? 1;
      ctx.beginPath();
      if (e.t === 'rect') ctx.rect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
      else ctx.ellipse((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.x1 - b.x0) / 2, (b.y1 - b.y0) / 2, 0, 0, Math.PI * 2);
      if (e.fill) { ctx.fillStyle = e.fill; ctx.fill(); }
      if (e.w > 0) { ctx.strokeStyle = e.color; ctx.lineWidth = e.w; const d = dashOf(e); if (d) ctx.setLineDash(d); ctx.stroke(); }
      break;
    }
    case 'line': case 'arrow': {
      ctx.globalAlpha = e.op ?? 1;
      ctx.strokeStyle = e.color; ctx.lineWidth = e.w;
      const d = dashOf(e); if (d) ctx.setLineDash(d);
      ctx.beginPath(); ctx.moveTo(e.x0, e.y0); ctx.lineTo(e.x1, e.y1); ctx.stroke();
      drawHeads(ctx, e);
      break;
    }
    case 'hl':
      ctx.globalAlpha = 0.4; ctx.fillStyle = e.color;
      for (const r of e.rects) ctx.fillRect(r[0], r[1], r[2] - r[0], r[3] - r[1]);
      ctx.globalAlpha = 1;
      break;
    case 'ul': case 'st':
      ctx.strokeStyle = e.color; ctx.lineWidth = 1.3;
      for (const r of e.rects) {
        const y = e.t === 'ul' ? r[3] - 1.5 : (r[1] + r[3]) / 2;
        ctx.beginPath(); ctx.moveTo(r[0], y); ctx.lineTo(r[2], y); ctx.stroke();
      }
      break;
    case 'text': drawTextBlock(ctx, e); break;
    case 'img': {
      const img = imageFor(e);
      const b = norm(e);
      if (img) ctx.drawImage(img, b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
      else { ctx.fillStyle = 'rgba(128,128,128,.25)'; ctx.fillRect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0); }
      break;
    }
    case 'redact': {
      const b = norm(e);
      ctx.fillStyle = 'rgba(0,0,0,.62)'; ctx.fillRect(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0);
      break;
    }
    default: break;
  }
  ctx.restore();
}
