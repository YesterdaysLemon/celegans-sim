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

const failures = [];
for (const [asset, policy] of expected) {
  const response = await requestWithRetry(new URL(asset, base));
  const actual = response.headers.get('cache-control');
  if (!response.ok) failures.push(`${asset}: HTTP ${response.status}`);
  else if (actual !== policy) failures.push(`${asset}: expected "${policy}", got "${actual}"`);
}

if (failures.length) {
  for (const failure of failures) console.error(`FAIL ${failure}`);
  console.error(`${failures.length} cache-policy failure(s).`);
  process.exit(1);
}

console.log(
  `${expected.length} viewer responses have explicit cache policies: ` +
  `${unhashed.length + 1} revalidate, ${immutable.length} immutable.`,
);
