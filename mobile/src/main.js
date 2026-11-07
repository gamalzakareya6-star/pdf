// App shell: screens, chrome (top bar / tools / option bars), menus, sheets, import/export.
import './style.css';
import { Capacitor } from '@capacitor/core';
import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import { App as CapApp } from '@capacitor/app';
import { t, setLang, getLang } from './i18n.js';
import { icon } from './icons.js';
import { h, $, iconBtn, toast, withBusy, openSheet, askText, askConfirm, actionSheet, goBack, backStack } from './ui.js';
import {
  S, subscribe, loadNew, commitBytes, undo, redo, canUndo, canRedo, hasEdits, markSaved, setPassword, removeEdit, replaceEdit,
} from './state.js';
import * as R from './render.js';
import { bake } from './bake.js';
import * as ops from './ops.js';
import {
  V, COLORS, colorFor, setColor, initView, rebuild, setTool, redrawAll, revalidate, zoomBy, fitWidth, goTo,
  setInvert, selectEdit, selectedEdit, editSelectedText, applyMarkup, selectedText, setSearch, stepSearch, clearSearch, clearSelection,
} from './view.js';

const app = $('#app');
const scroller = $('#scroller');
const native = Capacitor.isNativePlatform();
const store = {
  get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } },
};

// ------------------------------------------------------------------------------------------
// helpers
// ------------------------------------------------------------------------------------------
const baseName = () => S.name.replace(/\.pdf$/i, '');
const errText = (e) => t((e && e.message) || String(e));
async function safe(fn) {
  try { return await fn(); } catch (e) { console.error(e); toast(errText(e), 4200); return undefined; }
}
const readBytes = async (f) => new Uint8Array(await f.arrayBuffer());

function pickFiles(accept, multiple = false) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'file', accept, multiple });
    input.style.display = 'none';
    document.body.append(input);
    let done = false;
    const fin = (v) => { if (!done) { done = true; input.remove(); resolve(v); } };
    input.addEventListener('change', () => fin([...input.files]));
    input.addEventListener('cancel', () => fin([]));
    input.click();
  });
}

function toBase64(bytes) {
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}
const fromDataUrl = (u) => Uint8Array.from(atob(u.split(',')[1]), (c) => c.charCodeAt(0));

async function deliver(bytes, fname, mime) {
  if (native) {
    const r = await Filesystem.writeFile({ path: fname, data: toBase64(bytes), directory: Directory.Cache });
    await Share.share({ title: fname, url: r.uri, dialogTitle: t('Save or share') });
  } else {
    const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    const a = h('a', { href: url, download: fname });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 8000);
  }
}

async function copyText(s) {
  try { await navigator.clipboard.writeText(s); } catch (e) {
    const ta = h('textarea'); ta.value = s; document.body.append(ta); ta.select();
    try { document.execCommand('copy'); } catch (e2) { /* ignore */ }
    ta.remove();
  }
  toast(t('Copied'));
}

// ------------------------------------------------------------------------------------------
// document lifecycle
// ------------------------------------------------------------------------------------------
let pending = Promise.resolve();

subscribe((kind) => {
  if (kind === 'load' || kind === 'structure') {
    pending = (async () => {
      try {
        if (R.lastBytes !== S.bytes) await R.openDoc(S.bytes);
        if (kind === 'load') V.fit = true;
        app.dataset.screen = 'viewer';
        await rebuild(kind === 'structure');
      } catch (e) { console.error(e); toast(errText(e), 4200); }
      refresh();
    })();
  } else if (kind === 'edits') {
    revalidate(); redrawAll();
  }
  refresh();
});

