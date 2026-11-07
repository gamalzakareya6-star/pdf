// Bakes pending edits into the PDF bytes with pdf-lib.
import { PDFDocument, StandardFonts, rgb, degrees, BlendMode, LineCapStyle } from '@cantoo/pdf-lib';
import { layoutText, drawTextBlock, norm, PAD, dashOf, arrowHeads } from './draw.js';

const LATIN = /^[\x20-\x7e\xa0-\xff\r\n\t]*$/;

export function hex(c) {
  const n = parseInt(String(c).replace('#', ''), 16);
  return rgb(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

// view space (points, origin top-left, after /Rotate)  ->  PDF user space
export function mapper(page) {
  const box = page.getCropBox();
  const R = (((page.getRotation().angle % 360) + 360) % 360);
  const pt = (vx, vy) => {
    switch (R) {
      case 0: return [box.x + vx, box.y + box.height - vy];
      case 90: return [box.x + vy, box.y + vx];
      case 180: return [box.x + box.width - vx, box.y + vy];
      default: return [box.x + box.width - vy, box.y + box.height - vx];
    }
  };
  return { R, box, pt };
}

function rectIn(M, x0, y0, x1, y1) {
  const a = M.pt(x0, y0), b = M.pt(x1, y1);
  return { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), width: Math.abs(a[0] - b[0]), height: Math.abs(a[1] - b[1]) };
}

async function textPng(e, scale = 3) {
  const w = e.x1 - e.x0, h = e.y1 - e.y0;
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.ceil(w * scale)); c.height = Math.max(1, Math.ceil(h * scale));
  const ctx = c.getContext('2d');
  ctx.scale(scale, scale);
  ctx.translate(-e.x0, -e.y0);
  drawTextBlock(ctx, e);
  const blob = await new Promise((r) => c.toBlob(r, 'image/png'));
  return new Uint8Array(await blob.arrayBuffer());
}

async function drawOne(doc, page, M, getFont, e, cache) {
  switch (e.t) {
    case 'hl':
      for (const r of e.rects) {
        page.drawRectangle({ ...rectIn(M, r[0], r[1], r[2], r[3]), color: hex(e.color), opacity: 1, blendMode: BlendMode.Multiply });
      }
      break;
    case 'ul': case 'st':
      for (const r of e.rects) {
        const y = e.t === 'ul' ? r[3] - 1.5 : (r[1] + r[3]) / 2;
        const a = M.pt(r[0], y), b = M.pt(r[2], y);
        page.drawLine({ start: { x: a[0], y: a[1] }, end: { x: b[0], y: b[1] }, thickness: 1.3, color: hex(e.color) });
      }
      break;
    case 'ink': {
      const p = e.pts.map((q) => [...M.pt(q[0], q[1]), q[2] ?? 1]);
      if (e.vary && p.length > 1) {
        for (let i = 1; i < p.length; i++) {
          page.drawLine({ start: { x: p[i - 1][0], y: p[i - 1][1] }, end: { x: p[i][0], y: p[i][1] }, thickness: e.w * (p[i - 1][2] + p[i][2]) / 2, color: hex(e.color), lineCap: LineCapStyle.Round });
        }
        break;
      }
      if (e.vary) { page.drawLine({ start: { x: p[0][0], y: p[0][1] }, end: { x: p[0][0] + 0.01, y: p[0][1] }, thickness: e.w * p[0][2], color: hex(e.color), lineCap: LineCapStyle.Round }); break; }
      // single smooth path (y is negated because drawSvgPath flips the y axis)
      let d = `M ${p[0][0].toFixed(2)} ${(-p[0][1]).toFixed(2)}`;
      if (p.length === 1) d += ` L ${(p[0][0] + 0.01).toFixed(2)} ${(-p[0][1]).toFixed(2)}`;
      else if (e.raw) for (let i = 1; i < p.length; i++) d += ` L ${p[i][0].toFixed(2)} ${(-p[i][1]).toFixed(2)}`;
      else {
        for (let i = 1; i < p.length - 1; i++) {
          d += ` Q ${p[i][0].toFixed(2)} ${(-p[i][1]).toFixed(2)} ${((p[i][0] + p[i + 1][0]) / 2).toFixed(2)} ${(-(p[i][1] + p[i + 1][1]) / 2).toFixed(2)}`;
        }
        d += ` L ${p[p.length - 1][0].toFixed(2)} ${(-p[p.length - 1][1]).toFixed(2)}`;
      }
      const op = e.op ?? 1;
      const o = { x: 0, y: 0, scale: 1, borderColor: hex(e.color), borderWidth: e.w, borderOpacity: op,
        borderLineCap: e.cap === 'square' ? LineCapStyle.Projecting : (e.cap === 'butt' ? LineCapStyle.Butt : LineCapStyle.Round) };
      const dash = dashOf(e); if (dash) o.borderDashArray = dash;
      if (op < 1 && e.w >= 8) o.blendMode = BlendMode.Multiply;
      page.drawSvgPath(d, o);
      break;
    }
    case 'rect': {
      const b = norm(e);
      const opt = rectIn(M, b.x0, b.y0, b.x1, b.y1);
      if (e.fill) opt.color = hex(e.fill);
      if (e.w > 0) { opt.borderColor = hex(e.color); opt.borderWidth = e.w; const d = dashOf(e); if (d) opt.borderDashArray = d; } else opt.borderWidth = 0;
      opt.opacity = e.op ?? 1; opt.borderOpacity = e.op ?? 1;
      page.drawRectangle(opt);
      break;
    }
    case 'ellipse': {
      const b = norm(e);
      const r = rectIn(M, b.x0, b.y0, b.x1, b.y1);
      const opt = { x: r.x + r.width / 2, y: r.y + r.height / 2, xScale: r.width / 2, yScale: r.height / 2 };
      if (e.fill) opt.color = hex(e.fill);
      if (e.w > 0) { opt.borderColor = hex(e.color); opt.borderWidth = e.w; const d = dashOf(e); if (d) opt.borderDashArray = d; } else opt.borderWidth = 0;
      opt.opacity = e.op ?? 1; opt.borderOpacity = e.op ?? 1;
      page.drawEllipse(opt);
      break;
    }
    case 'line': case 'arrow': {
      const a = M.pt(e.x0, e.y0), b = M.pt(e.x1, e.y1);
      const op = e.op ?? 1;
      const base = { thickness: e.w, color: hex(e.color), lineCap: LineCapStyle.Round, opacity: op };
      const d = dashOf(e);
      page.drawLine({ start: { x: a[0], y: a[1] }, end: { x: b[0], y: b[1] }, ...base, ...(d ? { dashArray: d } : {}) });
      for (const hd of arrowHeads(e)) {
        const T = M.pt(hd.tip[0], hd.tip[1]), A = M.pt(hd.a[0], hd.a[1]), B = M.pt(hd.b[0], hd.b[1]);
        if (hd.tri) {
          page.drawSvgPath(`M ${T[0].toFixed(2)} ${(-T[1]).toFixed(2)} L ${A[0].toFixed(2)} ${(-A[1]).toFixed(2)} L ${B[0].toFixed(2)} ${(-B[1]).toFixed(2)} Z`, { x: 0, y: 0, scale: 1, color: hex(e.color), opacity: op });
        } else {
          page.drawLine({ start: { x: T[0], y: T[1] }, end: { x: A[0], y: A[1] }, ...base });
          page.drawLine({ start: { x: T[0], y: T[1] }, end: { x: B[0], y: B[1] }, ...base });
        }
      }
      break;
    }
    case 'text': {
      if (LATIN.test(e.text)) {
        if (e.bg) page.drawRectangle({ ...rectIn(M, e.x0, e.y0, e.x1, e.y1), color: hex(e.bg), borderWidth: 0 });
        const { lines } = layoutText(e);
        const fnt = await getFont(e);
        lines.forEach((ln, i) => {
          if (!ln) return;
          const A = M.pt(e.x0 + PAD, e.y0 + PAD + e.size + i * e.size * 1.3);
          page.drawText(ln.replace(/\t/g, ' '), { x: A[0], y: A[1], size: e.size, font: fnt, color: hex(e.color), rotate: degrees(M.R) });
        });
      } else {
        // Arabic / other scripts: shaped by the browser, embedded as a transparent PNG
        const img = await doc.embedPng(await textPng(e));
        const A = M.pt(e.x0, e.y1);
        page.drawImage(img, { x: A[0], y: A[1], width: e.x1 - e.x0, height: e.y1 - e.y0, rotate: degrees(M.R) });
      }
      break;
    }
    case 'img': {
      const b = norm(e);
      let img = cache.get(e.data);
      if (!img) {
        img = e.kind === 'jpg' ? await doc.embedJpg(e.data) : await doc.embedPng(e.data);
        cache.set(e.data, img);
      }
      const A = M.pt(b.x0, b.y1);
      page.drawImage(img, { x: A[0], y: A[1], width: b.x1 - b.x0, height: b.y1 - b.y0, rotate: degrees(M.R) });
      break;
    }
    default: break;
  }
}

