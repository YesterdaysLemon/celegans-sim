import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  utimesSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.join(HERE, 'conform.mjs');

function runFixture(present, staleReference = false) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'celegans-conform-'));
  const wasmDir = path.join(root, 'wasm');
  const webDir = path.join(root, 'web');
  mkdirSync(wasmDir);
  mkdirSync(webDir);
  copyFileSync(SCRIPT, path.join(wasmDir, 'conform.mjs'));

  if (present.includes('worm.wasm')) {
    writeFileSync(path.join(webDir, 'worm.wasm'), Buffer.from([0, 97, 115, 109, 1, 0, 0, 0]));
  }
  if (present.includes('worm.model')) {
    writeFileSync(path.join(webDir, 'worm.model'), Buffer.alloc(12));
  }
  if (present.includes('conform.json')) {
    writeFileSync(path.join(webDir, 'conform.json'), '{}');
  }

  if (staleReference) {
    const old = new Date('2026-01-01T00:00:00Z');
    const fresh = new Date('2026-01-02T00:00:00Z');
    utimesSync(path.join(webDir, 'conform.json'), old, old);
    utimesSync(path.join(webDir, 'worm.model'), fresh, fresh);
  }

  try {
    return spawnSync(process.execPath, [path.join(wasmDir, 'conform.mjs')], {
      encoding: 'utf8',
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

const cases = [
  {
    missing: 'worm.wasm',
    present: ['worm.model', 'conform.json'],
    command: 'cd wasm && npx asc assembly/index.ts --target release',
  },
  {
    missing: 'worm.model',
    present: ['worm.wasm', 'conform.json'],
    command: 'PYTHONPATH=. python tools/export_model.py',
  },
  {
    missing: 'conform.json',
    present: ['worm.wasm', 'worm.model'],
    command: 'PYTHONPATH=. python tools/conform.py > web/conform.json',
  },
];

for (const fixture of cases) {
  test(`missing ${fixture.missing} is a guided setup error`, () => {
    const result = runFixture(fixture.present);
    assert.equal(result.status, 2);
    assert.match(result.stderr, new RegExp(`Missing web/${fixture.missing}`));
    assert.ok(result.stderr.includes(fixture.command));
    assert.doesNotMatch(result.stderr, /ENOENT|node:fs/);
  });
}

test('an old reference is warned about before conformance starts', () => {
  const result = runFixture(['worm.wasm', 'worm.model', 'conform.json'], true);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /web\/conform\.json is older than web\/worm\.model/);
  assert.notEqual(result.status, 2);
});
