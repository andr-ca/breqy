# Phase 7: Memory - Research

**Researched:** 2026-03-23
**Domain:** Engine-owned canonical memory with MCP-shaped tool mediation
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Memory Ownership and MCP Boundary
- Session and global memory remain engine-owned canonical stores so restart safety and canonical policy enforcement stay inside the engine.
- MCP participation is mandatory in the user-facing memory path, but as an adapter surface over engine memory services rather than the source of truth.
- Agent-private memory uses a separate agent-owned store boundary with explicit isolation rules instead of collapsing into the engine-owned domains.
- Phase 7 should introduce stable `MemoryRepository` and `VectorIndex` interfaces, with a simple initial retrieval implementation if needed.

### Promotion, Policy, and Approval
- Phase 7 promotion scope is session -> global only.
- Promotion always goes through policy plus approval/autonomy evaluation before any global write occurs.
- Ordinary reads and session writes are policy-controlled, while approvals are reserved mainly for promotion-sensitive actions.
- Denied or deferred promotions must preserve the original session memory while preventing the global write.

### Record Shape and Retrieval Behavior
- Canonical memory records should be metadata-first structured records with scope, owner, session linkage, source, timestamps, tags, and content payload.
- Retrieval should use deterministic scoped filtering first and `VectorIndex` second behind an interface boundary.
- Session continuity should come from explicit tool-mediated writes plus engine-owned summaries/checkpoints, not passive scraping of arbitrary DB state.
- Task, approval, and artifact continuity should be represented as canonical metadata links inside memory records.

### Private Memory Integration and Phase Boundary
- Phase 7 should define the agent-private memory contract, store boundary, and isolation tests now, while leaving full agent runtime orchestration depth to Phase 8.
- Session and global memory must prove restart survival in Phase 7; private memory must prove contract and isolation behavior even if full process restart restore is later.
- Direct memory access should be blocked by architecture and tests: supported access goes through mediated services and tool paths rather than agent-side repository reach-in.
- Advanced retrieval tuning, auto-promotion heuristics, richer summarization, distributed backends, and full private-memory runtime wiring are explicitly deferred.

### the agent's Discretion
- The exact canonical record model may use one table plus typed metadata or a small set of focused persistence tables, as long as memory scope, owner, linkage, and promotion state remain explicit and testable.
- The first `VectorIndex` implementation may be intentionally minimal if the interface and scoped retrieval behavior are stable and verifiable.

### Deferred Ideas (OUT OF SCOPE)
- Full agent runtime wiring depth for private memory beyond the Phase 7 contract and isolation boundary.
- Rich semantic ranking, summarization heuristics, and automation-heavy retrieval/promotion behavior.
- Distributed or externalized canonical memory backends.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | Session memory is stored and managed by the engine (thread continuity, task state, approvals, artifact refs) | Engine-owned `MemoryService`, SQLite `MemoryRepository`, checkpoint/summary records, link metadata, restart-survival tests |
| MEM-02 | Global memory is stored and managed by the engine (durable profile, facts, promoted lessons) | Separate global scope in canonical records, promotion workflow, cross-session read tests |
| MEM-03 | Agent-private memory is isolated per agent process | Explicit `AgentPrivateMemoryStore` contract, no engine repo injection to agents, isolation tests by agent ID/store boundary |
| MEM-04 | Memory access is tool-mediated and permissioned (via MCP memory tool) | MCP-shaped memory tool names and schemas, `ToolService` outer gate, `MemoryService` inner policy checks |
| MEM-05 | Memory promotion from session to global requires explicit agent proposal + user approval (or autonomous commit when autonomy policy allows) | First-class promotion path, approval/autonomy evaluation before global write, denial preserves session record |
</phase_requirements>

## Summary

Phase 7 should add an engine-side `MemoryService` as the sole canonical owner of session and global memory, backed by a new `MemoryRepository` plus a minimal `VectorIndex` abstraction. This matches the repo's established architecture: domain models + repository interfaces + SQLite implementations + engine-composed orchestration services. It also matches the project docs, which explicitly assign session/global memory to the engine and agent-private memory to agent processes.

