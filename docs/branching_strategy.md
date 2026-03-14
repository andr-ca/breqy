# Breqy Branching Strategy

## Purpose

This document defines how branches are created, named, protected, and merged in Breqy.  
Goals:

- keep `main` stable and releasable
- prevent direct commits to protected branches
- support parallel work with short-lived topic branches
- require evidence-based merges (tests, review, documentation)

This strategy is aligned with:

- `agents/core.instructions.md` (branch safety, TDD, documentation, coverage)
- `docs/ai_delivery_approach_v_1.md` (orchestrated, evidence-based delivery)

## Protected Branches

The following branches are protected and must never receive direct commits:

- `main`
- `master`
- `develop` (if present)
- `sandbox*`
- `sit*`

Rules:

- work must happen on a topic branch
- merge into a protected branch only through Pull Request
- no force-push to protected branches

## Branch Types and Naming

Use short kebab-case names with clear intent for descriptive slugs (the part after the prefix):

- `feat/<short-kebab>`
- `fix/<short-kebab>`
- `hotfix/<short-kebab>`
- `docs/<short-kebab>`
- `chore/<short-kebab>`
- `refactor/<short-kebab>`
- `test/<short-kebab>`
- `release/<version-or-date>` (where `<version-or-date>` is a semantic version such as `1.2.3` or a date such as `2024-03-01` — this identifier is not kebab-case and is explicitly allowed)

Recommended format when task IDs exist:

- `feat/brq-144-session-resume-flow`
- `fix/brq-201-reconnect-duplication`
- `docs/branching-strategy`
- `release/1.2.3`

## Branch Source and Target Rules

Current repository default is a single long-lived trunk (`main`).

| Branch type | Source branch | PR target |
|---|---|---|
| `feat/*`, `fix/*`, `docs/*`, `chore/*`, `refactor/*`, `test/*` | `main` | `main` |
| `hotfix/*` | `main` | `main` |
| `release/*` | `main` | `main` |

If the team introduces `develop` later, use this scaled model:

| Branch type | Source branch | PR target |
|---|---|---|
| `feat/*`, `fix/*`, `docs/*`, `chore/*`, `refactor/*`, `test/*` | `develop` | `develop` |
| `hotfix/*` | `main` | `main` (then back-merge to `develop`) |
| `release/*` | `develop` (release cut) | `main` (then back-merge to `develop`) |

## Standard Workflow (Topic Branch)

1. Confirm branch strategy before file changes.
2. Create topic branch from the correct source branch.
3. Implement using TDD (`RED -> GREEN -> REFACTOR`).
4. Run required validation (tests, lint, type checks, coverage as applicable).
5. Update docs for behavior or architecture changes.
6. Open PR to the correct target branch.
7. Resolve review findings and rerun validation.
8. Merge after approvals and required checks pass.
9. Delete branch after merge.

## Pull Request Requirements

A PR is mergeable only when all applicable gates pass:

- branch name follows convention
- correct source/target branch pair
- tests pass
- coverage thresholds are satisfied:
  - business logic: 100%
  - overall project: 80% minimum
- required documentation updates are included
- checker/tester evidence exists for non-trivial tasks
- human approval is present

## Merge Policy

- default merge method: **squash merge**
- commit messages should follow conventional commits (`feat:`, `fix:`, `docs:`, etc.)
- keep PRs small and focused on a single task/slice
- do not mix unrelated refactors with feature work

## Hotfix Workflow

Use only for urgent production-impacting fixes.

1. Create `hotfix/<short-kebab>` from `main`.
2. Reproduce with a failing test first.
3. Implement minimal fix and validate.
4. Open PR to `main` with high-priority review.
5. After merge, tag release if needed.
6. If `develop` exists, back-merge/cherry-pick the hotfix.

## Release Branch Workflow (Optional)

Use only when a stabilization window is needed.

1. Cut `release/<version-or-date>` from the approved integration point.
2. Allow only:
   - release blockers
   - test fixes
   - docs/release notes
3. Run full regression and QA validation.
4. Merge release branch to `main`.
5. Tag the release.
6. Back-merge to `develop` if it exists.

## Freshness and Conflict Policy

- rebase or merge from source branch before requesting final review
- if branch is stale or conflict-prone, sync and rerun validation
- use `--force-with-lease` only on your own non-protected branch

## Examples

```bash
# feature work
git checkout main
git pull --ff-only
git checkout -b feat/brq-144-session-resume-flow

# docs work
git checkout main
git pull --ff-only
git checkout -b docs/branching-strategy

# hotfix work
git checkout main
git pull --ff-only
git checkout -b hotfix/session-resume-crash
```

## Governance

This branching strategy is a living document.  
Update it when delivery mode changes (for example, adopting `develop`, introducing release trains, or adding stricter CI gate requirements).
