## CORE INSTRUCTIONS FOR ANY WORK

## IMPORTANT — READ THESE FIRST

1. [Project Instructions](./project.instructions.md) — project-specific requirements
2. [Python Development Instructions](./python.instructions.md) — modular design, DI, patterns
3. [TDD Instructions](./tdd.instructions.md) — mandatory Red-Green-Refactor workflow

---

## 🔴 CRITICAL: BRANCH CHECK IS THE FIRST STEP (NO EXCEPTIONS)

Before making any change, creating any file, or writing any code:

1. Run:

```bash
git status -sb
git branch -a
```

2. Ask the user immediately:

```
I see we're on branch [current-branch]. Should we:
1) Continue on this branch?
2) Create a new feature branch (feat/...)?
3) Create a new fix branch (fix/...)?
4) Create a different type of branch?
```

3. Wait for user response before any file operations.

4. If on trunk (`main`, `master`, `develop`, `sandbox*`, `sit*`):
   - NEVER commit directly.
   - MUST create a new branch/worktree first.

5. Only after branch confirmation:
   - Proceed with TDD workflow.
   - Create/modify files.

Why this is mandatory:
- Committing to trunk causes avoidable conflicts and unsafe history.
- Working on the wrong branch wastes review and integration time.
- Branch confirmation enforces safe, auditable workflow.

---

## 🚨 TDD IS MANDATORY (NON-NEGOTIABLE)

Do not write implementation first.

Required cycle for every feature/fix/refactor:
1. **RED**: Write a failing test first.
2. **GREEN**: Write the minimum implementation to pass.
3. **REFACTOR**: Improve code while keeping tests green.

Enforcement rules:
- NEVER skip the failing-test step.
- NEVER defer tests to “later”.
- Even “small” changes require tests first.

Per-change order of operations:
1. Add test cases (`test: ...`).
2. Run tests and verify they fail for the correct reason.
3. Implement minimal code (`feat:` / `fix:`).
4. Run tests and verify they pass.
5. Refactor safely (`refactor:`).

If tempted to skip TDD due to time pressure: stop and continue with TDD anyway.

---

## 📚 DOCUMENTATION IS MANDATORY

All code changes must be documented.

After completing implementation and tests:
1. Identify affected documentation.
2. Update existing docs or create new docs in `docs/`.
3. Update `CHANGES.md` with what changed and why.
4. Verify examples, schemas, and links are current.

Minimum documentation scope (as applicable):
- API docs
- Architecture docs
- Setup/deployment docs
- Developer/user guidance
- Feature-specific docs

Rule: undocumented code is incomplete code.

---

## 📊 TEST COVERAGE REQUIREMENTS (MANDATORY)

Coverage thresholds:

| Code Category | Statement | Branch | Function | Line |
|---|---:|---:|---:|---:|
| Business Logic (services, validators, utils, rules, shared logic) | 100% | 100% | 100% | 100% |
| Components / UI Logic | 80% | 80% | 80% | 80% |
| Overall Project | 80% | 80% | 80% | 80% |

Business logic includes (not limited to):
- `**/services/**`
- `**/validators/**`
- `**/utils/**`
- `**/business_rules/**`
- `**/shared/**`
- Any file with calculations, transformations, or business decisions

Coverage workflow:
1. Write tests first.
2. Implement code.
3. Run coverage.
4. Add tests for uncovered lines.
5. Repeat until thresholds are met.

If thresholds are not met: stop and add tests before commit/PR.

---

## 🧪 MIGRATION DISCIPLINE (MANDATORY FOR SCHEMA/PERSISTENCE CHANGES)

When changing database schema, persistence models, migration code, or durable approval/state formats:

1. Write at least one failing test against a **pre-migration schema snapshot**.
2. Cover both:
   - **fresh database creation**
   - **upgrade from an older schema**
3. For upgrade tests, explicitly cover:
   - legacy-row backfill behavior
   - duplicate-row handling / deduplication
   - idempotent re-runs of the migration
4. Never create a uniqueness constraint or unique index **before** dedup/backfill logic has run.
5. If a migration changes scope or ownership semantics (for example session vs forever), add a test for each scope outcome.

Rule: a migration is incomplete until both fresh-install and upgrade-path tests pass.

---

## 📌 GITIGNORE CHECK (BEFORE FIRST COMMIT)

Always verify `.gitignore` exists and is correct before committing.
Do not commit dependencies, build artifacts, or secrets.

---

## 📋 BRANCH NAMING CONVENTION

Use topic branches only:
- `feat/<short-kebab>`
- `fix/<short-kebab>`
- `hotfix/<short-kebab>`
- `chore/<short-kebab>`
- `docs/<short-kebab>`
- `refactor/<short-kebab>`
- `test/<short-kebab>`

---

## 🔧 GIT WORKFLOW ENFORCEMENT