The user-facing path should be MCP-shaped but not MCP-owned. The cleanest fit is to register local tool executors with MCP-style names and schemas (for example `mcp.memory.n--search`, `mcp.memory.n--write`, `mcp.memory.n--promote`) that delegate to engine memory services. That preserves the mandatory tool-mediated contract established in Phase 6, keeps `ToolService` as the audit/policy/approval gateway, and avoids making an external MCP server the source of truth.

**Primary recommendation:** Use one engine-owned metadata-first `memory_records` store, one minimal `VectorIndex` interface with a no-op/keyword-first Phase 7 implementation, and a distinct promotion workflow that writes to global memory only after policy + approval/autonomy checks succeed.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Pydantic | 2.12.5 | Typed memory records, tool payloads, promotion requests | Already standard across Breqy domain/config/event models |
| aiosqlite | 0.22.1 | Async SQLite repos for canonical memory persistence | Matches existing storage layer and WAL-based engine persistence |
| MCP Tools spec | 2025-06-18 | User-facing memory tool contract (`tools/list`, `tools/call`) | Required by context; fits existing `MCPToolAdapter` pattern |
| structlog | 25.5.0 | Structured logging for memory writes/promotions/failures | Already standard in engine/policy/tools modules |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-ulid | 3.1.0 | Memory IDs / promotion IDs / link IDs | For new durable domain objects |
| pytest | 9.0.2 | Unit/integration coverage for memory repos/services | All new memory behavior |
| pytest-asyncio | 1.3.0 | Async repo/service tests | Async SQLite and engine service paths |
| pytest-cov | 7.1.0 | Coverage enforcement | Before phase completion |
| ruff | 0.15.7 | Lint/format | Standard repo hygiene |
| mypy | 1.19.1 | Interface safety around repo/index contracts | New abstractions and DI wiring |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process MCP-shaped adapter over engine service | Real external MCP memory server | More protocol realism, but wrong ownership boundary for canonical state in Phase 7 |
| Single metadata-first `memory_records` table + JSON fields | Several highly normalized memory tables | Better ad hoc SQL, but more migration and mapping complexity for v1 |
| Minimal `VectorIndex` implementation | External vector DB now | Better retrieval quality, but adds premature infra and violates current phase constraints |

**Installation:**
```bash
python3 -m pip install -e ".[dev]"
```

**Version verification:**
- `pydantic` 2.12.5 — published 2025-11-26
- `aiosqlite` 0.22.1 — published 2025-12-23
- `structlog` 25.5.0 — published 2025-10-27
- `pytest` 9.0.2 — published 2025-12-06
- `pytest-asyncio` 1.3.0 — published 2025-11-10
- `pytest-cov` 7.1.0 — published 2026-03-21
- `ruff` 0.15.7 — published 2026-03-19
- `mypy` 1.19.1 — published 2025-12-15
- `python-ulid` 3.1.0 — published 2025-08-18

## Architecture Patterns

### Recommended Project Structure
```text
breqy/
├── memory/
│   ├── __init__.py           # exports MemoryService, VectorIndex, contracts
│   ├── service.py            # engine-owned orchestration for read/write/promote
│   ├── index.py              # VectorIndex ABC + minimal phase-7 impl
│   ├── contracts.py          # AgentPrivateMemoryStore contract + DTOs
│   └── policies.py           # memory-specific resource naming/helpers
├── storage/
│   ├── interfaces.py         # add MemoryRepository, VectorIndex refs
│   └── sqlite/
│       ├── migrations.py     # add memory tables/indexes
│       └── memory_repo.py    # SQLite implementation
├── tools/
│   ├── memory.py             # MCP-shaped local adapters/executors
│   └── __init__.py           # export memory tools
└── domain/
    ├── models.py             # MemoryRecord / MemoryPromotion models
    ├── enums.py              # MemoryScope / MemorySource / PromotionStatus
    └── events.py             # memory.* typed events
```

