"""Fail-closed policy checks for the production deployment workflow."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


def _path_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    for match in re.finditer(r"^\s*paths:\s*\[", text, re.MULTILINE):
        start = text.index("[", match.start())
        depth = 0
        for end in range(start, len(text)):
            if text[end] == "[":
                depth += 1
            elif text[end] == "]":
                depth -= 1
                if depth == 0:
                    break
        else:
            raise AssertionError("unterminated deployment paths block")
        span = text[start + 1:end]
        globs = re.findall(r"'([^']*)'", span)
        residue = re.sub(r"'[^']*'", "", span).replace(",", "").split()
        assert not residue, "unparsed deployment paths text: %r" % residue
        assert globs, "deployment paths block parsed to nothing"
        blocks.append(globs)
    return blocks


def test_release_inputs_build_on_pull_requests_and_main():
    text = WORKFLOW.read_text()
    blocks = _path_blocks(text)
    assert len(blocks) == 2, "push and pull_request each need an explicit paths filter"
    assert blocks[0] == blocks[1], "PR validation and main deployment inputs must agree"
    assert blocks[0] == [
        "Dockerfile", ".dockerignore", "requirements*.txt", "worm/**", "data/**",
        "tools/export_model.py", "tools/conform.py", "tools/manifest.py", "wasm/**",
        "web/**", "docker/**", ".github/workflows/deploy.yml",
    ]
    assert re.search(r"push:\s*\n\s*branches:\s*\[main\]", text)
    assert "pull_request:" in text
    assert "workflow_dispatch:" in text


def test_automatic_deploy_requires_a_green_current_main_build():
    text = WORKFLOW.read_text()
    assert "needs: validate" in text
    assert "docker build --tag \"celegans-sim:ci-${GITHUB_SHA}\" ." in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "vars.DEPLOY_ENABLED == 'true'" in text
    assert "git ls-remote origin refs/heads/main" in text
    assert "steps.current.outputs.deploy == 'true'" in text
    assert "cancel-in-progress: false" in text


def test_manual_deploy_is_confirmed_and_the_webhook_is_bound_to_the_exact_sha():
    text = WORKFLOW.read_text()
    assert "github.event_name == 'workflow_dispatch' && inputs.confirm" in text
    assert 'event: "push", branch: "main"' in text
    assert "repo: process.env.GITHUB_REPOSITORY" in text
    assert "sha: process.env.GITHUB_SHA" in text
    assert 'crypto.createHmac("sha256"' in text
    assert "secrets.DEPLOY_WEBHOOK_SECRET" in text
    assert "secrets.DEPLOY_WEBHOOK_URL" in text
    assert 'X-GitHub-Event: push' in text
    assert 'X-Hub-Signature-256: $signature' in text
    assert '--data-binary "$payload"' in text
