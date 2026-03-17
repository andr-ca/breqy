# Breqy Product Requirements Document

## 1. Product summary
Breqy is a Linux-first, always-running, multi-agent helper platform with:
- a daemon-like engine
- one or more agent processes
- modular channel adapters
- persistent sessions
- layered memory
- built-in tool execution
- policy-driven approvals and permissions

The first client is a separate TUI application that connects to the engine.

## 2. Primary target user
Initial target:
- the user personally
- on local Linux laptop first
- later on a Proxmox VM
- with no cloud dependency as a core requirement

The system should be intentionally designed so it can later support household or broader users.

## 3. Primary jobs to be done
Priority order for v1 product direction:
1. Chat across channels, starting with TUI
2. Perform system administration tasks
3. Remember context across sessions
4. Inspect/fix local services or Docker
5. Create/edit files and projects
6. Browse/search knowledge
7. Automate repetitive workflows
8. Run coding tasks on the machine

## 4. Core user-facing concepts

### 4.1 Engine
A long-running process that:
- stores sessions
- accepts channel connections
- routes messages
- spawns agents/subagents
- manages shared memory domains
- manages background work
- records events and state

### 4.2 Agent
A separate process with:
- persona/instructions
- tool permissions
- skill permissions
- model preferences
- autonomy policy
- private memory
- access to shared memory through permissioned tools
- its own logging configuration

Agents may participate in sessions, perform work, and spawn or receive delegated work.

### 4.3 Session
A persistent thread that:
- can involve one or more agents
- survives restarts and disconnects
- can be reattached from multiple channels
- stores conversation and operational state
- tracks tasks, approvals, artifacts, and events

### 4.4 Channel
A thin adapter that:
- authenticates to the engine
- converts channel-native events into a common runtime model
- can create, attach to, or resume sessions
- subscribes to session updates

### 4.5 Skill
A reusable global capability pack stored on disk, consisting of:
- instructions
- optional scripts
- references/examples/assets
- a manifest defining requirements and expectations

A skill shapes how work is done. It does not directly grant permissions.

### 4.6 Tool
An executable capability, such as:
- shell execution
- filesystem read/write/edit
- SSH
- Docker
- memory access
- browser/search
- git
- scheduling
- OS/package/service operations
- agent-management operations

Tools define what an agent can do. Permissions and approvals govern when and where they can do it.

## 5. Functional requirements

### 5.1 Engine and runtime
The system must:
- run as an always-on engine
- expose an engine port
- allow channels to connect only to the engine
- allow agents to connect/register with the engine
- use standard A2A protocol between engine and agents
- define a canonical typed A2A contract in Slice 1 for core messages and events
- support event-driven and streaming communication primarily
- also support request/response where appropriate
- require shared schema models for engine, agents, and channels so payloads are not interpreted heuristically

### 5.2 TUI client
The first channel must be a separate TUI app that:
- connects to the running engine
- lists sessions
- resumes existing sessions
- starts new sessions
- streams chat output
- renders messages and operational events from the canonical typed event contract
- shows agent participation
- shows inline approvals
- shows tool actions and status
- shows logs and events
- shows explicit task and todo state
- shows command output
- supports diff and patch review
- supports slash commands
- shows background task status

#### Core streamed event contracts
Slice 1 must define stable typed schemas for the core event types used by the engine, agents, and TUI. At minimum, this includes message events, task update events, approval events, control events, and tool invocation events. The TUI must render these from typed contracts rather than guessing from loosely shaped payloads.

#### Runner authentication panel
The orchestrator TUI must include a runner authentication panel that:
- displays all configured runners with their authentication status (authenticated / unauthenticated / unknown)
- allows the user to initiate authentication for any unauthenticated runner inline
- for device flow providers (Copilot, Codex, Gemini): displays the verification URL (as a clickable OSC8 hyperlink) and user code, then polls for completion in the background
- for PKCE providers (Claude): displays the authorization URL to open in a browser and provides an input field to paste the returned authorization code
- for API-key providers (Qwen): displays a masked key input field
- is reachable via the `breqy-orchestrator auth` CLI subcommand (standalone, outside the main loop TUI) and accessible from the main orchestrator TUI via a keybind

At minimum, a tool invocation event must include stable identifiers and rendering fields such as: event ID, session ID, task ID if present, agent ID, tool name, invocation ID, status, timestamps, approval state when relevant, a human-readable summary, structured arguments or an argument reference, and result or error references when available.

### 5.3 Session behavior
A session must:
- have a primary agent
- allow the primary agent to delegate or spawn subagents
- allow the user to request a specific agent via `@agent-name`
- allow UI-driven agent selection
- allow manual primary-agent transfer
- support engine-suggested transfer with user approval
- record transfers in session history
- preserve participants and audit trail

### 5.4 Control primitives
The system must support four user intervention modes.

#### Stop
- cancel active work as soon as possible
- may request confirmation depending on policy and risk

#### Stop and steer
- let the current atomic step finish safely
- then stop the active plan
- accept new direction and re-plan

#### Steer
- allow current in-flight step to complete
- then update context and plan
- continue without stopping the overall task

#### Circuit break
- hard kill all related agent processes immediately
- intended for stuck or unsafe situations
- record emergency termination in session state

### 5.5 Task planning
For non-trivial work:
- the system must maintain an explicit visible task and todo list
- engine owns canonical task state
- agents can propose and update task state
- user steering can modify task plan mid-flight

### 5.6 Background tasks
The system must support:
- session-linked jobs
- detached and background jobs linked back to sessions when applicable
- restart survival
- progress streaming into sessions
- cancellation
- retry and resume where feasible