### Pattern 1: Engine-owned canonical memory service
**What:** One engine-side orchestration service owns reads/writes/promotions for session and global memory.
**When to use:** For any canonical memory operation that must survive restart, obey policy, and appear in the event log.
**Example:**
```python
# Source: existing repo pattern in breqy/tools/service.py and breqy/engine/server.py
result = await tool_service.execute_tool(
    session_id=session_id,
    agent_id=agent_id,
    tool_name="mcp.memory.n--write",
    arguments={"scope": "session", "content": "..."},
)

# Inside the memory tool adapter:
await memory_service.write_session_record(...)
```

### Pattern 2: MCP-shaped local memory adapter
**What:** Register memory operations in `ToolRegistry` under MCP-style names and schemas, but delegate locally to engine services.
**When to use:** For the mandatory user-facing memory path.
**Example:**
```json
// Source: MCP tools spec https://modelcontextprotocol.io/specification/2025-06-18/server/tools
{
  "method": "tools/call",
  "params": {
    "name": "search_memory",
    "arguments": {"scope": "session", "query": "approval history"}
  }
}
```

### Pattern 3: Promotion as a first-class workflow
**What:** Promotion is not a normal write; it is a proposal + evaluation + optional approval + global commit.
**When to use:** Session -> global only.
**Example:**
```python
# Source: project constraint + ApprovalService pattern in breqy/policy/approval.py
promotion = await memory_service.propose_promotion(record_id=record_id, agent_id=agent_id)
decision = await memory_service.evaluate_promotion(promotion)
if decision.requires_approval:
    await approval_service.request_approval(...)
```

### Pattern 4: Deterministic filtering before vector lookup
**What:** Scope, owner, session, tags, and promotion status filter first; `VectorIndex` is secondary.
**When to use:** Every retrieval path.
**Example:**
```python
# Source: Phase 7 context decision
records = await memory_repo.search(
    scope="session",
    session_id=session_id,
    agent_id=agent_id,
    tags=["approval", "artifact"],
)
ranked = await vector_index.rank(query="recent approvals", records=records)
```

### Pattern 5: Agent-private memory isolation by store boundary
**What:** Private memory has its own contract and store boundary; engine canonical repos do not serve it directly.
**When to use:** Any agent-private reads/writes.
**Example:**
```python
# Source: project.instructions.md + Phase 7 context
class AgentPrivateMemoryStore(Protocol):
    async def read(self, agent_id: str, query: str) -> list[PrivateMemoryRecord]: ...
    async def write(self, agent_id: str, payload: PrivateMemoryRecord) -> str: ...
```

### Anti-Patterns to Avoid
- **Direct repository reach-in from agents:** Agents should not receive SQLite connections or `MemoryRepository` instances.
- **Vector-first search:** Do not run embeddings/index lookup before scope and owner filtering.
- **Treating promotion as ordinary global write:** This bypasses approval/autonomy requirements.
- **External MCP server as canonical memory owner:** Violates engine ownership and restart-safety constraints.
- **Passive continuity from random DB scraping:** Continuity should come from explicit records, summaries, and links.

## Likely File Touch Points

