# Phase 6 Spec Reference

Status: approved
Canonical spec: `docs/superpowers/specs/2026-03-22-phase-6-tools-design.md`

This phase reuses the already-approved Phase 6 design instead of regenerating a new planning spec.

Key approved scope:
- Native `shell` and `filesystem` tools share one `ToolExecutor` contract.
- `ToolService` centralizes policy, filesystem gating, approvals, persistence, and event emission.
- `ToolInvocation` persistence uses the existing storage/repository pattern.
- MCP support includes server config, bootstrap, discovery, invocation, and graceful failure handling.
- Memory semantics remain Phase 7 scope, but Phase 6 provides the MCP substrate needed for memory-backed tools.

Requirement coverage:
- TOOL-01: tool contract
- TOOL-02: tool registry
- TOOL-03: shell execution through policy-aware orchestration
- TOOL-04: filesystem execution through filesystem policy
- TOOL-05: MCP bootstrap and remote tool invocation
- TOOL-06: memory-tool-ready MCP substrate for later memory-domain work