Before any git operation (branching, worktrees, commit, push, PR):
1. Re-read the "🔴 CRITICAL: BRANCH CHECK IS THE FIRST STEP (NO EXCEPTIONS)" section above.
2. Follow that section fully.
3. Do not skip user prompting and branch confirmation.

Key safety rules:
- Never bypass branch safety checks.
- Prefer worktrees for larger feature work when appropriate.
- Never commit directly to protected trunk branches.

### PR scope hygiene (mandatory before push / PR update)

Before pushing a branch or updating a PR, run both:

```bash
git log --oneline <base>..HEAD
git diff --name-only <base>...HEAD
```

Confirm:
- every commit belongs to the intended PR scope
- every changed file belongs to the intended PR scope

If unrelated commits or files are present:
- rebase, cherry-pick, or otherwise clean the branch **before** requesting review
- do not leave reviewers to sort out mixed scope

Rule: every PR must have a clean, reviewable scope.

---

## 🌲 WORKTREE WORKFLOW (MANDATORY WHEN ISOLATION IS NEEDED)

Use a dedicated worktree when:
- work is non-trivial and may take multiple commits
- tasks are parallelized across branches
- the current workspace has unrelated local changes
- the user explicitly asks for isolated execution

Directory selection order (required):
1. Use `.worktrees/` if it exists.
2. Else use `worktrees/` if it exists.
3. Else check `CLAUDE.md` for worktree location guidance.
4. Else ask the user where to create worktrees.

Safety checks before creating a project-local worktree (`.worktrees/` or `worktrees/`):
1. Verify `.gitignore` includes the chosen directory entry (`.worktrees/` or `worktrees/`).
2. If missing, add it immediately before creating the worktree.
3. Keep this ignore change tracked in the same branch unless the user asks otherwise.

Required creation sequence:
1. Confirm branch strategy with the user (from branch-check section).
2. Create the branch/worktree with `git worktree add <path> -b <branch-name> <start-point>`.
3. `cd` into the worktree and run project setup commands if needed.
4. Run baseline validation (at minimum the project’s quick test command) and report result.
5. Continue implementation only after the baseline state is known.

Worktree hygiene:
- Do not edit files in the original workspace after starting isolated work unless intentionally coordinating both.
- Report the full worktree path in progress updates.
- Remove finished worktrees only after merge/close and user confirmation.

---

## 🔴 TDD CHECKPOINT (BEFORE IMPLEMENTATION)

Confirm all answers are “yes”:
1. Have I written the test file?
2. Does the test fail for the right reason?
3. Am I writing the minimum code to pass?

If any answer is “no”: stop and return to RED.

---

## 📚 DOCUMENTATION CHECKPOINT (AFTER IMPLEMENTATION)

Confirm all answers are “yes”:
1. Did I update relevant docs in `docs/`?
2. Did I document new feature/API behavior?
3. Are examples/schemas current?
4. Did I update `CHANGES.md`?

If any answer is “no”: stop and update docs.

---

## 🔎 REVIEW-COMMENT HANDLING (MANDATORY)

When review feedback arrives:

1. Classify each comment before changing code:
   - invariant / correctness bug
   - security / hardening concern
   - UX/backend contract mismatch
   - PR hygiene / scope issue
   - non-actionable / not applicable
2. For invariant, security, or migration comments:
   - add a failing test first
   - then implement the fix
3. For UX/backend mismatches:
   - fix the **contract** first, not just the wording or UI, unless the contract is intentionally unsupported
4. For PR hygiene comments:
   - clean branch history or diff scope instead of explaining away unrelated changes
5. When replying:
   - say whether the concern was technically valid
   - say what changed, or why no change was needed

Rule: do not treat review comments as purely social artifacts; treat them as testable engineering claims.

---

## ✅ FINAL CHECKLIST (BEFORE COMMIT)

1. Branch Safety
   - [ ] Correct branch (not protected trunk)
   - [ ] User-confirmed branch strategy

2. TDD Complete
   - [ ] Tests written first
   - [ ] Fail-first validated
   - [ ] All tests pass
   - [ ] Coverage thresholds met

3. Documentation Complete
   - [ ] Relevant docs updated in `docs/`
   - [ ] `CHANGES.md` updated
   - [ ] Links/examples validated

4. Code Quality
   - [ ] Clean, maintainable code
   - [ ] No debug leftovers
   - [ ] Proper error handling

5. Commit Quality
   - [ ] Conventional commit message
   - [ ] Clear scope and rationale

Only commit after all boxes are checked.

---

## EXECUTION LEDGER RULES (AGENT ARTIFACTS)

- Treat JSONL plan/review artifacts as authoritative execution ledger.
- Keep artifact references portable (repo-relative), never local absolute paths.
- Enforce explicit branch-confirmation and structured evidence in prompts.
- Record major technical decisions early (scheduler, migrations, provider).