async function openBytes(bytes, name) {
  await withBusy(async () => {
    let password = null, pc;
    for (;;) {
      try { pc = await R.openDoc(bytes, password); break; } catch (e) {
        if (e && e.name === 'PasswordException') {
          const pw = await askText({
            title: t('Password required'),
            label: password ? t('Wrong password, try again:') : t('This file is protected. Enter the password:'),
            password: true, ok: t('Open'),
          });
          if (pw == null) return;
          password = pw;
        } else throw e;
      }
    }
    let data = bytes;
    if (password) { data = await ops.decryptPdf(bytes, password); pc = await R.openDoc(data); }
    setTool('hand');
    loadNew(data, name, password, pc);
  }, t('Opening…'));
  await pending;
}

async function openFromPicker() {
  const [f] = await pickFiles('application/pdf,.pdf');
  if (f) await safe(async () => openBytes(await readBytes(f), f.name));
}

async function newBlank() {
  await safe(async () => openBytes(await ops.blankPdf(), t('New document') + '.pdf'));
}

async function mergeFlow() {
  const files = await pickFiles('application/pdf,.pdf', true);
  if (!files.length) return;
  if (files.length < 2) { toast(t('Pick at least two PDF files')); return; }
  await safe(async () => {
    const out = await withBusy(async () => ops.mergePdfs(await Promise.all(files.map(readBytes))), t('Merging…'));
    await openBytes(out, 'merged.pdf');
  });
}

async function closeDoc() {
  if (S.dirty || hasEdits()) {
    const r = await askConfirm({ title: t('Close document?'), text: t('You have changes that were not saved.'), ok: t('Discard'), danger: true, third: t('Save') });
    if (!r) return;
    if (r === 'third') { const ok = await exportPdf(); if (!ok) return; }
  }
  setTool('hand'); clearSearch(); $('#searchbar').classList.remove('show');
  Object.assign(S, { bytes: null, edits: {}, pageCount: 0, undo: [], redo: [], dirty: false, password: null });
  await rebuild(false);
  app.dataset.screen = 'start';
  refresh();
}

// bake pending edits -> bytes
async function flush() {
  if (!hasEdits()) return S.bytes;
  return bake(S.bytes, S.edits, { rasterize: R.rasterizeRedact });
}

async function structural(fn, label) {
  await withBusy(async () => {
    const out = await fn(await flush());
    commitBytes(out, await ops.pageCountOf(out), {});
    await pending;
  }, label || t('Working…'));
}

async function exportPdf() {
  return safe(async () => {
    const bytes = await withBusy(async () => {
      let b = await flush();
      if (S.password) b = await ops.encryptPdf(b, S.password);
      return b;
    }, t('Preparing…'));
    await deliver(bytes, baseName() + (hasEdits() || S.dirty ? '-edited' : '') + '.pdf', 'application/pdf');
    markSaved();
    if (!native) toast(t('Saved'));
    return true;
  });
}

// ------------------------------------------------------------------------------------------
// images & signature
// ------------------------------------------------------------------------------------------
async function prepImage(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error('Cannot read image')); i.src = url; });
    const sc = Math.min(1, 1800 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = h('canvas');
    c.width = Math.max(1, Math.round(img.naturalWidth * sc)); c.height = Math.max(1, Math.round(img.naturalHeight * sc));
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const jpg = /jpe?g/i.test(file.type);
    const blob = await new Promise((r) => c.toBlob(r, jpg ? 'image/jpeg' : 'image/png', 0.9));
    return { data: new Uint8Array(await blob.arrayBuffer()), kind: jpg ? 'jpg' : 'png', w: c.width, h: c.height };
  } finally { URL.revokeObjectURL(url); }
}

async function chooseImage() {
  const [f] = await pickFiles('image/png,image/jpeg,image/*');
  if (!f) return false;
  const d = await safe(() => prepImage(f));
  if (!d) return false;
  V.imageData = d;
  return true;
}

function dataUrlToImageData(u) {
  return new Promise((ok) => {
    const i = new Image();
    i.onload = () => ok({ data: fromDataUrl(u), kind: 'png', w: i.naturalWidth, h: i.naturalHeight });
    i.onerror = () => ok(null);
    i.src = u;
  });
}

