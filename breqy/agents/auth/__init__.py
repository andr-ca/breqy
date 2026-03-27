"""Public auth contracts for agent runtime integrations."""
from breqy.agents.auth.adapters import build_provider_auth_backends
from breqy.agents.auth.models import AuthBackend, AuthResult
from breqy.agents.auth.service import AuthService

__all__ = ["AuthBackend", "AuthResult", "AuthService", "build_provider_auth_backends"]
