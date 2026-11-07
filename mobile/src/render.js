// pdf.js wrapper: rendering, text extraction (words / items), search, thumbnails.
import * as ns from 'pdfjs-dist/build/pdf.js';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.js?url';

const pdfjs = ns.default || ns;
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

let doc = null;
export let lastBytes = null;
export let version = 0;
const pages = new Map();
const infos = new Map();
const textCache = new Map();

export async function openDoc(bytes, password) {
  const task = pdfjs.getDocument({ data: new Uint8Array(bytes), password: password || undefined, isEvalSupported: false });
  const nd = await task.promise;
  if (doc) { try { doc.destroy(); } catch (e) { /* ignore */ } }
  doc = nd; lastBytes = bytes; version++;
  pages.clear(); infos.clear(); textCache.clear();
  return doc.numPages;
}

export const pageCount = () => (doc ? doc.numPages : 0);

export async function getPage(i) {
  if (!pages.has(i)) pages.set(i, await doc.getPage(i + 1));
  return pages.get(i);
}

export async function info(i) {
  if (!infos.has(i)) {
    const vp = (await getPage(i)).getViewport({ scale: 1 });
    infos.set(i, { w: vp.width, h: vp.height });
  }
  return infos.get(i);
}

// Returns a pdf.js render task (has .promise and .cancel()).
export async function renderTo(i, canvas, scale) {
  const page = await getPage(i);
  const vp = page.getViewport({ scale });
  canvas.width = Math.max(1, Math.floor(vp.width));
  canvas.height = Math.max(1, Math.floor(vp.height));
  return page.render({ canvasContext: canvas.getContext('2d'), viewport: vp });
}

export async function thumb(i, canvas, targetPx) {
  const inf = await info(i);
  const task = await renderTo(i, canvas, targetPx / inf.w);
  await task.promise;
}

// ---- text ---------------------------------------------------------------------
const TASHKEEL = /[ً-ٰٟـ]/g;
export function normWord(s) {
  return s.replace(TASHKEEL, '').replace(/[آأإ]/g, 'ا').replace(/ى/g, 'ي').toLowerCase();
}

function boxOf(P0, u, up, s0, s1) {
  const pts = [];
  for (const s of [s0, s1]) for (const k of [-0.22, 0.98]) pts.push([P0[0] + u[0] * s + up[0] * k, P0[1] + u[1] * s + up[1] * k]);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export async function getText(i) {
  if (textCache.has(i)) return textCache.get(i);
  const page = await getPage(i);
  const vp = page.getViewport({ scale: 1 });
  const tc = await page.getTextContent();
  const words = [], items = [];
  tc.items.forEach((it, idx) => {
    if (!it.str || !it.str.trim()) return;
    const tx = pdfjs.Util.transform(vp.transform, it.transform);
    const len = Math.hypot(tx[0], tx[1]) || 1;
    const u = [tx[0] / len, tx[1] / len];
    const up = [tx[2], tx[3]];
    const fh = Math.hypot(tx[2], tx[3]) || it.height || 10;
    const P0 = [tx[4], tx[5]];
    const w = it.width || 0;
    const rtl = it.dir === 'rtl';
    items.push({ s: it.str, rect: boxOf(P0, u, up, 0, w), size: fh, bx: P0[0], by: P0[1], rtl, idx, u });
    const L = it.str.length;
    const re = /\S+/g;
    let m;
    while ((m = re.exec(it.str))) {
      let f0 = m.index / L, f1 = (m.index + m[0].length) / L;
      if (rtl) { const a = 1 - f1, b = 1 - f0; f0 = a; f1 = b; }
      const r = boxOf(P0, u, up, w * f0, w * f1);
      words.push({ s: m[0], x0: r[0], y0: r[1], x1: r[2], y1: r[3], item: idx });
    }
  });
  const res = { words, items };
  textCache.set(i, res);
  return res;
}
export const getWords = async (i) => (await getText(i)).words;
export const getItems = async (i) => (await getText(i)).items;

// ---- search ------------------------------------------------------------------------
export async function search(query) {
  const q = normWord(query.trim());
  const hits = {};
  const list = [];
  if (!q) return { hits, list };
  for (let i = 0; i < pageCount(); i++) {
    const words = await getWords(i);
    const starts = [];
    let text = '';
    words.forEach((w, k) => { starts.push(text.length); text += normWord(w.s) + ' '; });
    let from = 0, pos;
    while ((pos = text.indexOf(q, from)) >= 0) {
      const end = pos + q.length;
      const rects = [];
      for (let k = 0; k < words.length; k++) {
        const ws = starts[k], we = ws + normWord(words[k].s).length;
        if (we > pos && ws < end) rects.push([words[k].x0, words[k].y0, words[k].x1, words[k].y1]);
      }
      if (rects.length) { (hits[i] = hits[i] || []).push(rects); list.push({ page: i, k: hits[i].length - 1 }); }
      from = pos + Math.max(1, q.length);
    }
  }
  return { hits, list };
}

// ---- redaction: render the page with black boxes burned in (text underneath is gone) ---------
export async function rasterizeRedact(bytes, i, rects, scale = 2.6) {
  const task = pdfjs.getDocument({ data: new Uint8Array(bytes), isEvalSupported: false });
  const d = await task.promise;
  try {
    const page = await d.getPage(i + 1);
    const vp = page.getViewport({ scale });
    const c = document.createElement('canvas');
    c.width = Math.floor(vp.width); c.height = Math.floor(vp.height);
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height);
    await page.render({ canvasContext: ctx, viewport: vp }).promise;
    ctx.fillStyle = '#000';
    for (const r of rects) ctx.fillRect(r.x0 * scale, r.y0 * scale, (r.x1 - r.x0) * scale, (r.y1 - r.y0) * scale);
    const blob = await new Promise((res) => c.toBlob(res, 'image/jpeg', 0.88));
    const base = page.getViewport({ scale: 1 });
    return { data: new Uint8Array(await blob.arrayBuffer()), w: base.width, h: base.height };
  } finally {
    try { d.destroy(); } catch (e) { /* ignore */ }
  }
}

export async function renderPng(i, scale) {
  const c = document.createElement('canvas');
  const task = await renderTo(i, c, scale);
  await task.promise;
  const blob = await new Promise((res) => c.toBlob(res, 'image/png'));
  return new Uint8Array(await blob.arrayBuffer());
}