function signaturePad() {
  return new Promise((resolve) => {
    const cv = h('canvas', { class: 'sigpad' });
    const saved = store.get('sig');
    let drew = false, drawing = false, last = null, minX = 1e9, minY = 1e9, maxX = -1, maxY = -1;
    let result = false;
    const W = 640, H = 280;
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d');
    ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.lineWidth = 5; ctx.strokeStyle = '#111';
    const pos = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
    cv.addEventListener('pointerdown', (e) => { drawing = true; drew = true; last = pos(e); cv.setPointerCapture(e.pointerId); stroke(last, last); });
    cv.addEventListener('pointermove', (e) => { if (!drawing) return; const p = pos(e); stroke(last, p); last = p; });
    const end = () => { drawing = false; };
    cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
    function stroke(a, b) {
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0] + 0.01, b[1]); ctx.stroke();
      minX = Math.min(minX, a[0], b[0]); minY = Math.min(minY, a[1], b[1]); maxX = Math.max(maxX, a[0], b[0]); maxY = Math.max(maxY, a[1], b[1]);
    }
    const sheet = openSheet({
      title: t('Draw your signature'),
      body: h('div', { class: 'sigwrap' }, cv, h('div', { class: 'sighint' }, t('Sign inside the box'))),
      footer: h('div', { class: 'sheet-actions' },
        h('button', { class: 'btn', type: 'button', onClick: () => { ctx.clearRect(0, 0, W, H); drew = false; minX = minY = 1e9; maxX = maxY = -1; } }, t('Clear')),
        saved ? h('button', { class: 'btn', type: 'button', onClick: async () => { const d = await dataUrlToImageData(saved); if (d) { V.imageData = d; result = true; sheet.close(); } } }, t('Use saved')) : null,
        h('button', { class: 'btn primary', type: 'button', onClick: async () => {
          if (!drew || maxX < 0) { toast(t('Draw your signature first')); return; }
          const pad = 8;
          const x = Math.max(0, minX - pad), y = Math.max(0, minY - pad);
          const w = Math.min(W, maxX + pad) - x, hh = Math.min(H, maxY + pad) - y;
          const out = h('canvas'); out.width = Math.max(1, Math.round(w)); out.height = Math.max(1, Math.round(hh));
          out.getContext('2d').drawImage(cv, x, y, w, hh, 0, 0, out.width, out.height);
          const url = out.toDataURL('image/png');
          store.set('sig', url);
          V.imageData = { data: fromDataUrl(url), kind: 'png', w: out.width, h: out.height };
          result = true; sheet.close();
        } }, t('Use signature'))),
      onClose: () => resolve(result),
    });
  });
}

function pickTool(id) {
  if (id === 'img') { chooseImage().then((ok) => { if (ok) setTool('img'); }); return; }
  if (id === 'sig') { signaturePad().then((ok) => { if (ok) setTool('sig'); }); return; }
  setTool(id);
}

// ------------------------------------------------------------------------------------------
// chrome
// ------------------------------------------------------------------------------------------
const hasDoc = () => !!S.bytes;

function buildTop() {
  const top = $('#topbar');
  top.textContent = '';
  top.append(
    iconBtn('close', t('Close'), closeDoc),
    h('div', { class: 'title', id: 'doctitle', dir: 'auto' }, S.name),
    iconBtn('undo', t('Undo'), () => { undo(); }, 'u-undo'),
    iconBtn('redo', t('Redo'), () => { redo(); }, 'u-redo'),
    iconBtn('search', t('Search'), toggleSearch),
    iconBtn('pages', t('Pages'), openPages),
    iconBtn('more', t('More'), openMenu));
}

const TOOL_LIST = () => [
  ['hand', 'hand', t('Pan')], ['select', 'select', t('Select')], ['edit', 'edittext', t('Edit text')],
  ['hl', 'highlight', t('Highlight')], ['ul', 'underline', t('Underline')], ['st', 'strike', t('Strikeout')],
  ['ink', 'draw', t('Draw')], ['text', 'text', t('Text')], ['note', 'note', t('Note')],
  ['rect', 'rect', t('Rectangle')], ['ellipse', 'ellipse', t('Ellipse')], ['line', 'line', t('Line')], ['arrow', 'arrow', t('Arrow')],
  ['img', 'image', t('Image')], ['sig', 'signature', t('Signature')], ['redact', 'redact', t('Redact')],
];