| Path | Change Type | Why |
|------|-------------|-----|
| `breqy/storage/interfaces.py` | Update | Add `MemoryRepository` and reference `VectorIndex` |
| `breqy/storage/sqlite/migrations.py` | Update | Add memory DDL and schema version bump |
| `breqy/domain/models.py` | Update | Add `MemoryRecord`, `MemoryLink`, `MemoryPromotion` models |
| `breqy/domain/enums.py` | Update | Add memory scope/source/promotion enums |
| `breqy/domain/events.py` | Update | Add typed memory write/promotion events |
| `breqy/tools/__init__.py` | Update | Export memory tool executors/adapters |
| `breqy/engine/server.py` | Update | Compose and register memory tool executors/services |
| `breqy/policy/evaluator.py` | Maybe update | Only if memory-specific resource naming helpers need tighter matching |
| `breqy/policy/approval.py` | Reuse | Promotion approval path should reuse existing service, not fork it |
| `breqy/tools/service.py` | Reuse or small update | Outer tool gate stays here; memory executor can do inner scope checks |
| `breqy/memory/service.py` | New | Canonical orchestration for read/write/promote |
| `breqy/memory/index.py` | New | `VectorIndex` ABC + minimal Phase 7 implementation |
| `breqy/memory/contracts.py` | New | Agent-private isolation contract |
| `breqy/storage/sqlite/memory_repo.py` | New | SQLite adapter |
| `breqy/tools/memory.py` | New | MCP-shaped local memory tool executors |
| `tests/unit/storage/test_memory_repo.py` | New | Repo round-trip and filtering |
| `tests/unit/memory/test_service.py` | New | Promotion/policy/isolation behavior |
| `tests/unit/tools/test_memory_tool.py` | New | MCP-shaped adapter contract |
| `tests/integration/memory/test_restart_survival.py` | New | Session/global restart survival |

**Current repo note:** `breqy/agents/**/*.py` is effectively absent in this worktree, so private-memory runtime wiring should stay contract-only in Phase 7 and leave process integration to Phase 8.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Human approval flow for promotion | A second custom approval state machine | `ApprovalService` | Existing pending/timeout/session-grant logic already fits promotion gating |
| Tool mediation | A special memory-only execution path | `ToolRegistry` + `ToolService` | Preserves audit events, policy checks, and one execution contract |
| MCP surface | Ad hoc JSON blobs or bespoke RPC | MCP-shaped tool schemas and names | Keeps Phase 7 aligned with Phase 6 MCP boundary and official tools model |
| Retrieval interface | Hard-coded vector backend calls in business logic | `VectorIndex` abstraction | Keeps scoring/backends replaceable and allows minimal Phase 7 implementation |
| Canonical continuity links | Implicit joins across tasks/approvals/artifacts only | Explicit metadata links on records | Easier auditability and deterministic retrieval |

**Key insight:** The hard part here is not storage; it is preserving one canonical permissioned path. Reusing existing tool, approval, and event patterns is more important than adding a powerful retrieval backend.

## Common Pitfalls

### Pitfall 1: Letting the memory tool own canonical state
**What goes wrong:** The adapter becomes the source of truth instead of the engine.
**Why it happens:** MCP makes remote tools feel like data owners.
**How to avoid:** Keep `MemoryService` + `MemoryRepository` inside the engine; tool adapter only translates arguments/results.
**Warning signs:** Canonical writes happen in `breqy/tools/memory.py` without an engine service call.

### Pitfall 2: Policy only at the outer tool layer
**What goes wrong:** All memory actions share one coarse `tool:<name>` rule.
**Why it happens:** `ToolService` already evaluates tool policy, so it is tempting to stop there.
**How to avoid:** Add inner memory action resources such as `memory:session:read`, `memory:session:write`, `memory:global:promote`.
**Warning signs:** Promotion and ordinary session writes are governed by identical policy decisions.

### Pitfall 3: Private memory isolation implemented as a filter on shared canonical rows
**What goes wrong:** Agent A and B can leak via query bugs or missing predicates.
**Why it happens:** Shared tables are simpler initially.
**How to avoid:** Separate private-memory contract/store boundary; test cross-agent denial explicitly.
**Warning signs:** Agent-private queries hit the same repo/service as session/global without a distinct interface.

### Pitfall 4: Retrieval ranking before scope reduction
**What goes wrong:** Wrong-scope memory outranks correct-scope records.
**Why it happens:** Vector search is treated as primary retrieval.
**How to avoid:** Scope/owner/session/tag filtering first, ranking second.
**Warning signs:** Retrieval path starts with embeddings or fuzzy search before scope checks.

