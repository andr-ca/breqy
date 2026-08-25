# Harness Feedback Log

Operational friction observed while using agentharness skills and managed blocks in this repo.

## 2026-08-25 – safe-pr-merge.sh crashes (exit 128) when run from a consumer repo

**Recurrence key:** `safe-pr-merge-outside-repo-ls-files`

**Harness version:** `9cb9292eaf2612b62806b624a2f6fbb387797e42`

**Event class:** tool-output-mismatch

**Observed vs. inferred:** Directly observed (reproduced with `bash -x`)

**What happened:** Ran `bash ~/agentharness/tools/safe-pr-merge.sh 21` from inside the breqy checkout, per CLAUDE.md's guidance to prefer this tool over the manual merge checklist. It exited immediately with status 128 and zero output — no `[STEP]`/`[INFO]` lines at all, before even checking PR CI status.

**Root cause:** `warn_if_stale_script()` runs `git ls-files --full-name -- "${BASH_SOURCE[0]}"` against whatever repo the caller is standing in. When the script lives outside that repo's tree entirely (the documented cross-repo usage the header comment describes), `git ls-files` fails with `fatal: ... is outside repository` (exit 128). That failure is piped into `head -1` under `set -euo pipefail`, and `rel_path` is assigned via a bare `rel_path="$(...)"` (not `local rel_path="$(...)"` on one line), so `set -e` isn't masked and the whole script aborts before the staleness check's own `[ -z "$rel_path" ] && return 0` guard ever runs.

**Impact:** Blocking on first use — the tool CLAUDE.md recommends couldn't be used as documented at all until worked around.

**What agentharness should change:** See upstream issue.

**Corrective action taken:** Worked around by copying the script into breqy's gitignored `temp/` dir and running it from there (puts `${BASH_SOURCE[0]}` inside the repo, so `git ls-files` returns cleanly instead of erroring). Confirmed the rest of the script (CI check, review-comment wait, merge, post-merge CI poll) works correctly once past this point — used successfully to merge breqy PRs #20 and #21. Logged upstream as [#277](https://github.com/andr-ca/agentharness/issues/277).

**Severity:** blocking

**Workaround:** Copy the script into the target repo (e.g. its gitignored `temp/`) before running it, instead of invoking it from the harness checkout path directly.

## 2026-08-20 – Agent skipped worktree on dirty checkout during feature work

**Recurrence key:** `worktree-not-used-on-dirty-checkout`

**Harness version:** `9cb9292eaf2612b62806b624a2f6fbb387797e42`

**Event class:** mandate-violation

**Observed vs. inferred:** Directly observed (session transcript + git state)

**What happened:** A Cursor agent session implemented the Ollama ModelProvider feature in the main breqy checkout instead of an isolated git worktree. The session started on branch `chore/ruff-0.16-modernize` with ~100+ unrelated modified files, created `feat/ollama-provider` via in-place `git checkout -b`, and never confirmed branch strategy with the user before editing.

**Root cause:** Competing harness instructions were not ranked clearly enough for the agent to choose worktree isolation over a simple branch switch. `agents/core.instructions.md` requires branch confirmation before file ops; `GEMINI.md` and the `branching` skill recommend worktrees for significant/parallel work — but none of these mandates are hook-enforced, and the agent prioritized "create feature branch" without detecting that the working tree was heavily dirty.

**Impact:** Ollama changes are entangled with an unrelated ruff-modernization working tree (~127 `git status` lines). Commits/PRs risk mixing scopes. The repo already uses worktrees (`.worktrees/fix-tool-name-validation`, `.worktrees/reasoning-text-display`), so the convention was known locally but not followed.

**What agentharness should change:** See upstream issue (filed below).

**Corrective action taken:** Logged upstream as [#249](https://github.com/andr-ca/agentharness/issues/249).

**Severity:** degraded

**Workaround:** User can migrate Ollama changes to a new worktree from `develop` and cherry-pick/stage only Ollama paths.
