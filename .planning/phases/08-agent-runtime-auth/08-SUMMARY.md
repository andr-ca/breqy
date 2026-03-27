# Phase 8 Summary

Status: complete
Completed: 2026-03-24

Phase 8 delivered the default agent runtime and provider-auth slice for the `exp-full-build` worktree run.

Completed outcomes:
- Added Phase 8 agent config fields and default `agents/breqy/` definition loading.
- Added Phase 8 domain event and runtime/auth model contracts.
- Added `CredentialStore` and Breqy-native auth service contracts.
- Added provider auth adapters for Copilot, Codex, Claude, Gemini, and Qwen.
- Added Breqy-owned provider execution adapters with class-based orchestrator runner reuse.
- Added canonical top-level `skills/` support and a validated `SkillLoader`.
- Restored missing `EngineConfig.policy_rules` and `EngineConfig.filesystem_policies` so daemon-composed defaults remain compatible with the engine runtime.
- Added agent-owned delegated private-memory runtime support with owning-agent enforcement and typed result translation.
- Implemented engine-side agent registration, disconnect cleanup, canonical user-turn persistence before dispatch, targeted `AgentWorkRequestedEvent` routing, transport-only tool/private-memory handoff, and assistant-turn persistence on final runtime messages.
- Implemented the initial `breqy/agents/runtime.py` loop and daemon hook for default-agent startup.
- Added end-to-end integration coverage for runtime round trips and delegated private-memory flow.

Notable closure decisions:
- Provider and default model selection stay `agent.yaml`-driven in Phase 8.
- `skill_permissions` remains a list field and wildcard form stays `["*"]`.
- `AgentWorkRequestedEvent` is the runtime dispatch trigger.
- `ToolExecutionRequestedEvent`, `ToolExecutionResultEvent`, `PrivateMemoryOperationRequestedEvent`, and `PrivateMemoryOperationResultEvent` are transport-only handoff events by default, not extra durable audit events.
- Provider subprocess auth isolation must block ambient CLI/session reuse, not only inject tokens.

Primary sources:
- `docs/superpowers/specs/2026-03-23-phase-8-agent-runtime-auth-design.md`
- `docs/superpowers/plans/2026-03-23-phase-8-agent-runtime-auth.md`

Primary files touched during closure:
- `breqy/config/models.py`
- `breqy/config/loader.py`
- `breqy/domain/enums.py`
- `breqy/domain/events.py`
- `breqy/domain/models.py`
- `breqy/agents/credentials.py`
- `breqy/agents/auth/`
- `breqy/agents/providers/`
- `breqy/agents/skills.py`
- `breqy/agents/private_memory.py`
- `breqy/agents/runtime.py`
- `breqy/a2a/server.py`
- `breqy/engine/agent_registry.py`
- `breqy/engine/server.py`
- `breqy/engine/daemon.py`
- `agents/breqy/agent.yaml`
- `agents/breqy/persona.md`
- `skills/`
- `docs/architecture.md`
- `CHANGES.md`

Next phase:
- Phase 9 - Sessions and Control
