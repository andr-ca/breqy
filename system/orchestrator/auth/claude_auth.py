# system/orchestrator/auth/claude_auth.py
from __future__ import annotations
import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode, urlparse, parse_qs
import httpx
from system.orchestrator.auth.base import PkceProvider
from system.orchestrator.auth.credential_store import CredentialStore

# Public OAuth app credentials for Claude/Anthropic
# These are public application identifiers used in PKCE flow
_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
_AUTH_URL = "https://claude.ai/oauth/authorize"
_TOKEN_URL = "https://api.anthropic.com/oauth/token"
_SCOPES = "org:create_api_key user:profile"


class ClaudeAuth(PkceProvider):
    """Claude/Anthropic authentication via PKCE Authorization Code flow.

    The user visits a URL in their browser, approves, then pastes the
    authorization code back into the TUI.
    """

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store
        self._code_verifier: str | None = None
        self._state: str | None = None

    @property
    def provider_name(self) -> str:
        return "claude"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def get_auth_url(self) -> str:
        """Generate PKCE challenge, store verifier, return authorization URL."""
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self._code_verifier = verifier
        self._state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": _CLIENT_ID,
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": self._state,
        }
        return f"{_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, raw_input: str) -> None:
        """Exchange authorization code for token; store in CredentialStore.

        Accepts either a bare code or a full redirect URL containing ?code=.
        """
        code = self._extract_code(raw_input)
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": self._code_verifier or "",
                "client_id": _CLIENT_ID,
                "redirect_uri": _REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if token:
            self._store.set(self.provider_name, token)

    @staticmethod
    def _extract_code(raw_input: str) -> str:
        """Return the code value from a bare code string or a full redirect URL."""
        raw_input = raw_input.strip()
        parsed = urlparse(raw_input)
        if parsed.scheme in ("http", "https"):
            params = parse_qs(parsed.query)
            codes = params.get("code", [])
            if codes:
                return codes[0]
        return raw_input
