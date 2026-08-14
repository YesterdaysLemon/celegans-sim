#!/bin/bash
# SessionStart hook: the stale-checkpoint guard, plus a venv bootstrap.
#
# WHY THIS EXISTS. Remote (web) sessions for this repository run in containers that are
# reclaimed when idle and restored from a *filesystem checkpoint* on the next activity.
# The checkpoint can lag reality by days: git refs, the working tree, the venv, and any
# run caches all roll back together, silently. Three sessions in a row started on
# week-old git state without knowing it; one wrote a wrong history into a commit message
# before noticing (corrected in #119). GitHub is the durable truth -- this hook makes a
# session learn that before it does anything else.
#
# The guard prints a loud banner when the checkout is behind origin/main or its own
# upstream. It never blocks the session: a failed fetch is reported, not fatal.
set -uo pipefail

cd "$CLAUDE_PROJECT_DIR"

if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
    echo "=== session-start: git staleness guard (remote container) ==="
    if git fetch origin --quiet 2>/dev/null; then
        behind_main=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
        if [ "$behind_main" != "0" ] && [ "$behind_main" != "?" ]; then
            echo ""
            echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
            echo "!! STALE CHECKOUT: HEAD is $behind_main commit(s) behind origin/main."
            echo "!! This container restores from filesystem checkpoints after"
            echo "!! restarts and has repeatedly woken on old git state. Trust"
            echo "!! GitHub, not this working tree. Before ANY work:"
            echo "!!     git fetch origin && git checkout -B <branch> origin/main"
            echo "!! Local caches, venv and scratch files may also have rolled back."
            echo "!! Benchmarks and profiles taken before resyncing measure the"
            echo "!! wrong code."
            echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        else
            echo "checkout is current with origin/main ($(git rev-parse --short HEAD))"
        fi
        upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
        if [ -n "$upstream" ]; then
            behind_up=$(git rev-list --count HEAD.."$upstream" 2>/dev/null || echo 0)
            ahead_up=$(git rev-list --count "$upstream"..HEAD 2>/dev/null || echo 0)
            if [ "$behind_up" != "0" ]; then
                echo "!! also behind $upstream by $behind_up commit(s)"
            fi
            if [ "$ahead_up" != "0" ]; then
                echo "note: ahead of $upstream by $ahead_up commit(s) -- unpushed work from a previous life?"
            fi
        fi
    else
        echo "!! git fetch FAILED (network or credentials). Local refs may be stale;"
        echo "!! verify against GitHub before trusting anything in this tree."
    fi

    # Idempotent venv bootstrap, so tests can run in a genuinely fresh container.
    # A checkpoint-restored container usually still has .venv; a truly fresh one does not.
    if [ ! -x .venv/bin/python ]; then
        echo "=== session-start: no venv found, creating one ==="
        python3 -m venv .venv && .venv/bin/python -m pip install -q -e '.[test]' \
            && echo "venv ready: $(.venv/bin/python --version)"
    fi
fi

exit 0
