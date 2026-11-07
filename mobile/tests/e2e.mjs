// End-to-end test: serves dist/, drives the app in a Pixel 7 emulation, saves screenshots, verifies output PDFs.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { chromium, devices } from 'playwright';
import { PDFDocument, StandardFonts } from '@cantoo/pdf-lib';

const DIST = path.resolve('dist');
const SHOTS = path.resolve('shots');
fs.mkdirSync(SHOTS, { recursive: true });
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.json': 'application/json', '.wasm': 'application/wasm' };

const server = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(DIST, p);
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); res.end('nf'); return; }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(4173, '127.0.0.1', r));

const failures = [];
const ok = (name, cond, extra = '') => {
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`);
  if (!cond) failures.push(name + (extra ? ` (${extra})` : ''));
};

async function makePdf() {
  const d = await PDFDocument.create();
  const f = await d.embedFont(StandardFonts.Helvetica);
  const p = d.addPage([595, 842]);
  p.drawText('Hello World', { x: 60, y: 760, size: 28, font: f });
  p.drawText('Invoice 123 total 450 dollars', { x: 60, y: 700, size: 18, font: f });
  p.drawText('Second paragraph of the sample document', { x: 60, y: 660, size: 14, font: f });
  p.drawText('Confidential secret code ZEBRA', { x: 60, y: 600, size: 16, font: f });
  const p2 = d.addPage([595, 842]);
  p2.drawText('Page two', { x: 60, y: 760, size: 28, font: f });
  return Buffer.from(await d.save()).toString('base64');
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ ...devices['Pixel 7'], acceptDownloads: true, locale: 'en-US' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
const shot = (n) => page.screenshot({ path: path.join(SHOTS, n + '.png') });

try {
  await page.goto('http://127.0.0.1:4173/');
  await page.waitForSelector('#openbtn');
  await shot('01-start-en');
  await page.evaluate(() => { localStorage.setItem('lang', 'ar'); });
  await page.reload();
  await page.waitForSelector('#openbtn');
  await shot('02-start-ar');
  ok('arabic direction', await page.evaluate(() => document.documentElement.dir === 'rtl'));
  await page.evaluate(() => { localStorage.setItem('lang', 'en'); });
  await page.reload();
  await page.waitForSelector('#openbtn');

  const b64 = await makePdf();
  await page.evaluate(async (b) => {
    await window.__pdf.openBytes(Uint8Array.from(atob(b), (c) => c.charCodeAt(0)), 'sample.pdf');
  }, b64);
  await page.waitForSelector('.page.ready', { timeout: 20000 });
  await page.waitForTimeout(500);
  await shot('03-viewer');
  ok('viewer visible', await page.evaluate(() => document.getElementById('app').dataset.screen === 'viewer'));
  ok('page count 2', (await page.evaluate(() => window.__pdf.S.pageCount)) === 2);
  ok('canvas has ink', await page.evaluate(() => {
    const c = document.querySelector('.page.ready canvas.pdf');
    const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    let dark = 0; for (let i = 0; i < d.length; i += 40) if (d[i] < 100) dark++;
    return dark > 20;
  }));

  // helper: page-relative -> client coords
  const at = (x, y) => page.evaluate(([x, y]) => {
    const r = document.querySelector('.page').getBoundingClientRect();
    return [r.left + x * window.__pdf.V.zoom, r.top + y * window.__pdf.V.zoom];
  }, [x, y]);
  const wordRect = (w) => page.evaluate(async (w) => {
    const words = await window.__pdf.R.getWords(0);
    const k = words.find((o) => o.s === w);
    const r = document.querySelector('.page').getBoundingClientRect();
    const z = window.__pdf.V.zoom;
    return { x0: r.left + k.x0 * z, y0: r.top + k.y0 * z, x1: r.left + k.x1 * z, y1: r.top + k.y1 * z };
  }, w);
  const edits = () => page.evaluate(() => JSON.parse(JSON.stringify(window.__pdf.S.edits, (k, v) => (v instanceof Uint8Array ? '[bytes]' : v))));
  const drag = async (a, b) => { await page.mouse.move(a[0], a[1]); await page.mouse.down(); await page.mouse.move((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, { steps: 4 }); await page.mouse.move(b[0], b[1], { steps: 4 }); await page.mouse.up(); };

  // ink
  await page.click('[data-tool=ink]');
  await drag(await at(300, 300), await at(420, 360));
  let e = await edits();
  ok('ink edit created', (e[0] || []).some((x) => x.t === 'ink'));

  // highlight text
  await page.click('[data-tool=hl]');
  const hw = await wordRect('Hello');
  const ww = await wordRect('World');
  await drag([hw.x0 + 2, (hw.y0 + hw.y1) / 2], [ww.x1 - 2, (ww.y0 + ww.y1) / 2]);
  await page.waitForTimeout(300);
  e = await edits();
  ok('highlight created', (e[0] || []).some((x) => x.t === 'hl'));

  // text (Arabic + latin)
  await page.click('[data-tool=text]');
  await page.mouse.click(...(await at(80, 480)));
  await page.waitForSelector('.texted');
  await page.fill('.texted', 'مرحبا بالعالم Hello');
  await shot('04-text-editor');
  await page.click('.tb.ok');
  e = await edits();
  ok('text edit created', (e[0] || []).some((x) => x.t === 'text'));

  // rectangle
  await page.click('[data-tool=rect]');
  await drag(await at(300, 450), await at(480, 520));
  e = await edits();
  ok('rect created', (e[0] || []).some((x) => x.t === 'rect'));

  // select + delete the rect
  await page.click('[data-tool=select]');
  await page.mouse.click(...(await at(300, 485)));
  await page.waitForTimeout(150);
  ok('selection made', await page.evaluate(() => !!window.__pdf.V.sel));
  await shot('05-selected');
  await page.click('.chip.danger');
  e = await edits();
  ok('rect deleted', !(e[0] || []).some((x) => x.t === 'rect'));

  // undo restores it, redo removes again
  await page.click('.u-undo');
  e = await edits();
  ok('undo restores rect', (e[0] || []).some((x) => x.t === 'rect'));
  await page.click('.u-redo');

  // edit existing text
  await page.click('[data-tool=edit]');
  const iw = await wordRect('Second');
  await page.mouse.click(iw.x0 + 4, (iw.y0 + iw.y1) / 2);
  await page.waitForSelector('.dialog textarea');
  await page.fill('.dialog textarea', 'Edited paragraph');
  await page.click('.dialog .btn.primary');
  await page.waitForTimeout(200);
  e = await edits();
  ok('edit-text produced cover+text', (e[0] || []).filter((x) => x.t === 'text' && x.text === 'Edited paragraph').length === 1);

  // redact
  await page.click('[data-tool=redact]');
  const zr = await wordRect('ZEBRA');
  await drag([zr.x0 - 4, zr.y0 - 3], [zr.x1 + 4, zr.y1 + 3]);
  e = await edits();
  ok('redact created', (e[0] || []).some((x) => x.t === 'redact'));
  await page.click('[data-tool=hand]');
  await shot('06-edited');

  // search
  await page.click('button[aria-label=Search]');
  await page.fill('#q', 'invoice');
  await page.waitForTimeout(700);
  ok('search finds result', await page.evaluate(() => window.__pdf.V.search.list.length >= 1));
  await shot('07-search');
  await page.click('#searchbar button[aria-label=Close]');

  // pages sheet
  await page.click('button[aria-label=Pages]');
  await page.waitForSelector('.thumb canvas');
  await page.waitForTimeout(700);
  await shot('08-pages');
  await page.click('.pbtn:has-text("Duplicate")');
  await page.waitForFunction(() => window.__pdf.S.pageCount === 3, null, { timeout: 15000 });
  ok('duplicate page -> 3 pages', true);
  await page.waitForTimeout(500);
  await page.keyboard.press('Escape');
  await page.evaluate(() => document.querySelector('.sheet-root .backdrop')?.click());
  await page.waitForTimeout(400);

  // menu screenshot
  await page.click('button[aria-label=More]');
  await page.waitForTimeout(400);
  await shot('09-menu');
  await page.evaluate(() => document.querySelector('.sheet-root .backdrop')?.click());
  await page.waitForTimeout(300);

  // export & verify
  const dl = page.waitForEvent('download', { timeout: 30000 });
  await page.evaluate(() => window.__pdf.exportPdf());
  const download = await dl;
  const outPath = path.join(SHOTS, 'export.pdf');
  await download.saveAs(outPath);
  const out = await PDFDocument.load(fs.readFileSync(outPath));
  ok('exported pdf has 3 pages', out.getPageCount() === 3);

  await page.evaluate(async (b64out) => {
    await window.__pdf.openBytes(Uint8Array.from(atob(b64out), (c) => c.charCodeAt(0)), 'out.pdf');
  }, fs.readFileSync(outPath).toString('base64'));
  await page.waitForSelector('.page.ready');
  await page.waitForTimeout(800);
  await shot('10-exported-reopened');
  const words = await page.evaluate(async () => (await window.__pdf.R.getWords(0)).map((w) => w.s));
  ok('redacted text is gone from file', !words.includes('ZEBRA') && !words.includes('Confidential'), words.join(' ').slice(0, 80));

  // encryption roundtrip
  const enc = await page.evaluate(async () => {
    const { ops, S, R } = window.__pdf;
    const e2 = await ops.encryptPdf(S.bytes, 'secret1');
    let needs = false;
    try { await R.openDoc(e2); } catch (er) { needs = er && er.name === 'PasswordException'; }
    const dec = await ops.decryptPdf(e2, 'secret1');
    return { needs, n: await ops.pageCountOf(dec) };
  });
  ok('encrypted pdf requires password', enc.needs);
  ok('decrypt roundtrip', enc.n >= 1);

  // dark mode + arabic UI shot
  await page.evaluate(() => { localStorage.setItem('lang', 'ar'); localStorage.setItem('theme', 'dark'); });
  await page.reload();
  await page.waitForSelector('#openbtn');
  await shot('11-start-ar-dark');
} catch (err) {
  failures.push('exception: ' + (err && err.message));
  console.log('EXCEPTION', err);
  try { await shot('99-failure'); } catch (e2) { /* ignore */ }
}

const real = errors.filter((e) => !/favicon|net::ERR/i.test(e));
ok('no console/page errors', real.length === 0, real.slice(0, 3).join(' || '));
await browser.close();
server.close();
if (failures.length) {
  console.log('::error title=e2e failed::' + failures.join(' ;; ').replace(/[\r\n%]/g, ' ').slice(0, 900));
  process.exit(1);
}
console.log('all e2e checks passed');
