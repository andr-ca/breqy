# Phase 7 Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build persistent engine-owned memory with a mandatory tool-mediated memory interface, promotion control, and private-memory isolation contracts.

**Architecture:** Add canonical memory domain models, storage interfaces, SQLite persistence, engine memory orchestration, MCP-shaped local memory tool executors, and focused verification for restart survival and promotion control. Keep session/global memory engine-owned, treat MCP as adapter shape rather than ownership boundary, and defer full private-memory runtime wiring.

**Tech Stack:** Python 3.12+, pydantic v2, aiosqlite, structlog, pytest, pytest-asyncio

---

## File Structure

- Create: `breqy/memory/__init__.py`
- Create: `breqy/memory/service.py`
- Create: `breqy/memory/index.py`
- Create: `breqy/memory/contracts.py`
- Create: `breqy/tools/memory.py`
- Create: `breqy/storage/sqlite/memory_repo.py`
- Modify: `breqy/domain/enums.py`
- Modify: `breqy/domain/models.py`
- Modify: `breqy/domain/events.py`
- Modify: `breqy/storage/interfaces.py`
- Modify: `breqy/storage/sqlite/migrations.py`
- Modify: `breqy/storage/sqlite/__init__.py`
- Modify: `breqy/tools/__init__.py`
- Modify: `breqy/tools/service.py`
- Modify: `breqy/engine/server.py`
- Modify: `breqy/engine/daemon.py`
- Modify: `docs/architecture.md`
- Modify: `CHANGES.md`
- Modify: `.planning/phases/07-memory/07-SUMMARY.md`
- Modify: `.planning/phases/07-memory/07-VERIFICATION.md`
- Test: `tests/unit/storage/test_migrations.py`
- Test: `tests/unit/storage/test_memory_repo.py`
- Test: `tests/unit/memory/test_service.py`
- Test: `tests/unit/memory/test_private_store.py`
- Test: `tests/unit/tools/test_memory_tool.py`
- Test: `tests/unit/engine/test_server.py`
- Test: `tests/unit/engine/test_daemon.py`
- Test: `tests/integration/memory/test_restart_survival.py`
- Test: `tests/integration/memory/test_global_memory.py`

### Task 1: Define memory domain contracts

**Files:**
- Modify: `breqy/domain/enums.py`
- Modify: `breqy/domain/models.py`
- Modify: `breqy/domain/events.py`
- Test: `tests/unit/domain/test_models.py`
- Test: `tests/unit/domain/test_events.py`

- [ ] **Step 1: Write failing domain tests for memory enums, models, and events**
- [ ] **Step 2: Run targeted tests and verify they fail for missing memory types**
- [ ] **Step 3: Add minimal memory enums, record/promotion models, and typed memory events**
- [ ] **Step 4: Run targeted tests and verify they pass**

### Task 2: Add memory storage abstractions and SQLite persistence

**Files:**
- Modify: `breqy/storage/interfaces.py`
- Modify: `breqy/storage/sqlite/migrations.py`
- Create: `breqy/storage/sqlite/memory_repo.py`
- Modify: `breqy/storage/sqlite/__init__.py`
- Test: `tests/unit/storage/test_migrations.py`
- Test: `tests/unit/storage/test_memory_repo.py`

- [ ] **Step 1: Write failing repository and migration tests for session/global memory round-trip, scoped query, promotion-state updates, and new memory DDL**
- [ ] **Step 2: Run `uv run pytest tests/unit/storage/test_memory_repo.py tests/unit/storage/test_migrations.py -v` and verify failure is for missing interfaces, DDL, or implementation**
- [ ] **Step 3: Add `MemoryRepository` abstraction, memory DDL, and minimal SQLite implementation with explicit task, approval, artifact, event, and promotion metadata support**
- [ ] **Step 4: Run `uv run pytest tests/unit/storage/test_memory_repo.py tests/unit/storage/test_migrations.py -v` and verify pass**

### Task 3: Add retrieval and private-memory contracts

**Files:**
- Create: `breqy/memory/index.py`
- Create: `breqy/memory/contracts.py`
- Test: `tests/unit/memory/test_private_store.py`

- [ ] **Step 1: Write failing tests for minimal `VectorIndex` behavior and private-memory isolation contract expectations**
- [ ] **Step 2: Run `uv run pytest tests/unit/memory/test_private_store.py -v` and verify failure**
- [ ] **Step 3: Add minimal `VectorIndex` boundary and `AgentPrivateMemoryStore` contract/test doubles**
- [ ] **Step 4: Re-run targeted tests and verify pass**

### Task 4: Implement engine-owned memory orchestration

**Files:**
- Create: `breqy/memory/service.py`
- Modify: `breqy/tools/service.py`
- Test: `tests/unit/memory/test_service.py`

- [ ] **Step 1: Write failing service tests for session write, scoped read, checkpoint or summary creation, rejected direct global writes, promotion approval/autonomy flow, denied promotion, and deterministic filter-before-rank behavior**
- [ ] **Step 2: Run `uv run pytest tests/unit/memory/test_service.py -v` and verify failure**
- [ ] **Step 3: Implement minimal `MemoryService` orchestration using repository, vector boundary, explicit memory resource checks, approval/policy integration, and explicit linkage/promotion metadata handling**
- [ ] **Step 4: Re-run `uv run pytest tests/unit/memory/test_service.py -v` and verify pass**