function buildTools() {
  const bar = $('#toolbar');
  bar.textContent = '';
  for (const [id, ic, label] of TOOL_LIST()) {
    bar.append(h('button', { class: 'tool', type: 'button', 'data-tool': id, onClick: () => pickTool(id) },
      h('span', { class: 'tool-ic', html: icon(ic) }), h('span', { class: 'tool-l' }, label)));
  }
  markTool();
}

function markTool() {
  document.querySelectorAll('#toolbar .tool').forEach((b) => {
    const on = b.dataset.tool === V.tool;
    b.classList.toggle('on', on);
    if (on) b.scrollIntoView({ inline: 'center', block: 'nearest' });
  });
}

const COLOR_TOOLS = new Set(['hl', 'ul', 'st', 'ink', 'rect', 'ellipse', 'line', 'arrow', 'text', 'note']);
const WIDTH_TOOLS = new Set(['ink', 'rect', 'ellipse', 'line', 'arrow']);

function swatches(current, onPick) {
  const wrap = h('div', { class: 'swatches' });
  for (const c of COLORS) {
    wrap.append(h('button', { class: 'sw' + (c.toLowerCase() === String(current).toLowerCase() ? ' on' : ''), type: 'button', style: `--c:${c}`, 'aria-label': c, onClick: () => onPick(c) }));
  }
  return wrap;
}

function slider(label, min, max, value, onInput) {
  const out = h('span', { class: 'sl-v' }, String(value));
  const inp = h('input', { type: 'range', min, max, value, step: 1 });
  inp.addEventListener('input', () => { out.textContent = inp.value; onInput(+inp.value); });
  return h('label', { class: 'slider' }, h('span', { class: 'sl-l' }, label), inp, out);
}

const actBtn = (ic, label, fn, cls = '') => h('button', { class: 'chip ' + cls, type: 'button', onClick: fn }, h('span', { html: icon(ic) }), h('span', {}, label));

function buildOpt() {
  const bar = $('#optbar');
  bar.textContent = '';
  const tool = V.tool;
  let show = false;
  if (tool === 'select') {
    const e = selectedEdit();
    if (e) {
      show = true;
      if (e.t !== 'img' && e.t !== 'redact' && e.color) bar.append(swatches(e.color, (c) => replaceEdit(V.sel.page, V.sel.idx, { ...e, color: c })));
      if (e.t === 'text') bar.append(actBtn('edittext', t('Edit'), editSelectedText));
      bar.append(actBtn('trash', t('Delete'), () => { const s = V.sel; clearSelection(); removeEdit(s.page, s.idx); }, 'danger'));
    } else if (V.tsel) {
      show = true;
      bar.append(actBtn('copy', t('Copy'), async () => { await copyText(selectedText()); clearSelection(); }),
        actBtn('highlight', t('Highlight'), () => applyMarkup('hl')),
        actBtn('underline', t('Underline'), () => applyMarkup('ul')),
        actBtn('strike', t('Strikeout'), () => applyMarkup('st')));
    } else { show = true; bar.append(h('div', { class: 'hint' }, t('Tap an item to select it · long-press text to select'))); }
  } else if (COLOR_TOOLS.has(tool)) {
    show = true;
    bar.append(swatches(colorFor(tool), (c) => { setColor(c, tool); buildOpt(); }));
    if (WIDTH_TOOLS.has(tool)) bar.append(slider(t('Width'), 1, 14, V.width, (v) => { V.width = v; }));
    if (tool === 'text') bar.append(slider(t('Size'), 8, 56, V.size, (v) => { V.size = v; }));
  } else {
    const hints = {
      hand: t('Drag to scroll · pinch to zoom · double-tap to fit'),
      edit: t('Tap on existing text to change it'),
      redact: t('Drag over what you want to hide permanently'),
      img: t('Tap on the page where the image goes'),
      sig: t('Tap on the page where the signature goes'),
    };
    if (hints[tool]) { show = true; bar.append(h('div', { class: 'hint' }, hints[tool])); }
  }
  bar.classList.toggle('show', show && hasDoc());
}

