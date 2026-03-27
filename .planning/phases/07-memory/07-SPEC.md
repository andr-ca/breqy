# Phase 7 Spec Reference

Status: drafted
Canonical spec: `docs/superpowers/specs/2026-03-23-phase-7-memory-design.md`

This phase uses an engine-owned canonical memory architecture with a mandatory MCP-shaped mediated access surface.

Key scope:
- engine-owned session memory
- engine-owned global memory
- agent-private memory contract and isolation behavior
- promotion from session to global through policy and approval control
- mandatory tool-mediated memory access
