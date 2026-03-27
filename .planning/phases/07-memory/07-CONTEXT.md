# Phase 7: Memory - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 7 delivers persistent, scoped memory for Breqy: engine-owned session and global memory, agent-private memory isolation contracts, mandatory tool-mediated access through a memory interface, and promotion flow from session memory to global memory with policy and approval control.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `breqy/tools/mcp.py` already provides the MCP registration boundary that Phase 7 can reuse for a mandatory memory tool surface.
- `breqy/policy/evaluator.py` and `breqy/policy/approval.py` already provide the core decision and approval primitives needed for promotion control.
- `breqy/storage/` and `breqy/storage/sqlite/` already follow the repository + SQLite implementation pattern that memory persistence should match.
- `breqy/engine/server.py`, `breqy/engine/event_bus.py`, and `breqy/engine/event_writer.py` already provide the engine-side orchestration points for mediated access and durable event history.

### Established Patterns
- Engine-owned state is modeled with pydantic domain structs, repository interfaces, and SQLite implementations injected via constructors.
- Policy-sensitive behavior is centralized in orchestration services rather than embedded inside low-level executors.
- Phase 6 established a mandatory tool-mediated path for controlled operations, with engine-owned canonical state behind that interface.
- Tests are organized as focused unit coverage first, with integration-style engine checks where phase wiring matters.

### Integration Points
- Memory persistence will integrate into `breqy/storage/interfaces.py` and matching SQLite modules.
- Memory orchestration will likely compose into engine services alongside the existing tool and approval flow.
- The memory tool surface must integrate with the Phase 6 MCP/tool boundary without making external MCP ownership mandatory for canonical memory state.
- Agent-private memory contracts must line up with the later agent runtime work in `breqy/agents/`.

</code_context>

<specifics>
## Specific Ideas

- Use a hybrid mandatory MCP shape: memory access stays tool-mediated, but engine-owned canonical memory remains the real source of truth for session and global domains.
- Keep the promotion workflow as a distinct first-class path rather than treating promotion as an ordinary write.

</specifics>

<deferred>
## Deferred Ideas

- Full agent runtime wiring depth for private memory beyond the Phase 7 contract and isolation boundary.
- Rich semantic ranking, summarization heuristics, and automation-heavy retrieval/promotion behavior.
- Distributed or externalized canonical memory backends.

</deferred>