### Task 5: Add mandatory tool-mediated memory interface

**Files:**
- Create: `breqy/tools/memory.py`
- Modify: `breqy/tools/__init__.py`
- Test: `tests/unit/tools/test_memory_tool.py`

- [ ] **Step 1: Write failing tests for MCP-shaped local memory tool operations (`search`, `write`, `promote`) including rejected `write(scope="global")` and private-scope routing**
- [ ] **Step 2: Run `uv run pytest tests/unit/tools/test_memory_tool.py -v` and verify failure**
- [ ] **Step 3: Implement local tool executors/adapters that delegate to `MemoryService` and expose stable tool names/schemas**
- [ ] **Step 4: Re-run `uv run pytest tests/unit/tools/test_memory_tool.py -v` and verify pass**

### Task 6: Compose memory into engine runtime

**Files:**
- Create: `breqy/memory/__init__.py`
- Modify: `breqy/engine/server.py`
- Modify: `breqy/engine/daemon.py`
- Test: `tests/unit/engine/test_server.py`
- Test: `tests/unit/engine/test_daemon.py`

- [ ] **Step 1: Write failing engine tests proving daemon/server compose memory services, register memory tools in the default engine path, and persist memory events through the engine event flow**
- [ ] **Step 2: Run `uv run pytest tests/unit/engine/test_server.py tests/unit/engine/test_daemon.py -v` and verify failure**
- [ ] **Step 3: Implement minimal engine composition and default registry wiring for memory services/tools**
- [ ] **Step 4: Re-run the targeted engine tests and verify pass**

### Task 7: Verify restart survival and cross-session global reads

**Files:**
- Test: `tests/integration/memory/test_restart_survival.py`
- Test: `tests/integration/memory/test_global_memory.py`

- [ ] **Step 1: Write failing integration tests for session-memory restart survival and global-memory cross-session visibility**
- [ ] **Step 2: Run `uv run pytest tests/integration/memory/test_restart_survival.py tests/integration/memory/test_global_memory.py -v` and verify failure**
- [ ] **Step 3: Fill any minimal persistence/composition gaps needed to satisfy the integration flows**
- [ ] **Step 4: Re-run the integration tests and verify pass**

### Task 8: Verify mediated access and promotion policy behavior

**Files:**
- Test: `tests/integration/memory/test_mediated_access.py`
- Test: `tests/unit/memory/test_service.py`
- Test: `tests/unit/tools/test_memory_tool.py`

- [ ] **Step 1: Write failing tests for mediated-access-only behavior, direct-access rejection, and autonomy-allowed versus approval-required promotion outcomes**
- [ ] **Step 2: Run `uv run pytest tests/integration/memory/test_mediated_access.py tests/unit/memory/test_service.py tests/unit/tools/test_memory_tool.py -v` and verify failure**
- [ ] **Step 3: Implement any minimal gaps needed to satisfy mediated-access and promotion-decision behavior**
- [ ] **Step 4: Re-run `uv run pytest tests/integration/memory/test_mediated_access.py tests/unit/memory/test_service.py tests/unit/tools/test_memory_tool.py -v` and verify pass, including promotion-decision behavior**

### Task 9: Documentation and phase verification

**Files:**
- Modify: `docs/architecture.md`
- Modify: `CHANGES.md`
- Test: `tests/unit/storage/test_migrations.py`
- Test: `tests/unit/storage/test_memory_repo.py`
- Test: `tests/unit/memory/test_service.py`
- Test: `tests/unit/memory/test_private_store.py`
- Test: `tests/unit/tools/test_memory_tool.py`
- Test: `tests/unit/engine/test_server.py`
- Test: `tests/unit/engine/test_daemon.py`
- Test: `tests/integration/memory/test_restart_survival.py`
- Test: `tests/integration/memory/test_global_memory.py`
- Test: `tests/integration/memory/test_mediated_access.py`

- [ ] **Step 1: Update architecture and changelog docs for the Phase 7 memory model and mediated access path**
- [ ] **Step 2: Run `uv run pytest tests/unit/storage/test_migrations.py tests/unit/storage/test_memory_repo.py tests/unit/memory/test_service.py tests/unit/memory/test_private_store.py tests/unit/tools/test_memory_tool.py tests/unit/engine/test_server.py tests/unit/engine/test_daemon.py tests/integration/memory/test_restart_survival.py tests/integration/memory/test_global_memory.py tests/integration/memory/test_mediated_access.py -v` and verify pass**
- [ ] **Step 3: Run `uv run pytest -q` and verify full project pass**
- [ ] **Step 4: Run explicit coverage verification for the new memory business-logic paths and confirm the repo thresholds are met**
- [ ] **Step 5: Record the exact coverage command and result in `.planning/phases/07-memory/07-VERIFICATION.md`**
- [ ] **Step 5: Capture phase summary and verification artifacts in `.planning/phases/07-memory/`**