### 5.7 Memory model
The system must support:
- **global memory** managed by engine
- **session memory** managed by engine
- **agent-private memory** managed by each agent

Recommended memory classes:
- profile and facts
- episodic history
- working memory
- artifacts and knowledge

Requirements:
- global memory should be more curated and harder to write
- session memory should capture operational continuity automatically
- agent-private memory should be isolated by default
- memory access should be tool-mediated and permissioned
- memory promotion from session to global should be explicit and policy-controlled

Promotion is defined as an explicit agent proposal plus user approval, or an automatic commit only when allowed by the active autonomy and policy configuration.

### 5.8 Persistence
The system must use:
- canonical DB storage for session, message, event, approval, and task metadata
- file-based summaries, logs, and artifacts alongside DB state
- first-class append-only event logging
- artifact references stored canonically in the DB

### 5.9 Approvals and permissions
Approvals:
- inline in the conversation flow
- low-friction by default
- per action
- with option to approve for the rest of the session

Autonomy:
- configurable from assistant-like to highly privileged
- adjustable at runtime from UI or TUI, temporarily for the current runtime or session

Permissions must support layered policy:
- global
- agent
- session
- most restrictive rule wins

#### Filesystem policy
Must support path-based controls with separate operation classes:
- read
- write/edit
- delete
- execute

Each can be governed by:
- whitelist
- approval-required paths
- blacklist

For v1, policy matching should use exact paths and directory-prefix rules only. Glob or wildcard pattern matching is out of scope for v1.

#### SSH policy
SSH is a tool with host policy:
- whitelist: connect without approval
- approve list: connect with approval, optionally extended to session
- blacklist: never connect

### 5.10 Agent definitions
Agent definitions must be file-based, source-of-truth folders containing:
- persona/system prompt
- tool permissions
- skill permissions
- memory locations
- model preferences
- autonomy policy
- subagent spawning rules
- startup hooks
- log level
- log location
- network port

Agents should auto-attempt connection to the engine on startup.

### 5.11 Skills
Skills must be:
- global
- file-based
- folder-scoped
- selectable per agent by allowlist or `*`

A skill may define:
- instructions
- required tools
- suggested tools
- incompatible tools
- required inputs
- expected outputs and artifacts
- safety and approval hints
- environment constraints
- success criteria
- validation and post-checks

Skills may only be invoked when the agent already has the required tools permitted by policy. Skill metadata may inform planning and validation, but it must not bypass or weaken tool-level permission checks.

### 5.12 Model and provider abstraction
The system must abstract model and provider integration so that any provider can be attached later.

v1 initial provider direction:
- All five orchestrator runners (Claude, Codex, Gemini, Copilot, Qwen) must support first-class authentication
- Providers with OAuth 2.0 device flow (GitHub Copilot, OpenAI Codex, Google Gemini) must use RFC 8628 device authorization grant
- Claude/Anthropic must use PKCE Authorization Code flow: the TUI displays a clickable URL; the user approves in a browser and pastes back the authorization code
- Qwen/DashScope has no OAuth flow; the TUI must accept an API key via a masked input field
- All credentials must be stored in the OS keyring via a `CredentialStore` abstraction; credentials must never be written to plain YAML or `.env` files by the system

The inference interface must support streaming output from day one, including token or chunk streaming and tool-call deltas sufficient for an interactive TUI experience.

Provider logic must be separated into:
- provider adapter
- auth provider (device flow, PKCE, or key entry per provider)
- credential store (keyring-backed)
- selection policy
- inference interface

### 5.13 Workspaces
For v1:
- a session may attach to one or more workspaces
- default scope is within attached workspace(s)
- broader filesystem access can be explicitly allowed
- architecture should leave room for future first-class project objects above sessions

### 5.14 Authentication
v1 must include real authentication between clients, channels, agents, and the engine. For Linux-first local mode, the preferred default is a local authenticated transport such as a UNIX domain socket with OS-level peer credential checks. Remote or network-accessible modes may use a different authenticated transport later, but must preserve the same engine trust boundary.

Additional user and account models are future work.

### 5.15 Configuration
Configuration must be:
- file-only in v1
- runtime changes temporary only
- mixed-format:
  - Markdown for long-form instructions
  - YAML for manifests and config

### 5.16 Failure handling
The system must:
- retry transient failures when appropriate
- checkpoint and resume where possible
- expose clear recovery suggestions
- auto-restart crashed agents where configured
- mark crashes and restarts in session state
- allow reattachment to same session context after restart

## 6. Non-functional requirements
Priority order:
1. reliability and restart safety
2. security and permission correctness
3. transparency and auditability
4. debuggability
5. extensibility and plugin friendliness
6. easy local setup
7. low latency and responsiveness
8. portability
9. testability
10. low resource usage

## 7. Vertical slices

### Slice 1
Must include:
- engine daemon
- one default agent
- separate TUI client
- create and resume persistent session
- streaming chat
- visible task list
- shell tool
- filesystem tool
- inline approvals
- stop, stop-and-steer, steer, and circuit break
- persistence of sessions and events across restart
- canonical typed event schemas for core runtime events

### Slice 2
Priority order:
1. session and global memory retrieval and promotion flow
2. SSH tool with whitelist, approve-list, and blacklist
3. agent spawning, delegation, and handoff
4. Docker and service inspection and basic remediation
5. artifact tracking for diffs, logs, and reports

## 8. v1 implementation risks to watch
- Agent process sprawl: session-level and runtime-level limits are required to prevent zombie processes, excessive ports, and runaway subagent creation.
- TUI responsiveness: input handling must remain responsive while events and tool output stream.
- SQLite write contention: WAL mode helps, but append-heavy workloads require careful write orchestration.
