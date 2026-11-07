// Prints GitHub Actions annotations so failures are readable through the public check-run API.
import fs from 'node:fs';
const [, , level = 'error', title = 'info', file] = process.argv;
const body = file && fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
const lines = body.trim().split('\n').slice(-12).join(' | ').replace(/[\r%]/g, ' ').slice(0, 900);
console.log(`::${level} title=${title}::${lines}`);
