export type HomepageSection = {
  id: string;
  eyebrow: string;
  title: string;
  copy: string;
};

export type ProductClaim = {
  name: string;
  status: "available" | "deferred";
  copy: string;
};

export const siteMeta = {
  name: "Breqy",
  launchStage: "Early Access",
  productionUrl: "https://breqy.com",
  preProductionUrl: "https://develop.breqy.com",
  description:
    "Breqy is a Linux-first, always-on multi-agent AI runtime for persistent sessions, controlled tool use, and auditable local work.",
  positioning:
    "A public marketing/docs website for the local-first Breqy runtime, separate from the product runtime itself.",
  repositoryUrl: "https://github.com/malandr/breqy",
} as const;

export const deploymentTargets = {
  develop: {
    environment: "pre-prod",
    url: "https://develop.breqy.com",
    projectVariable: "CLOUDFLARE_PAGES_PROJECT_PREPROD",
  },
  main: {
    environment: "production",
    url: "https://breqy.com",
    projectVariable: "CLOUDFLARE_PAGES_PROJECT_PROD",
  },
} as const;

export const homepageSections: HomepageSection[] = [
  {
    id: "hero",
    eyebrow: "Early Access",
    title: "Always-on AI runtime for local Linux work.",
    copy: "Breqy keeps an engine alive independently of any UI, preserves sessions, and lets agent processes do real work with policy and approvals in the loop.",
  },
  {
    id: "runtime",
    eyebrow: "Engine",
    title: "The durable core stays running.",
    copy: "The engine owns sessions, event history, policy, approvals, task state, and memory boundaries. Clients can disconnect without throwing away the thread.",
  },
  {
    id: "agents",
    eyebrow: "Agents",
    title: "Separate processes, explicit permissions.",
    copy: "Agents connect over typed A2A messages, keep their own runtime identity, and execute only the tools policy allows.",
  },
  {
    id: "sessions",
    eyebrow: "Continuity",
    title: "Sessions survive restarts and reconnects.",
    copy: "Breqy treats sessions as first-class operational threads with messages, tasks, participants, approvals, and durable events.",
  },
  {
    id: "approvals",
    eyebrow: "Safety",
    title: "Tool use is visible before it matters.",
    copy: "Shell, filesystem, browser, and memory tools are routed through explicit policy checks, reusable approval grants, and the event log.",
  },
  {
    id: "control",
    eyebrow: "Steering",
    title: "Stop, steer, or circuit-break.",
    copy: "The user can interrupt work, let an atomic step finish before redirecting, or hard-stop unsafe execution.",
  },
  {
    id: "architecture",
    eyebrow: "Topology",
    title: "Engine, agents, and channels stay separate.",
    copy: "TUI now and future channels later connect only to the engine. Agents register separately and exchange canonical typed envelopes.",
  },
  {
    id: "quickstart",
    eyebrow: "Install",
    title: "Start the daemon, attach the TUI, keep working.",
    copy: "The early-access path is intentionally local: install the Python package, start the engine, launch the Textual TUI, then approve tool work as needed.",
  },
  {
    id: "roadmap",
    eyebrow: "Scope",
    title: "Slice 1 first, no mystery claims.",
    copy: "Breqy is focused on the local engine, TUI, sessions, approvals, and native tools before expanding into richer channels and remote operations.",
  },
  {
    id: "source",
    eyebrow: "Source",
    title: "Built in the open, with auditability as a design constraint.",
    copy: "The website reflects the same discipline as the runtime: branch-gated delivery, testable contracts, docs, and explicit operational boundaries.",
  },
];

export const productClaims: ProductClaim[] = [
  {
    name: "Engine daemon",
    status: "available",
    copy: "Available in Slice 1: long-running engine process with durable sessions and typed event routing.",
  },
  {
    name: "Textual TUI",
    status: "available",
    copy: "Available in Slice 1: terminal UI for sessions, chat, tasks, approvals, controls, and logs.",
  },
  {
    name: "Shell and filesystem tools",
    status: "available",
    copy: "Available in Slice 1 through policy-mediated local tool execution and approval events.",
  },
  {
    name: "Rich WebUI channel",
    status: "deferred",
    copy: "Future Slice 2 work; this website is marketing/docs, not the browser channel itself.",
  },
  {
    name: "SSH operations",
    status: "deferred",
    copy: "Deferred remote-operation capability planned after the local Slice 1 runtime is stable.",
  },
  {
    name: "Docker inspection workflows",
    status: "deferred",
    copy: "Planned for Slice 2 and later; outside the current Early Access capability set.",
  },
  {
    name: "Agent delegation depth",
    status: "deferred",
    copy: "Future multi-agent expansion beyond the Slice 1 default runtime path.",
  },
];

export const quickstartCommands = [
  {
    label: "Install dependencies",
    command: "uv sync",
  },
  {
    label: "Start the engine",
    command: "breqy engine start",
  },
  {
    label: "Open the TUI",
    command: "breqy tui",
  },
  {
    label: "Authenticate a runner",
    command: "breqy auth copilot",
  },
] as const;

export const architectureNodes = [
  {
    name: "breqy-engine",
    role: "Owns sessions, event log, memory boundaries, approvals, task state, and routing.",
  },
  {
    name: "agent processes",
    role: "Register over A2A, reason within granted constraints, and request mediated tool execution.",
  },
  {
    name: "channel apps",
    role: "Thin clients such as the Textual TUI. Future channels attach to the same runtime.",
  },
] as const;