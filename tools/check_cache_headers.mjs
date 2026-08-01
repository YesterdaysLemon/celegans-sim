/* Assert the cache contract served by docker/nginx.conf.
 *
 * Run this against the container (or an nginx instance using the same config):
 *
 *   node tools/check_cache_headers.mjs http://127.0.0.1:8080
 *
 * The viewer has no build step. Its JavaScript import graph therefore uses stable,
 * unhashed URLs, all of which must revalidate. The WASM/model pair carries its content
 * hash as a query parameter and can be immutable.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const WEB = path.join(ROOT, 'web');
const base = process.argv[2];

if (!base) {
  console.error('usage: node tools/check_cache_headers.mjs http://host:port');
  process.exit(2);
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const item = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(item, out);
    else out.push(item);
  }
  return out;
}

const unhashed = walk(WEB)
  .filter(file => ['.js', '.css'].includes(path.extname(file)))
  .map(file => path.relative(WEB, file).split(path.sep).join('/'))
  .concat(['index.html', 'build.json'])
  .sort();

const manifest = JSON.parse(fs.readFileSync(path.join(WEB, 'build.json'), 'utf8'));
const immutable = Object.entries(manifest).map(([name, hash]) => `${name}?v=${hash}`);
const expected = [
  ['/', 'no-cache'],
  ...unhashed.map(asset => [`/${asset}`, 'no-cache']),
  ...immutable.map(asset => [`/${asset}`, 'public, max-age=31536000, immutable']),
];

async function requestWithRetry(url) {
  let last;
  for (let attempt = 0; attempt < 30; attempt++) {
    try {
      return await fetch(url, { method: 'HEAD' });
    } catch (error) {
      last = error;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  throw last;
}

/* What each extension must be *typed* as, not merely cached as.
 *
 * A browser refuses an ES module served with a non-JavaScript MIME type, so a wrong
 * Content-Type here is not a cosmetic header problem -- it is a blank page. This config had
 * exactly that defect: a server-level `types` block replaced the inherited MIME map instead
 * of extending it, leaving .js, .css and .html to fall through to application/octet-stream.
 * Nothing noticed, because this file only ever read Cache-Control and the browser smoke
 * test drives a different server with its own correct types.
 *
 * Matched on the media type alone, so a charset parameter is allowed through -- what the
 * browser dispatches on is the type, and pinning the whole header would fail on a
 * `; charset=utf-8` that is perfectly correct.
 */
const TYPES = {
  '.js': 'text/javascript',
  '.mjs': 'text/javascript',
  '.css': 'text/css',
  '.html': 'text/html',
  '.json': 'application/json',
  '.wasm': 'application/wasm',
  '.model': 'application/octet-stream',
};
// nginx has served .js as text/javascript since 1.21.1; before that it was
// application/javascript. Both are valid JavaScript MIME types to a browser, so accept
// either rather than pinning a version of the base image.
const ALSO_OK = { 'text/javascript': ['application/javascript'] };

function typeOf(asset) {
  const ext = path.extname(new URL(asset, 'http://x/').pathname);
  return TYPES[ext] || null;
}

const failures = [];
for (const [asset, policy] of expected) {
  const response = await requestWithRetry(new URL(asset, base));
  const actual = response.headers.get('cache-control');
  if (!response.ok) { failures.push(`${asset}: HTTP ${response.status}`); continue; }
  if (actual !== policy) failures.push(`${asset}: expected "${policy}", got "${actual}"`);

  const want = asset === '/' ? 'text/html' : typeOf(asset);
  if (want) {
    const got = (response.headers.get('content-type') || '').split(';')[0].trim();
    const ok = got === want || (ALSO_OK[want] || []).includes(got);
    if (!ok) failures.push(`${asset}: Content-Type expected "${want}", got "${got || '(none)'}"`);
  }
}

if (failures.length) {
  for (const failure of failures) console.error(`FAIL ${failure}`);
  console.error(`${failures.length} failure(s).`);
  process.exit(1);
}

console.log(
  `${expected.length} viewer responses have explicit cache policies: ` +
  `${unhashed.length + 1} revalidate, ${immutable.length} immutable.`,
);
console.log('Every response also carries a Content-Type a browser will accept.');