function refresh() {
  const tt = $('#doctitle'); if (tt) tt.textContent = S.name + (S.dirty || hasEdits() ? ' •' : '');
  const u = $('.u-undo'), r = $('.u-redo');
  if (u) u.disabled = !canUndo();
  if (r) r.disabled = !canRedo();
  markTool();
  buildOpt();
  updatePill();
}

function updatePill() {
  const p = $('#pill');
  if (!p) return;
  p.textContent = hasDoc() ? `${V.page + 1} / ${S.pageCount}` : '';
}

V.on.page = updatePill;
V.on.tool = () => { markTool(); buildOpt(); };
V.on.selection = () => buildOpt();
V.on.needImage = () => pickTool(V.tool);
V.on.afterText = (p, i) => { setTool('select'); selectEdit(p, i); };
V.on.afterImage = (p, i) => { setTool('select'); selectEdit(p, i); };

// ---- search --------------------------------------------------------------------------------------
let searchTimer = 0, searchSeq = 0;
function buildSearch() {
  const bar = $('#searchbar');
  bar.textContent = '';
  const inp = h('input', { id: 'q', type: 'search', dir: 'auto', placeholder: t('Search in document'), enterkeyhint: 'search' });
  const cnt = h('span', { id: 'qcount', class: 'qcount' });
  const run = async () => {
    const seq = ++searchSeq;
    const q = inp.value.trim();
    if (!q) { clearSearch(); cnt.textContent = ''; return; }
    const res = await R.search(q);
    if (seq !== searchSeq) return;
    setSearch(res);
    cnt.textContent = res.list.length ? `1/${res.list.length}` : t('No results');
  };
  inp.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(run, 280); });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); const k = stepSearch(e.shiftKey ? -1 : 1); if (k) cnt.textContent = `${k}/${V.search.list.length}`; } });
  const step = (d) => { const k = stepSearch(d); if (k) cnt.textContent = `${k}/${V.search.list.length}`; };
  bar.append(inp, cnt, iconBtn('prev', t('Previous'), () => step(-1)), iconBtn('next', t('Next'), () => step(1)), iconBtn('close', t('Close'), toggleSearch));
}
function toggleSearch() {
  const bar = $('#searchbar');
  const on = !bar.classList.contains('show');
  bar.classList.toggle('show', on);
  if (on) { const q = $('#q'); q.focus(); q.select(); } else { clearSearch(); searchSeq++; }
}

