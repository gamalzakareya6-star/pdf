// Small DOM helpers: h(), toast, busy overlay, sheets, prompts. Plain DOM, no framework.
import { t } from './i18n.js';
import { icon } from './icons.js';

export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const iconBtn = (name, label, onClick, cls = '') =>
  h('button', { class: 'ibtn ' + cls, type: 'button', 'aria-label': label, title: label, onClick, html: icon(name) });

// ---- back-button stack ------------------------------------------------------------------
export const backStack = [];
export function pushCloser(fn) { backStack.push(fn); }
export function dropCloser(fn) { const i = backStack.lastIndexOf(fn); if (i >= 0) backStack.splice(i, 1); }
export function goBack() { const fn = backStack.pop(); if (fn) { fn(); return true; } return false; }

const layer = () => document.getElementById('layer');

// ---- toast / busy ---------------------------------------------------------------------------
let toastTimer = 0;
export function toast(msg, ms = 2600) {
  let el = document.getElementById('toast');
  if (!el) { el = h('div', { id: 'toast', role: 'status' }); layer().append(el); }
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

let busyCount = 0;
export function busy(on, text) {
  let el = document.getElementById('busy');
  if (on) {
    busyCount++;
    if (!el) { el = h('div', { id: 'busy' }, h('div', { class: 'spinner' }), h('div', { id: 'busytext' })); layer().append(el); }
    $('#busytext', el).textContent = text || t('Working…');
    el.classList.add('show');
  } else {
    busyCount = Math.max(0, busyCount - 1);
    if (el && !busyCount) el.classList.remove('show');
  }
}
export async function withBusy(fn, text) {
  busy(true, text);
  try { return await fn(); } finally { busy(false); }
}

// ---- bottom sheet --------------------------------------------------------------------------------
export function openSheet({ title, body, footer, onClose, tall = false, cls = '' }) {
  const backdrop = h('div', { class: 'backdrop' });
  const sheet = h('div', { class: 'sheet ' + cls + (tall ? ' tall' : ''), role: 'dialog' },
    h('div', { class: 'grab' }),
    title ? h('div', { class: 'sheet-title' }, title) : null,
    h('div', { class: 'sheet-body' }, body),
    footer || null);
  const root = h('div', { class: 'sheet-root' }, backdrop, sheet);
  layer().append(root);
  requestAnimationFrame(() => root.classList.add('open'));
  let closed = false;
  const api = {
    el: sheet,
    close() {
      if (closed) return;
      closed = true;
      dropCloser(api.close);
      root.classList.remove('open');
      setTimeout(() => root.remove(), 220);
      if (onClose) onClose();
    },
  };
  backdrop.addEventListener('click', api.close);
  pushCloser(api.close);
  return api;
}

// ---- modal prompts ------------------------------------------------------------------------------------
function modal(build) {
  return new Promise((resolve) => {
    const backdrop = h('div', { class: 'backdrop' });
    const box = h('div', { class: 'dialog', role: 'dialog' });
    const root = h('div', { class: 'dialog-root' }, backdrop, box);
    let done = false;
    const finish = (v) => {
      if (done) return;
      done = true;
      dropCloser(cancel);
      root.remove();
      resolve(v);
    };
    const cancel = () => finish(null);
    backdrop.addEventListener('click', cancel);
    pushCloser(cancel);
    build(box, finish);
    layer().append(root);
    requestAnimationFrame(() => root.classList.add('open'));
  });
}

export function askText({ title, label, value = '', multiline = false, password = false, ok = t('OK'), placeholder = '', numeric = false }) {
  return modal((box, finish) => {
    const input = multiline
      ? h('textarea', { rows: 4, dir: 'auto', placeholder })
      : h('input', { type: password ? 'password' : (numeric ? 'number' : 'text'), dir: 'auto', placeholder, autocomplete: 'off' });
    input.value = value;
    const go = () => finish(input.value);
    if (!multiline) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
    box.append(
      h('div', { class: 'dialog-title' }, title),
      label ? h('div', { class: 'dialog-label' }, label) : null,
      input,
      h('div', { class: 'dialog-actions' },
        h('button', { class: 'btn', type: 'button', onClick: () => finish(null) }, t('Cancel')),
        h('button', { class: 'btn primary', type: 'button', onClick: go }, ok)));
    setTimeout(() => { input.focus(); if (!multiline) input.select(); }, 60);
  });
}

export function askConfirm({ title, text = '', ok = t('OK'), danger = false, third = null }) {
  return modal((box, finish) => {
    box.append(
      h('div', { class: 'dialog-title' }, title),
      text ? h('div', { class: 'dialog-text' }, text) : null,
      h('div', { class: 'dialog-actions' },
        h('button', { class: 'btn', type: 'button', onClick: () => finish(false) }, t('Cancel')),
        third ? h('button', { class: 'btn', type: 'button', onClick: () => finish('third') }, third) : null,
        h('button', { class: 'btn primary' + (danger ? ' danger' : ''), type: 'button', onClick: () => finish(true) }, ok)));
  });
}

// list of actions in a sheet: items = [{icon, label, onClick, disabled, toggle, value}]
export function actionSheet(title, items) {
  const list = h('div', { class: 'list' });
  const sheet = openSheet({ title, body: list });
  for (const it of items) {
    if (it === 'sep') { list.append(h('div', { class: 'sep' })); continue; }
    const row = h('button', { class: 'row', type: 'button', disabled: !!it.disabled,
      onClick: () => { sheet.close(); setTimeout(() => it.onClick && it.onClick(), 60); } },
    h('span', { class: 'row-ic', html: it.icon ? icon(it.icon) : '' }),
    h('span', { class: 'row-label' }, it.label),
    it.value ? h('span', { class: 'row-value' }, it.value) : null);
    list.append(row);
  }
  return sheet;
}
