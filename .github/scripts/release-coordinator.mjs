#!/usr/bin/env node

/** Fail-closed, change-sensitive coordination for production releases. */

import { execFileSync, spawnSync } from "node:child_process";
import { appendFileSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";


export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const WORKFLOWS = Object.freeze([
  { id: "python.yml", label: "python" },
  { id: "viewer.yml", label: "viewer" },
]);

const SHA_RE = /^[0-9a-f]{40}$/;
const API_VERSION = "2022-11-28";


export class SupersededError extends Error {}


export function parsePathBlocks(text) {
  const blocks = [];
  const pattern = /^\s*paths:\s*\[/gm;
  for (const match of text.matchAll(pattern)) {
    const start = text.indexOf("[", match.index);
    let depth = 0;
    let end = -1;
    for (let i = start; i < text.length; i += 1) {
      if (text[i] === "[") depth += 1;
      if (text[i] === "]") {
        depth -= 1;
        if (depth === 0) {
          end = i;
          break;
        }
      }
    }
    if (end < 0) throw new Error(`unterminated paths block near offset ${start}`);
    const span = text.slice(start + 1, end);
    const globs = [...span.matchAll(/'([^']*)'/g)].map((item) => item[1]);
    const residue = span.replaceAll(/'[^']*'/g, "").replaceAll(",", "").trim();
    if (residue) throw new Error(`unparsed paths text: ${JSON.stringify(residue)}`);
    if (!globs.length) throw new Error(`paths block near offset ${start} parsed to nothing`);
    blocks.push(globs);
  }
  return blocks;
}


export function workflowGlobs(workflow, root = ROOT) {
  const text = readFileSync(resolve(root, ".github", "workflows", workflow), "utf8");
  const blocks = parsePathBlocks(text);
  if (blocks.length !== 2) {
    throw new Error(`${workflow}: expected push and pull_request path filters; got ${blocks.length}`);
  }
  if (JSON.stringify(blocks[0]) !== JSON.stringify(blocks[1])) {
    throw new Error(`${workflow}: push and pull_request path filters differ`);
  }
  return blocks[0];
}


export function globRegex(glob) {
  if (glob.startsWith("!") || glob.includes("+")) {
    throw new Error(`unsupported GitHub filter syntax in ${JSON.stringify(glob)}`);
  }
  let expression = "";
  for (let i = 0; i < glob.length; i += 1) {
    const char = glob[i];
    if (char === "*" && glob[i + 1] === "*") {
      expression += ".*";
      i += 1;
    } else if (char === "*") {
      expression += "[^/]*";
    } else if (char === "?") {
      expression += "[^/]";
    } else {
      expression += char.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }
  }
  return new RegExp(`^${expression}$`);
}


export function matchesAny(path, globs) {
  return globs.some((glob) => globRegex(glob).test(path));
}


export function requiredWorkflows(changedPaths, specs = WORKFLOWS, root = ROOT) {
  return specs.filter((spec) => matchesAny(changedPaths, workflowGlobs(spec.id, root)));
}


function git(args, root = ROOT) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
}


export function isAncestor(ancestor, descendant, root = ROOT) {
  if (!SHA_RE.test(ancestor) || !SHA_RE.test(descendant)) return false;
  const result = spawnSync(
    "git", ["merge-base", "--is-ancestor", ancestor, descendant],
    { cwd: root, encoding: "utf8" },
  );
  if (result.status === 0) return true;
  if (result.status === 1) return false;
  throw new Error(`git merge-base failed: ${result.stderr.trim()}`);
}


export function changedFilesBetween(base, head, root = ROOT) {
  if (!SHA_RE.test(base) || !SHA_RE.test(head)) throw new Error("invalid deployment SHA");
  if (!isAncestor(base, head, root)) {
    throw new Error(`last deployed SHA ${base} is not an ancestor of ${head}`);
  }
  const output = git(["diff", "--no-renames", "--name-only", `${base}..${head}`], root);
  return output ? output.split(/\r?\n/).filter(Boolean) : [];
}


export function trackedFiles(head, root = ROOT) {
  if (!SHA_RE.test(head)) throw new Error("invalid release SHA");
  const output = git(["ls-tree", "-r", "--name-only", head], root);
  const files = output.split(/\r?\n/).filter(Boolean);
  if (files.length < 100) throw new Error(`release tree unexpectedly contains ${files.length} files`);
  return files;
}


export function selectCoverageRun(runs, { base, head, globs, ancestor, changes }) {
  const candidates = [...runs]
    .filter((run) => ["push", "workflow_dispatch"].includes(run.event))
    .filter((run) => SHA_RE.test(run.head_sha))
    .sort((left, right) => String(right.created_at).localeCompare(String(left.created_at)));
  for (const run of candidates) {
    if (!ancestor(base, run.head_sha) || !ancestor(run.head_sha, head)) continue;
    if (changes(run.head_sha, head).some((path) => matchesAny(path, globs))) continue;
    return run;
  }
  return null;
}


function sleep(ms) {
  return new Promise((accept) => setTimeout(accept, ms));
}


function apiClient({ apiUrl, repository, token, fetchImpl = fetch }) {
  if (!repository || !token) throw new Error("GITHUB_REPOSITORY and GITHUB_TOKEN are required");
  return async function api(path, options = {}) {
    const response = await fetchImpl(`${apiUrl}/repos/${repository}${path}`, {
      ...options,
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": API_VERSION,
        "Content-Type": "application/json",
        ...options.headers,
      },
    });
    if (!response.ok) throw new Error(`GitHub API ${options.method ?? "GET"} ${path}: HTTP ${response.status}`);
    if (response.status === 204) return null;
    return response.json();
  };
}


