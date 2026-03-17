# system/orchestrator/auth/__init__.py
from __future__ import annotations
from system.orchestrator.auth.base import AuthFlowType, AuthProvider, DeviceCodeResponse
from system.orchestrator.auth.credential_store import CredentialStore
from system.orchestrator.auth.copilot_auth import GitHubCopilotAuth
from system.orchestrator.auth.gemini_auth import GeminiAuth
from system.orchestrator.auth.codex_auth import CodexAuth
from system.orchestrator.auth.claude_auth import ClaudeAuth
from system.orchestrator.auth.qwen_auth import QwenAuth

# Maps provider_name → class; used by main.py and AuthPanel to build provider instances
ALL_PROVIDER_CLASSES: dict[str, type[AuthProvider]] = {
    "claude": ClaudeAuth,
    "codex": CodexAuth,
    "gemini": GeminiAuth,
    "copilot": GitHubCopilotAuth,
    "qwen": QwenAuth,
}

__all__ = [
    "AuthFlowType", "AuthProvider", "DeviceCodeResponse", "CredentialStore",
    "GitHubCopilotAuth", "GeminiAuth", "CodexAuth", "ClaudeAuth", "QwenAuth",
    "ALL_PROVIDER_CLASSES",
]
