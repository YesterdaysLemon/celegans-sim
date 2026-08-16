import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ROOT,
  globRegex,
  lastSuccessfulDeployment,
  parsePathBlocks,
  requiredWorkflows,
  selectCoverageRun,
  workflowGlobs,
} from "./release-coordinator.mjs";


test("workflow path parsers fail closed and push matches pull request", () => {
  for (const name of ["python.yml", "viewer.yml", "deploy.yml"]) {
    const text = readFileSync(`${ROOT}/.github/workflows/${name}`, "utf8");
    const blocks = parsePathBlocks(text);
    assert.equal(blocks.length, 2);
    assert.deepEqual(blocks[0], blocks[1]);
  }
  assert.throws(() => parsePathBlocks("paths: ['web/**', unquoted]"), /unparsed/);
  assert.throws(() => parsePathBlocks("paths: ['web/**'"), /unterminated/);
});


test("GitHub path globs use anchored separator-aware matching", () => {
  assert.equal(globRegex("web/**").test("web/viewer/app.js"), true);
  assert.equal(globRegex("web/**").test("website/app.js"), false);
  assert.equal(globRegex("tools/*.py").test("tools/a.py"), true);
  assert.equal(globRegex("tools/*.py").test("tools/nested/a.py"), false);
  assert.equal(globRegex("requirements*.txt").test("requirements-dev.txt"), true);
  assert.throws(() => globRegex("!docs/**"), /unsupported/);
});


test("only workflows whose declared inputs changed are required", () => {
  assert.deepEqual(requiredWorkflows(["web/style.css"]).map((item) => item.id), ["viewer.yml"]);
  assert.deepEqual(requiredWorkflows(["worm/engine.py"]).map((item) => item.id), ["python.yml"]);
  assert.deepEqual(
    requiredWorkflows(["wasm/assembly/index.ts"]).map((item) => item.id),
    ["python.yml", "viewer.yml"],
  );
  assert.deepEqual(requiredWorkflows(["Dockerfile"]).map((item) => item.id), []);
});


test("a successful ancestor run covers later commits only when its inputs stayed unchanged", () => {
  const base = "1".repeat(40);
  const model = "2".repeat(40);
  const ui = "3".repeat(40);
  const order = new Map([[base, 0], [model, 1], [ui, 2]]);
  const runs = [
    { id: 8, event: "push", head_sha: model, created_at: "2026-08-16T01:00:00Z" },
  ];
  const ancestor = (left, right) => order.get(left) <= order.get(right);
  const unchanged = () => ["web/style.css"];
  const changedAgain = () => ["worm/engine.py"];

  assert.equal(selectCoverageRun(runs, {
    base, head: ui, globs: workflowGlobs("python.yml"), ancestor, changes: unchanged,
  })?.id, 8);
  assert.equal(selectCoverageRun(runs, {
    base, head: ui, globs: workflowGlobs("python.yml"), ancestor, changes: changedAgain,
  }), null);
});


test("the deployment baseline is the newest ancestor whose latest status succeeded", async () => {
  const head = "f".repeat(40);
  const old = "a".repeat(40);
  const failed = "b".repeat(40);
  const calls = [];
  const api = async (path) => {
    calls.push(path);
    if (path.startsWith("/deployments?")) return [
      { id: 2, sha: failed },
      { id: 1, sha: old },
    ];
    if (path.includes("/2/")) return [{ state: "failure" }];
    return [{ state: "success" }];
  };
  const ancestor = (left, right) => right === head && [old, failed].includes(left);
  assert.equal(await lastSuccessfulDeployment(api, head, ancestor), old);
  assert.equal(calls.length, 3);
});
