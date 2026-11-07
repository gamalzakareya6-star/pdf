// Page-level operations (pdf-lib). Every function takes PDF bytes and returns new bytes.
import { PDFDocument, degrees, PageSizes } from '@cantoo/pdf-lib';

const load = (bytes, opts = {}) => PDFDocument.load(bytes, { updateMetadata: false, ...opts });
const save = async (d) => new Uint8Array(await d.save());

export function parseRanges(spec, total) {
  spec = (spec || '').trim().toLowerCase();
  if (!spec || spec === 'all' || spec === '*') return Array.from({ length: total }, (_, i) => i);
  const out = [];
  for (const part of spec.replace(/\s+/g, '').replace(/[،؛;]/g, ',').split(',')) {
    if (!part) continue;
    let a, b;
    if (part.includes('-')) {
      const [s, e] = part.split('-');
      a = s ? parseInt(s, 10) : 1; b = e ? parseInt(e, 10) : total;
    } else a = b = parseInt(part, 10);
    if (!(a >= 1) || !(b <= total) || a > b) throw new Error('Invalid page range');
    for (let i = a; i <= b; i++) out.push(i - 1);
  }
  if (!out.length) throw new Error('Invalid page range');
  return out;
}

export async function blankPdf() {
  const d = await PDFDocument.create();
  d.addPage(PageSizes.A4);
  return save(d);
}

export async function pageCountOf(bytes, opts) { return (await load(bytes, opts)).getPageCount(); }

export async function rotatePages(bytes, idxs, delta) {
  const d = await load(bytes);
  for (const i of idxs) {
    const p = d.getPage(i);
    p.setRotation(degrees((((p.getRotation().angle + delta) % 360) + 360) % 360));
  }
  return save(d);
}

export async function deletePages(bytes, idxs) {
  const d = await load(bytes);
  if (new Set(idxs).size >= d.getPageCount()) throw new Error('Cannot delete all pages');
  [...new Set(idxs)].sort((a, b) => b - a).forEach((i) => d.removePage(i));
  return save(d);
}

export async function duplicatePages(bytes, idxs) {
  const d = await load(bytes);
  for (const i of [...new Set(idxs)].sort((a, b) => b - a)) {
    const [c] = await d.copyPages(d, [i]);
    d.insertPage(i + 1, c);
  }
  return save(d);
}

export async function insertBlank(bytes, after) {
  const d = await load(bytes);
  const { width, height } = d.getPage(Math.max(0, Math.min(after, d.getPageCount() - 1))).getSize();
  d.insertPage(after + 1, [width, height]);
  return save(d);
}

// move page `from` so that it ends up at index `to`
export async function movePage(bytes, from, to) {
  const d = await load(bytes);
  const n = d.getPageCount();
  if (from === to || from < 0 || to < 0 || from >= n || to >= n) return bytes;
  const [c] = await d.copyPages(d, [from]);
  if (to > from) { d.insertPage(to + 1, c); d.removePage(from); } else { d.insertPage(to, c); d.removePage(from + 1); }
  return save(d);
}

export async function extractPages(bytes, idxs) {
  const src = await load(bytes);
  const nd = await PDFDocument.create();
  const pages = await nd.copyPages(src, idxs);
  pages.forEach((p) => nd.addPage(p));
  return save(nd);
}

export async function mergePdfs(list) {
  const nd = await PDFDocument.create();
  for (const b of list) {
    const s = await load(b);
    const pages = await nd.copyPages(s, s.getPageIndices());
    pages.forEach((p) => nd.addPage(p));
  }
  return save(nd);
}

export async function insertPdf(base, other, after) {
  const d = await load(base);
  const s = await load(other);
  const pages = await d.copyPages(s, s.getPageIndices());
  pages.forEach((p, k) => d.insertPage(after + 1 + k, p));
  return save(d);
}

export async function getMeta(bytes) {
  const d = await load(bytes);
  return {
    title: d.getTitle() || '', author: d.getAuthor() || '', subject: d.getSubject() || '',
    keywords: d.getKeywords() || '', pages: d.getPageCount(),
  };
}

export async function setMeta(bytes, m) {
  const d = await load(bytes);
  d.setTitle(m.title || ''); d.setAuthor(m.author || ''); d.setSubject(m.subject || '');
  d.setKeywords((m.keywords || '').split(/[,،]/).map((s) => s.trim()).filter(Boolean));
  return save(d);
}

export async function encryptPdf(bytes, pw) {
  const d = await load(bytes);
  await d.encrypt({
    userPassword: pw, ownerPassword: pw,
    permissions: { printing: 'highResolution', modifying: true, copying: true, annotating: true, fillingForms: true, contentAccessibility: true, documentAssembly: true },
  });
  return save(d);
}

export async function decryptPdf(bytes, pw) {
  // Re-saving a decrypted document may re-encrypt it, so copy the pages into a fresh (plain) document.
  const src = await PDFDocument.load(bytes, { password: pw, updateMetadata: false });
  const nd = await PDFDocument.create();
  const pages = await nd.copyPages(src, src.getPageIndices());
  pages.forEach((p) => nd.addPage(p));
  try {
    nd.setTitle(src.getTitle() || ''); nd.setAuthor(src.getAuthor() || '');
    nd.setSubject(src.getSubject() || ''); nd.setKeywords((src.getKeywords() || '').split(/[,،]/).map((x) => x.trim()).filter(Boolean));
  } catch (e) { /* metadata is optional */ }
  return save(nd);
}