// ------------------------------------------------------------------------------------------
// pages sheet (thumbnails + page operations)
// ------------------------------------------------------------------------------------------
function openPages() {
  if (!hasDoc()) return;
  let sel = new Set([V.page]);
  const grid = h('div', { class: 'thumbs' });
  const bar = h('div', { class: 'pagebar' });
  let io = null;

  const idxs = () => [...sel].sort((a, b) => a - b);
  const act = async (fn, label, after) => {
    await safe(async () => { await structural(fn, label); if (after) sel = after(); draw(); });
  };

  function drawBar() {
    bar.textContent = '';
    const one = sel.size === 1, any = sel.size > 0;
    const b = (ic, label, fn, dis, cls = '') => h('button', { class: 'pbtn ' + cls, type: 'button', disabled: dis, onClick: fn },
      h('span', { html: icon(ic) }), h('span', {}, label));
    bar.append(
      b('rotate_ccw', t('Rotate left'), () => act((x) => ops.rotatePages(x, idxs(), -90), t('Rotating…')), !any),
      b('rotate_cw', t('Rotate right'), () => act((x) => ops.rotatePages(x, idxs(), 90), t('Rotating…')), !any),
      b('arrow_left', t('Move earlier'), () => { const i = idxs()[0]; act((x) => ops.movePage(x, i, i - 1), t('Moving…'), () => new Set([i - 1])); }, !(one && idxs()[0] > 0)),
      b('arrow_right', t('Move later'), () => { const i = idxs()[0]; act((x) => ops.movePage(x, i, i + 1), t('Moving…'), () => new Set([i + 1])); }, !(one && idxs()[0] < S.pageCount - 1)),
      b('copy', t('Duplicate'), () => act((x) => ops.duplicatePages(x, idxs()), t('Duplicating…'), () => new Set()), !any),
      b('file_plus', t('Blank page after'), () => { const i = idxs()[idxs().length - 1]; act((x) => ops.insertBlank(x, i), t('Adding…'), () => new Set([i + 1])); }, !any),
      b('scissors', t('Extract'), async () => {
        const list = idxs();
        await safe(async () => {
          const out = await withBusy(async () => ops.extractPages(await flush(), list), t('Extracting…'));
          await deliver(out, baseName() + '-pages.pdf', 'application/pdf');
        });
      }, !any),
      b('trash', t('Delete'), async () => {
        if (sel.size >= S.pageCount) { toast(t('Cannot delete all pages')); return; }
        const ok = await askConfirm({ title: t('Delete pages?'), text: t('{n} page(s) will be removed.', { n: sel.size }), ok: t('Delete'), danger: true });
        if (ok) { const list = idxs(); act((x) => ops.deletePages(x, list), t('Deleting…'), () => new Set([Math.min(list[0], S.pageCount - list.length - 1 < 0 ? 0 : list[0])])); }
      }, !any, 'danger'));
  }

  function draw() {
    if (io) io.disconnect();
    grid.textContent = '';
    drawBar();
    io = new IntersectionObserver((es) => {
      for (const en of es) {
        if (!en.isIntersecting) continue;
        io.unobserve(en.target);
        const i = +en.target.dataset.i;
        R.thumb(i, en.target.querySelector('canvas'), 220 * Math.min(window.devicePixelRatio || 1, 2)).catch(() => {});
      }
    }, { root: sheet.el.querySelector('.sheet-body'), rootMargin: '200px' });
    for (let i = 0; i < S.pageCount; i++) {
      const cell = h('button', { class: 'thumb' + (sel.has(i) ? ' on' : ''), type: 'button', 'data-i': i,
        onClick: () => { if (sel.has(i)) sel.delete(i); else sel.add(i); cell.classList.toggle('on', sel.has(i)); drawBar(); } },
      h('canvas'), h('span', { class: 'tn' }, String(i + 1)),
      h('span', { class: 'go', onClick: (ev) => { ev.stopPropagation(); sheet.close(); setTimeout(() => goTo(i, false), 240); } }, h('span', { html: icon('fullscreen') })));
      grid.append(cell);
      io.observe(cell);
    }
  }

  const sheet = openSheet({
    title: t('Pages'), tall: true, cls: 'pages',
    body: grid, footer: bar,
    onClose: () => { if (io) io.disconnect(); },
  });
  draw();
}

// ------------------------------------------------------------------------------------------
// more menu & dialogs
// ------------------------------------------------------------------------------------------
function openMenu() {
  if (!hasDoc()) return;
  actionSheet(S.name, [
    { icon: 'export', label: native ? t('Save / Share PDF') : t('Download PDF'), onClick: exportPdf },
    'sep',
    { icon: 'pages', label: t('Manage pages'), onClick: openPages },
    { icon: 'file_plus', label: t('Insert pages from another PDF'), onClick: insertFromPdf },
    { icon: 'image', label: t('Export this page as image'), onClick: exportPageImage },
    'sep',
    { icon: 'info', label: t('Document properties'), onClick: openMeta },
    S.password
      ? { icon: 'lock', label: t('Remove password'), onClick: () => { setPassword(null); toast(t('Password will be removed when saving')); } }
      : { icon: 'lock', label: t('Protect with password'), onClick: protect },
    'sep',
    { icon: 'invert', label: V.invert ? t('Normal colors') : t('Night reading'), onClick: () => setInvert(!V.invert) },
    { icon: 'fit_width', label: t('Fit to width'), onClick: fitWidth },
    { icon: 'sun', label: t('Appearance & language'), onClick: openSettings },
  ]);
}

