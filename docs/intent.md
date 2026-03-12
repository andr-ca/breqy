# Breqy Intent

## 1. Why Breqy exists
Breqy exists to act as an always-on, modular, multi-agent technical counterpart that can help the user perform real work across local and remote Linux environments. It is designed to reduce friction between thought and execution: chatting, planning, inspecting systems, operating tools, making controlled changes, and preserving useful memory over time.

The system is intentionally built as a personal-first runtime that can later evolve into a household or broader multi-user platform, without depending on cloud deployment as a core assumption.

## 2. Core problem
Today, technical work is fragmented across terminals, chats, scripts, notes, browser tabs, and ad hoc automation. Existing assistants are often:
- tied to a single interface
- not always running
- weak at durable memory
- weak at safe tool execution
- poor at interruption and steering
- not modular enough for multiple agent personas and roles

Breqy aims to solve this by combining:
- an always-running engine
- persistent sessions
- separable agent processes
- pluggable channels
- controlled tool use
- layered memory
- explicit user intervention controls

## 3. Product vision
Breqy is a persistent agent runtime with a strong default persona and support for specialized subagents. It should feel like a capable second-self: sharp, calm, high-agency, slightly disruptive, and trustworthy.

It should be able to:
- stay alive independently of any UI
- be reached from multiple channels
- preserve context and task continuity across sessions and reconnects
- use tools to perform real work
- delegate to other agents when appropriate
- remain interruptible, steerable, auditable, and safe

## 4. Guiding principles
1. **Always-on core**  
   The engine persists independently of any client.

2. **Channels are adapters**  
   TUI, WebUI, Telegram, WhatsApp, and future channels are thin clients over one shared runtime.

3. **Sessions are first-class**  
   Sessions survive restarts, disconnects, and reconnects from multiple channels.

4. **Agents are real runtime participants**  
   Agents are separate processes with their own memory, permissions, and configuration.

5. **Least privilege by default**  
   Permissions, approvals, and scope boundaries must be explicit and configurable.

6. **Interruptibility is mandatory**  
   The user must always be able to stop, stop-and-steer, steer, or circuit-break work.

7. **Memory must be layered**  
   Global, session, and agent-private memory must be separated and governed clearly.

8. **Configuration is source-controlled and inspectable**  
   File-based configuration is the source of truth.

9. **Implementation should stay loosely coupled**  
   Storage, model providers, and other infrastructure must be abstracted behind interfaces and dependency injection.

10. **Linux-first, but portable by intention**  
    v1 targets Linux desktop/server/VM/SSH, while avoiding accidental design choices that block Windows later.

## 5. Breqy default persona
Breqy is the product and display name of the default primary agent. The technical identifier is `breqy`.

### Persona traits
- sharp
- calm
- high-agency
- slightly disruptive
- trustworthy

### Communication style
- balanced
- concise by default
- structured when executing
- transparent about risk and uncertainty
- lightly dry, not jokey

### Behavioral expectations
- moves work forward
- produces visible plans for non-trivial work
- respects policy boundaries
- adapts quickly when interrupted or redirected
- avoids fluff, fake certainty, and reckless autonomy

### Failure-mode tone
When work fails, Breqy should state facts, impact, likely cause, and recovery path directly. It should not dramatize failure, anthropomorphize it, or hide the next step behind vague apologies.

## 6. v1 success criteria
Breqy v1 is successful if:
1. The user can start the engine, connect from the TUI, and reliably create and resume persistent sessions.
2. The default agent can perform approved Linux admin and filesystem tasks with clear visibility and control.
3. Memory survives restarts and helps carry relevant context across sessions.
4. The user can stop, stop-and-steer, steer, or circuit-break work safely and predictably.
5. The system can spawn or delegate to subagents with clear session visibility and audit trail. This is a v1 capability target, but not a Slice 1 requirement.

## 7. Non-goals for v1
Out of scope for v1:
- cloud-native deployment as a core path
- multi-user accounts and permissions
- per-user/channel identity mapping
- rich Web UI
- production-grade Telegram/WhatsApp support
- MCP integration beyond extension points
- persistent config editing from UI
- advanced tracing/metrics stack
- agent-local skill libraries

Windows is not core for v1, but is a fast follower.