### Pitfall 5: No typed memory events
**What goes wrong:** Memory writes and promotions become hard to audit and hard for TUI/log consumers to render later.
**Why it happens:** Existing `EventType` lacks memory-specific entries.
**How to avoid:** Add typed memory events in Phase 7.
**Warning signs:** Memory changes are only visible by inspecting tables directly.

### Pitfall 6: Phase 7 trying to finish Phase 8
**What goes wrong:** Agent runtime wiring balloons scope.
**Why it happens:** Private memory invites immediate process-level integration.
**How to avoid:** Deliver the private-memory contract and isolation tests now; defer full runtime hookup.
**Warning signs:** Phase 7 starts depending on full agent loop/spawner orchestration.

## Code Examples

Verified patterns from official and project sources:

### MCP tool call shape
```json
// Source: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_memory",
    "arguments": {
      "scope": "session",
      "query": "approval history"
    }
  }
}
```

### Existing engine tool gateway pattern
```python
// Source: /home/andrey/projects/breqy/.worktrees/exp-full-build/breqy/tools/service.py
decision = self._policy_evaluator.evaluate(
    resource=f"tool:{tool_name}",
    agent_id=agent_id,
    session_id=session_id,
)
if decision.action == PolicyAction.REQUIRE_APPROVAL:
    approval_id = await self._approval_service.request_approval(...)
```