async function insertFromPdf() {
  const [f] = await pickFiles('application/pdf,.pdf');
  if (!f) return;
  await safe(async () => {
    const other = await readBytes(f);
    const v = await askText({ title: t('Insert pages'), label: t('Insert after page (0 = at the start):'), value: String(V.page + 1), numeric: true });
    if (v == null) return;
    const after = Math.max(0, Math.min(S.pageCount, parseInt(v, 10) || 0)) - 1;
    await structural((b) => ops.insertPdf(b, other, after), t('Inserting…'));
  });
}

async function exportPageImage() {
  await safe(async () => {
    if (hasEdits()) await structural((b) => b);
    const png = await withBusy(() => R.renderPng(V.page, 2.5), t('Rendering…'));
    await deliver(png, `${baseName()}-p${V.page + 1}.png`, 'image/png');
  });
}

async function openMeta() {
  await safe(async () => {
    const m = await ops.getMeta(S.bytes);
    const f = {};
    const row = (k, label, val) => { f[k] = h('input', { type: 'text', dir: 'auto', value: val }); return h('label', { class: 'field' }, h('span', {}, label), f[k]); };
    const sheet = openSheet({
      title: t('Document properties'),
      body: h('div', { class: 'form' },
        row('title', t('Title'), m.title), row('author', t('Author'), m.author), row('subject', t('Subject'), m.subject), row('keywords', t('Keywords'), m.keywords),
        h('div', { class: 'meta-n' }, t('{n} page(s)', { n: m.pages }))),
      footer: h('div', { class: 'sheet-actions' },
        h('button', { class: 'btn', type: 'button', onClick: () => sheet.close() }, t('Cancel')),
        h('button', { class: 'btn primary', type: 'button', onClick: async () => {
          const meta = { title: f.title.value, author: f.author.value, subject: f.subject.value, keywords: f.keywords.value };
          sheet.close();
          await safe(() => structural((b) => ops.setMeta(b, meta), t('Saving…')));
        } }, t('Apply'))),
    });
  });
}

async function protect() {
  const pw = await askText({ title: t('Protect with password'), label: t('Choose a password:'), password: true, ok: t('Set') });
  if (!pw) return;
  const again = await askText({ title: t('Protect with password'), label: t('Repeat the password:'), password: true, ok: t('Set') });
  if (again == null) return;
  if (again !== pw) { toast(t('Passwords do not match')); return; }
  setPassword(pw);
  toast(t('The saved file will need this password'));
}

