# Phase 7 Memory Design

## Goal

Deliver persistent, scoped memory for Breqy with engine-owned canonical session and global memory, a mandatory tool-mediated memory interface, promotion from session to global under policy and approval control, and a defined contract for agent-private memory isolation.

## Scope

Phase 7 covers:
- engine-owned session memory
- engine-owned global memory
- a mandatory MCP-shaped memory tool surface over engine memory services
- session-to-global promotion workflow
- repository and retrieval abstractions needed for stable persistence and scoped lookup
- agent-private memory contract and isolation behavior

Phase 7 explicitly does not cover:
- full agent runtime wiring depth for private memory
- advanced ranking and semantic retrieval tuning
- auto-promotion heuristics beyond explicit policy/autonomy decisions
- distributed or external canonical memory backends

## Architecture

### Canonical ownership

Session memory and global memory remain engine-owned canonical state. This preserves restart safety, canonical policy enforcement, and one durable source of truth. The memory tool surface is mandatory, but it operates as an adapter over engine services rather than as an independent owner of state.

### Core components

- `MemoryRepository`
  - canonical persistence boundary for session and global memory records
  - supports create, query, and promotion state updates
- `VectorIndex`
  - retrieval ranking boundary behind an interface
  - may use a deliberately minimal Phase 7 implementation
- `MemoryService`
  - engine-owned orchestration for read, write, summarize/checkpoint, and promote workflows
  - enforces scope rules and delegates to approval and policy logic where needed
- memory tool executors/adapters
  - exposed through the normal tool path
  - use MCP-shaped naming and validated argument schemas
  - delegate to `MemoryService`
- `AgentPrivateMemoryStore`
  - contract boundary for agent-owned private memory
  - isolated by agent identity
  - fully runtime-integrated behavior is deferred to Phase 8

## Data model

### Canonical memory record

Phase 7 should use metadata-first records containing:
- record id
- scope (`session` or `global`)
- owner / originating agent id
- session id when applicable
- source / record type
- tags
- content payload
- explicit links to related task, approval, artifact, or event ids
- created and updated timestamps
- promotion state metadata where applicable

The physical persistence shape may be one metadata-rich table or a very small focused set of tables, but scope, linkage, and promotion state must remain explicit and testable.

### Promotion model

Promotion is a first-class workflow, not an ordinary write. Phase 7 only supports session-to-global promotion. A promotion record or explicit promotion status must preserve:
- source session memory record
- proposing agent id
- approval correlation
- final outcome (`pending`, `approved`, `denied`)

## Access model

### Tool-mediated path

All supported memory access goes through the memory tool surface. For Phase 7, that tool surface is mandatory and MCP-shaped, but locally backed by engine memory services. Suggested operation set:
- `search`
- `write`
- `promote`

Scope is expressed via validated arguments instead of separate tool names per domain.

### Operation and scope matrix

| Operation | `session` | `global` | `private` |
|-----------|-----------|----------|-----------|
| `search` | allowed through the engine-mediated memory tool path | allowed through the engine-mediated memory tool path with global policy checks | allowed only through the mediated private-memory path delegating to `AgentPrivateMemoryStore` |
| `write` | allowed through the engine-mediated memory tool path with policy checks | rejected as a direct write path in Phase 7 | allowed only through the mediated private-memory path delegating to `AgentPrivateMemoryStore` |
| `promote` | allowed only as a session source operation | not a direct write target; global memory is created only by approved promotion | unsupported in Phase 7 |

Direct `write(scope="global")` must be rejected. Global memory enters the canonical store in Phase 7 only through the promotion workflow.

### Private-memory routing

Private-scope tool calls remain tool-mediated, but they do not route through the engine-owned canonical session/global store. Instead, the mediated memory path dispatches private-domain reads and writes to an `AgentPrivateMemoryStore` contract keyed by agent identity.

### Policy and approval

- outer tool access remains gated by `ToolService`
- memory-specific actions also need inner resource checks so promotion is not treated the same as ordinary reads or writes
- memory-specific resource names should be explicit, such as `memory:session:read`, `memory:session:write`, `memory:global:read`, `memory:private:read`, `memory:private:write`, and `memory:session:promote`
- reads and session writes are policy-controlled
- promotion always goes through policy plus approval/autonomy evaluation before any global write occurs
- denied or deferred promotions preserve the session record and block the global write

### Direct-access rejection

Phase 7 must treat direct repository or database access by agents as rejected architecture, not just an unsupported convention. The design should enforce this by never exposing `MemoryRepository` or SQLite handles to agent-facing paths and by adding negative tests for rejected direct global writes and unsupported direct-access patterns.

## Retrieval behavior

Retrieval is deterministic-first:
1. filter by scope, owner, session, tags, and any required links
2. optionally rank the already-allowed candidate set via `VectorIndex`

Phase 7 should not make vector retrieval the primary selector. Scoped filtering must happen first to preserve isolation and predictable behavior.

## Session continuity

Session continuity should come from explicit memory writes plus engine-owned summaries or checkpoints. Phase 7 should not depend on passive mining of arbitrary DB state as the primary continuity mechanism. Memory records should carry canonical links to tasks, approvals, and artifacts so continuity survives restart in a structured way.

Phase 7 should include a lightweight checkpoint or summary path so continuity is not limited to ad hoc note writes.

## Agent-private memory

Agent-private memory remains agent-owned. Phase 7 should define the contract and tests proving isolation semantics, but deeper runtime/process wiring belongs to Phase 8. The engine must not treat private memory as interchangeable with canonical session/global memory.

## Events and auditability

Phase 7 should add typed memory events so later TUI and audit flows can render memory operations without table inspection. Minimum event coverage should include:
- memory record created or updated
- promotion requested
- promotion approved/promoted
- promotion denied

Those events must be emitted through the existing engine event path so they are persisted by the event writer, not merely defined as domain types.

## Testing strategy

### Unit coverage

- repository round-trip and scoped query behavior
- memory service reads, writes, and promotion orchestration
- private memory isolation contract behavior
- memory tool adapter argument validation and result shaping
- checkpoint or summary creation behavior for session continuity
- negative tests for rejected direct global writes and unsupported direct-access paths

### Integration coverage

- session memory survives restart
- global memory written in one session is visible in another
- promotion requires approval/autonomy decision before global write
- mediated access path remains the supported path for memory operations
- memory events reach the durable engine event path

## Deferred work

- full agent runtime private-memory wiring
- advanced retrieval ranking and richer summarization heuristics
- autonomous promotion heuristics beyond active policy/autonomy rules
- distributed memory backends or external canonical stores
