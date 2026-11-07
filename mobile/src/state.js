// Document state: bytes of the PDF + pending (not yet baked) edits, with undo/redo.
// Edits are plain objects in "view space" (points, origin top-left of the displayed page, after /Rotate).
// Everything here is immutable-by-convention so snapshots are cheap (they share references).

export const S = {
  bytes: null,        // Uint8Array (never encrypted)
  edits: {},          // { [pageIndex]: Edit[] }
  pageCount: 0,
  name: 'document.pdf',
  password: null,     // re-applied when exporting
  dirty: false,
  undo: [],
  redo: [],
};

const subs = new Set();
export const subscribe = (fn) => { subs.add(fn); return () => subs.delete(fn); };
const emit = (kind) => subs.forEach((f) => { try { f(kind); } catch (e) { console.error(e); } });

const snap = () => ({ bytes: S.bytes, edits: S.edits, pageCount: S.pageCount });
const MAX_UNDO = 40;

function push() {
  S.undo.push(snap());
  if (S.undo.length > MAX_UNDO) S.undo.shift();
  S.redo.length = 0;
}

export function loadNew(bytes, name, password, pageCount) {
  S.bytes = bytes; S.name = name || 'document.pdf'; S.password = password || null;
  S.pageCount = pageCount; S.edits = {}; S.undo = []; S.redo = []; S.dirty = false;
  emit('load');
}

export function commitEdits(edits) {
  push(); S.edits = edits; S.dirty = true; emit('edits');
}

export function commitBytes(bytes, pageCount, edits = {}) {
  push(); S.bytes = bytes; S.pageCount = pageCount; S.edits = edits; S.dirty = true; emit('structure');
}

function restore(s) {
  const structural = s.bytes !== S.bytes || s.pageCount !== S.pageCount;
  S.bytes = s.bytes; S.edits = s.edits; S.pageCount = s.pageCount; S.dirty = true;
  emit(structural ? 'structure' : 'edits');
}

export function undo() { if (!S.undo.length) return; S.redo.push(snap()); restore(S.undo.pop()); }
export function redo() { if (!S.redo.length) return; S.undo.push(snap()); restore(S.redo.pop()); }
export const canUndo = () => S.undo.length > 0;
export const canRedo = () => S.redo.length > 0;

export function addEdits(page, list) {
  commitEdits({ ...S.edits, [page]: (S.edits[page] || []).concat(list) });
}
export const addEdit = (page, e) => addEdits(page, [e]);

export function replaceEdit(page, idx, e) {
  const list = (S.edits[page] || []).slice();
  list[idx] = e;
  commitEdits({ ...S.edits, [page]: list });
}

export function removeEdit(page, idx) {
  const list = (S.edits[page] || []).slice();
  list.splice(idx, 1);
  commitEdits({ ...S.edits, [page]: list });
}

export const hasEdits = () => Object.values(S.edits).some((l) => l && l.length);
export const markSaved = () => { S.dirty = false; emit('saved'); };
export const setPassword = (pw) => { S.password = pw || null; S.dirty = true; emit('meta'); };