// ------------------------------------------------------------------------------------------
// settings
// ------------------------------------------------------------------------------------------
function applyTheme(th) {
  document.documentElement.dataset.theme = th;
  store.set('theme', th);
}
function initTheme() {
  const saved = store.get('theme');
  applyTheme(saved || (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
}

function openSettings() {
  const body = h('div', { class: 'form' });
  const seg = (label, opts, cur, on) => {
    const row = h('div', { class: 'seg-row' }, h('div', { class: 'seg-l' }, label));
    const wrap = h('div', { class: 'seg' });
    for (const [v, text] of opts) wrap.append(h('button', { type: 'button', class: v === cur ? 'on' : '', onClick: () => { on(v); sheet.close(); } }, text));
    row.append(wrap); body.append(row);
  };
  seg(t('Appearance'), [['light', t('Light')], ['dark', t('Dark')]], document.documentElement.dataset.theme, applyTheme);
  seg(t('Language'), [['ar', 'العربية'], ['en', 'English']], getLang(), (l) => { setLang(l); store.set('lang', l); renderAll(); });
  body.append(h('div', { class: 'about' }, 'PDF Toolkit · v1.0'));
  const sheet = openSheet({ title: t('Appearance & language'), body });
}

// ------------------------------------------------------------------------------------------
// start screen
// ------------------------------------------------------------------------------------------
function buildStart() {
  const s = $('#start');
  s.textContent = '';
  const feats = [t('Highlight & annotate'), t('Edit text'), t('Sign'), t('Redact'), t('Merge & split'), t('Password protect')];
  s.append(
    h('div', { class: 'start-top' },
      iconBtn('globe', t('Language'), openSettings), iconBtn(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon', t('Appearance'), () => { applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); buildStart(); })),
    h('div', { class: 'hero' },
      h('div', { class: 'logo', html: '<svg viewBox="0 0 48 48"><rect x="8" y="4" width="32" height="40" rx="6" fill="currentColor" opacity=".18"/><rect x="8" y="4" width="32" height="40" rx="6" fill="none" stroke="currentColor" stroke-width="2.5"/><path d="M16 17h16M16 24h16M16 31h9" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>' }),
      h('h1', {}, 'PDF Toolkit'),
      h('p', {}, t('Open, edit and sign PDF files right on your phone.'))),
    h('div', { class: 'start-actions' },
      h('button', { class: 'bigbtn primary', type: 'button', id: 'openbtn', onClick: openFromPicker }, h('span', { html: icon('open') }), t('Open PDF')),
      h('div', { class: 'two' },
        h('button', { class: 'bigbtn', type: 'button', onClick: newBlank }, h('span', { html: icon('file_plus') }), t('New blank PDF')),
        h('button', { class: 'bigbtn', type: 'button', onClick: mergeFlow }, h('span', { html: icon('merge') }), t('Merge PDFs')))),
    h('div', { class: 'feats' }, feats.map((f) => h('span', { class: 'feat' }, f))),
    h('div', { class: 'privacy' }, t('Your files stay on your device.')));
}

// ------------------------------------------------------------------------------------------
function renderAll() {
  document.documentElement.lang = getLang();
  document.documentElement.dir = getLang() === 'ar' ? 'rtl' : 'ltr';
  buildStart(); buildTop(); buildTools(); buildSearch(); refresh();
  const pill = $('#pill');
  if (pill) pill.setAttribute('aria-label', t('Go to page'));
}

function init() {
  initTheme();
  const saved = store.get('lang');
  setLang(saved || ((navigator.language || '').toLowerCase().startsWith('ar') ? 'ar' : 'en'));
  initView(scroller, $('#pages'));
  renderAll();
  app.dataset.screen = 'start';

  $('#pill').addEventListener('click', async () => {
    if (!hasDoc()) return;
    const v = await askText({ title: t('Go to page'), label: `1 – ${S.pageCount}`, value: String(V.page + 1), numeric: true });
    const n = parseInt(v, 10);
    if (n >= 1 && n <= S.pageCount) goTo(n - 1, false);
  });
  $('#zin').addEventListener('click', () => zoomBy(1.25));
  $('#zout').addEventListener('click', () => zoomBy(0.8));

  window.addEventListener('beforeunload', (e) => { if (hasDoc() && (S.dirty || hasEdits())) { e.preventDefault(); e.returnValue = ''; } });
  if (native) {
    CapApp.addListener('backButton', async () => {
      if (goBack()) return;
      if ($('#searchbar').classList.contains('show')) { toggleSearch(); return; }
      if (hasDoc()) { await closeDoc(); return; }
      CapApp.exitApp();
    });
  } else {
    history.pushState({}, '');
    window.addEventListener('popstate', () => { if (backStack.length) { goBack(); history.pushState({}, ''); } });
  }
  window.__pdf = { S, V, R, ops, openBytes, flush, exportPdf };
}

init();
