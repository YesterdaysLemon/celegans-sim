import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ROOT, parsePathBlocks } from "./release-coordinator.mjs";


const workflow = readFileSync(`${ROOT}/.github/workflows/deploy.yml`, "utf8");


test("release inputs build on pull requests and main", () => {
  const blocks = parsePathBlocks(workflow);
  assert.equal(blocks.length, 2);
  assert.deepEqual(blocks[0], blocks[1]);
  assert.deepEqual(blocks[0], [
    "Dockerfile", ".dockerignore", "requirements*.txt", "worm/**", "data/**",
    "tools/export_model.py", "tools/conform.py", "tools/manifest.py", "wasm/**",
    "web/**", "docker/**", ".github/scripts/**", ".github/workflows/deploy.yml",
  ]);
  assert.match(workflow, /push:\s*\n\s*branches:\s*\[main\]/);
  assert.match(workflow, /pull_request:/);
  assert.match(workflow, /workflow_dispatch:/);
});


test("automatic release waits for selective coverage since the last deployment", () => {
  assert.match(workflow, /actions: write/);
  assert.match(workflow, /deployments: write/);
  assert.match(workflow, /needs: validate/);
  assert.match(workflow, /node \.github\/scripts\/release-coordinator\.mjs/);
  assert.match(workflow, /vars\.DEPLOY_ENABLED == 'true'/);
  assert.match(workflow, /outputs:\s*\n\s*deploy: \$\{\{ steps\.coordinate\.outputs\.deploy \}\}/);
  assert.match(workflow, /environment:\s*\n\s*name: production/);
  assert.match(workflow, /concurrency:\s*\n\s*group: celegans-production/);
});


test("manual deployment is confirmed and webhook payload is exact-SHA signed", () => {
  assert.match(workflow, /github\.event_name == 'workflow_dispatch' && inputs\.confirm/);
  assert.match(workflow, /event: "push", branch: "main"/);
  assert.match(workflow, /repo: process\.env\.GITHUB_REPOSITORY/);
  assert.match(workflow, /sha: process\.env\.GITHUB_SHA/);
  assert.match(workflow, /crypto\.createHmac\("sha256"/);
  assert.match(workflow, /secrets\.DEPLOY_WEBHOOK_SECRET/);
  assert.match(workflow, /secrets\.DEPLOY_WEBHOOK_URL/);
  assert.match(workflow, /X-GitHub-Event: push/);
  assert.match(workflow, /X-Hub-Signature-256: \$signature/);
  assert.match(workflow, /--data-binary "\$payload"/);
});
