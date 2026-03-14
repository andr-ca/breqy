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