### Existing SQLite repo mapping pattern
```python
// Source: /home/andrey/projects/breqy/.worktrees/exp-full-build/breqy/storage/sqlite/session_repo.py
await self._conn.execute(
    """INSERT INTO sessions
       (id, status, primary_agent_id, workspace_paths, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?)""",
    (...),
)
await self._conn.commit()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Bypass tools and query stores directly | Tool-mediated access with explicit human-in-the-loop safety | Formalized in MCP tools spec 2025-06-18 | Memory should look like a tool, not a hidden side channel |
| Treat memory as raw conversation log | Metadata-first records + summaries/checkpoints + optional retrieval ranking | Current Breqy architecture docs | Better restart continuity and explicit links to tasks/approvals/artifacts |
| Make vector search primary | Deterministic scope filtering first, vector index second | Locked in Phase 7 context | Safer isolation and more predictable results |

**Deprecated/outdated:**
- Using an external MCP memory server as canonical owner for session/global memory in Phase 7
- Relying on passive DB scraping for continuity instead of explicit memory records

## Open Questions

1. **One memory table or one table plus link table?**
   - What we know: Context allows either one metadata-rich table or a small focused set.
   - What's unclear: Whether explicit link rows materially improve query clarity for task/approval/artifact refs in v1.
   - Recommendation: Start with one `memory_records` table plus JSON link metadata unless query pain appears during implementation.

2. **How many MCP-shaped memory tools should Phase 7 expose?**
   - What we know: Reads, writes, and promotion are mandatory; promotion is distinct.
   - What's unclear: Whether session/global/private reads should be one `search` tool with scoped args or separate tool names.
   - Recommendation: Keep Phase 7 minimal with three tool names: `search`, `write`, `promote`; encode scope in validated arguments.

3. **Do we add memory event types now or rely only on DB state?**
   - What we know: Architecture expects memory event families; current enums do not have them.
   - What's unclear: Exact event surface needed for later TUI rendering.
   - Recommendation: Add at least `memory.recorded`, `memory.promotion_requested`, `memory.promoted`, and `memory.promotion_denied` in Phase 7.

## Validation Architecture

> `.planning/config.json` was not present in this worktree, so `workflow.nyquist_validation` is treated as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` |
| Quick run command | `python3 -m pytest tests/unit/storage tests/unit/tools tests/unit/engine -q` |
| Full suite command | `python3 -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | Session memory persists continuity records across restart | integration | `python3 -m pytest tests/integration/memory/test_restart_survival.py -q` | ❌ Wave 0 |
| MEM-02 | Global memory written once is readable in a different session | integration | `python3 -m pytest tests/integration/memory/test_global_memory.py -q` | ❌ Wave 0 |
| MEM-03 | Agent-private memory is unreadable across agents | unit | `python3 -m pytest tests/unit/memory/test_private_store.py -q` | ❌ Wave 0 |
| MEM-04 | Memory access only works through MCP-shaped tool path and policy checks | unit/integration | `python3 -m pytest tests/unit/tools/test_memory_tool.py tests/unit/memory/test_service.py -q` | ❌ Wave 0 |
| MEM-05 | Promotion requires approval/autonomy evaluation before global write | unit | `python3 -m pytest tests/unit/memory/test_promotion_flow.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/unit/memory tests/unit/tools/test_memory_tool.py tests/unit/storage/test_memory_repo.py -q`
- **Per wave merge:** `python3 -m pytest tests/unit/storage tests/unit/tools tests/unit/engine tests/unit/memory -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/storage/test_memory_repo.py` — covers MEM-01, MEM-02 filtering and round-trip
- [ ] `tests/unit/memory/test_service.py` — covers MEM-04, MEM-05 orchestration
- [ ] `tests/unit/memory/test_private_store.py` — covers MEM-03 isolation contract
- [ ] `tests/unit/tools/test_memory_tool.py` — covers MCP-shaped adapter inputs/outputs
- [ ] `tests/integration/memory/test_restart_survival.py` — covers MEM-01 restart survival
- [ ] `tests/integration/memory/test_global_memory.py` — covers MEM-02 cross-session reads
- [ ] Framework install: `python3 -m pip install -e ".[dev]"` — current worktree cannot import `aiosqlite`, so pytest collection is not runnable yet

## Sources

### Primary (HIGH confidence)
- Local project architecture: `/home/andrey/projects/breqy/.worktrees/exp-full-build/docs/architecture.md` — engine vs agent memory ownership, event writer, storage boundaries
- Local project requirements: `/home/andrey/projects/breqy/.worktrees/exp-full-build/.planning/REQUIREMENTS.md` — MEM-01 through MEM-05
- Local phase context: `/home/andrey/projects/breqy/.worktrees/exp-full-build/.planning/phases/07-memory/07-CONTEXT.md` — locked decisions and scope boundaries
- Local implementation patterns: `breqy/tools/service.py`, `breqy/tools/mcp.py`, `breqy/storage/interfaces.py`, `breqy/storage/sqlite/*.py`, `breqy/engine/server.py`, `breqy/policy/approval.py`
- MCP official spec: https://modelcontextprotocol.io/specification/2025-06-18/server/tools — tool discovery/call contract and human-in-the-loop safety guidance
- MCP official spec overview: https://modelcontextprotocol.io/specification/2025-06-18 — trust/safety and capability framing

### Secondary (MEDIUM confidence)
- aiosqlite project metadata/docs via PyPI: https://pypi.org/pypi/aiosqlite/json — confirms async SQLite positioning and current version
- PyPI package metadata used for current version verification:
  - https://pypi.org/pypi/pydantic/json
  - https://pypi.org/pypi/aiosqlite/json
  - https://pypi.org/pypi/structlog/json
  - https://pypi.org/pypi/pytest/json
  - https://pypi.org/pypi/pytest-asyncio/json
  - https://pypi.org/pypi/pytest-cov/json
  - https://pypi.org/pypi/ruff/json
  - https://pypi.org/pypi/mypy/json
  - https://pypi.org/pypi/python-ulid/json

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - core repo stack is clear and verified, but Phase 7 vector implementation remains intentionally minimal/discretionary
- Architecture: HIGH - strongly constrained by local project docs, current code patterns, and Phase 7 context
- Pitfalls: MEDIUM - well supported by current architecture and MCP guidance, but some depend on planned memory event/resource naming not yet implemented

**Research date:** 2026-03-23
**Valid until:** 2026-04-22
