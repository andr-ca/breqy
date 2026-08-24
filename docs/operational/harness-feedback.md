# Harness Feedback Log

Operational friction observed while using agentharness skills and managed blocks in this repo.

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