// edits: { [page]: Edit[] };  rasterize(bytes, pageIndex, rects) -> {data, w, h}  (only needed for redactions)
export async function bake(bytes, edits, { rasterize } = {}) {
  const pagesWith = Object.keys(edits).map(Number).filter((i) => (edits[i] || []).length);
  if (!pagesWith.length) return bytes;
  const doc = await PDFDocument.load(bytes, { updateMetadata: false });
  const fonts = new Map();
  const getFont = async (e) => {
    const fam = e.font === 'serif' ? 'Times' : (e.font === 'mono' ? 'Courier' : 'Helvetica');
    const key = e.bold ? (fam === 'Times' ? 'TimesRomanBold' : fam + 'Bold') : (fam === 'Times' ? 'TimesRoman' : fam);
    if (!fonts.has(key)) fonts.set(key, await doc.embedFont(StandardFonts[key]));
    return fonts.get(key);
  };
  const cache = new Map();
  const redactions = new Map();
  for (const i of pagesWith) {
    const page = doc.getPage(i);
    const M = mapper(page);
    for (const e of edits[i]) {
      if (e.t === 'redact') {
        if (!redactions.has(i)) redactions.set(i, []);
        redactions.get(i).push(norm(e));
        continue;
      }
      await drawOne(doc, page, M, getFont, e, cache);
    }
  }
  let out = new Uint8Array(await doc.save());
  if (redactions.size) {
    if (!rasterize) throw new Error('rasterize callback required for redactions');
    const d2 = await PDFDocument.load(out, { updateMetadata: false });
    for (const [i, rects] of redactions) {
      const r = await rasterize(out, i, rects);
      const img = await d2.embedJpg(r.data);
      d2.removePage(i);
      const np = d2.insertPage(i, [r.w, r.h]);
      np.drawImage(img, { x: 0, y: 0, width: r.w, height: r.h });
    }
    out = new Uint8Array(await d2.save());
  }
  return out;
}