export async function lastSuccessfulDeployment(api, head, ancestor) {
  const deployments = await api("/deployments?environment=production&per_page=100");
  for (const deployment of deployments) {
    if (!SHA_RE.test(deployment.sha) || !ancestor(deployment.sha, head)) continue;
    const statuses = await api(`/deployments/${deployment.id}/statuses?per_page=1`);
    if (statuses[0]?.state === "success") return deployment.sha;
  }
  return null;
}


async function remoteMainSha() {
  const output = git(["ls-remote", "origin", "refs/heads/main"]);
  const sha = output.split(/\s+/, 1)[0];
  if (!SHA_RE.test(sha)) throw new Error("origin/main did not resolve to a commit");
  return sha;
}


async function assertCurrent(head) {
  const current = await remoteMainSha();
  if (current !== head) {
    throw new SupersededError(`skipping ${head}; main is now ${current}`);
  }
}


async function workflowRuns(api, workflow) {
  const query = new URLSearchParams({ branch: "main", per_page: "100" });
  const payload = await api(`/actions/workflows/${encodeURIComponent(workflow)}/runs?${query}`);
  return payload.workflow_runs;
}


async function coverageRun(api, spec, base, head, globs) {
  const runs = await workflowRuns(api, spec.id);
  return selectCoverageRun(runs, {
    base,
    head,
    globs,
    ancestor: (left, right) => isAncestor(left, right),
    changes: (left, right) => changedFilesBetween(left, right),
  });
}


async function requireSuccessfulJobs(api, run, label) {
  const payload = await api(`/actions/runs/${run.id}/jobs?filter=latest&per_page=100`);
  const successes = payload.jobs.filter((job) => job.conclusion === "success");
  if (!successes.length) {
    throw new Error(`${label} run ${run.html_url} completed without a successful job; CI may be disabled`);
  }
}


async function waitForCoverage(api, spec, { base, head, globs, timeoutMs = 40 * 60_000 }) {
  const started = Date.now();
  let dispatched = false;
  let lastStatus = "";
  while (Date.now() - started < timeoutMs) {
    await assertCurrent(head);
    const run = await coverageRun(api, spec, base, head, globs);
    if (!run && !dispatched && Date.now() - started >= 20_000) {
      await assertCurrent(head);
      console.log(`${spec.label}: no covering run exists; dispatching ${spec.id} on current main`);
      await api(`/actions/workflows/${encodeURIComponent(spec.id)}/dispatches`, {
        method: "POST",
        body: JSON.stringify({ ref: "main" }),
      });
      dispatched = true;
    } else if (run) {
      const status = `${run.status}/${run.conclusion ?? "pending"}`;
      if (status !== lastStatus) {
        console.log(`${spec.label}: ${status} at ${run.head_sha} (${run.html_url})`);
        lastStatus = status;
      }
      if (run.status === "completed") {
        if (run.conclusion !== "success") {
          throw new Error(`${spec.label} coverage failed: ${run.html_url} (${run.conclusion})`);
        }
        await requireSuccessfulJobs(api, run, spec.label);
        return run;
      }
    }
    await sleep(20_000);
  }
  throw new Error(`${spec.label} produced no successful covering run within ${timeoutMs / 60_000} minutes`);
}


function setDeployOutput(value) {
  const output = process.env.GITHUB_OUTPUT;
  if (!output) throw new Error("GITHUB_OUTPUT is required");
  appendFileSync(output, `deploy=${value ? "true" : "false"}\n`);
}


export async function coordinate(env = process.env) {
  const head = env.GITHUB_SHA;
  if (!SHA_RE.test(head)) throw new Error("GITHUB_SHA must be a full lowercase commit SHA");
  await assertCurrent(head);

  if (env.GITHUB_EVENT_NAME === "workflow_dispatch") {
    console.log(`manual deployment confirmed for current main ${head}`);
    return true;
  }

  const api = apiClient({
    apiUrl: env.GITHUB_API_URL ?? "https://api.github.com",
    repository: env.GITHUB_REPOSITORY,
    token: env.GITHUB_TOKEN,
  });
  const base = await lastSuccessfulDeployment(
    api, head, (left, right) => isAncestor(left, right),
  );
  const changed = base ? changedFilesBetween(base, head) : trackedFiles(head);
  console.log(base
    ? `last successful production SHA: ${base}; ${changed.length} undeployed paths changed`
    : `no successful production deployment is recorded; checking the full ${changed.length}-path tree`);

  const required = requiredWorkflows(changed);
  if (!required.length) {
    console.log("release-only change: the production image gate is sufficient");
  } else {
    console.log(`required CI coverage: ${required.map((item) => item.label).join(", ")}`);
    await Promise.all(required.map((spec) => waitForCoverage(api, spec, {
      base: base ?? git(["rev-list", "--max-parents=0", head]).split(/\r?\n/)[0],
      head,
      globs: workflowGlobs(spec.id),
    })));
  }
  await assertCurrent(head);
  return true;
}


async function main() {
  try {
    setDeployOutput(await coordinate());
  } catch (error) {
    if (error instanceof SupersededError) {
      console.log(error.message);
      setDeployOutput(false);
      return;
    }
    throw error;
  }
}


if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  await main();
}
