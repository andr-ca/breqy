# system/orchestrator/auth/codex_auth.py
from __future__ import annotations

import datetime

import httpx

from system.orchestrator.auth.base import DeviceCodeResponse, DeviceFlowProvider
from system.orchestrator.auth.credential_store import CredentialStore

_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_USERCODE_URL = "https://auth.openai.com/api/accounts/deviceauth/usercode"
_POLL_URL = "https://auth.openai.com/api/accounts/deviceauth/token"
_TOKEN_URL = "https://auth.openai.com/oauth/token"
_VERIFICATION_URI = "https://auth.openai.com/codex/device"
_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"


class CodexAuth(DeviceFlowProvider):
    """OpenAI Codex authentication via device authorization flow.

    The server generates the PKCE pair; the code_verifier is returned in the
    poll response and used directly in the final token exchange.

    Flow:
      1. POST /deviceauth/usercode → {device_auth_id, user_code}
      2. User visits https://auth.openai.com/codex/device and enters user_code
      3. Poll POST /deviceauth/token until 200 → {authorization_code, code_verifier}
      4. Exchange POST /oauth/token (form-encoded) → access_token
    """

    def __init__(self, credential_store: CredentialStore) -> None:
        self._store = credential_store
        self._user_code: str | None = None

    @property
    def provider_name(self) -> str:
        return "codex"

    def is_authenticated(self) -> bool:
        return self._store.get(self.provider_name) is not None

    def get_token(self) -> str | None:
        return self._store.get(self.provider_name)

    def revoke(self) -> None:
        self._store.delete(self.provider_name)

    def request_device_code(self) -> DeviceCodeResponse:
        """Request a device_auth_id and user_code from OpenAI."""
        resp = httpx.post(_USERCODE_URL, json={"client_id": _CLIENT_ID})
        resp.raise_for_status()
        data = resp.json()
        self._user_code = data["user_code"]
        return DeviceCodeResponse(
            device_code=data["device_auth_id"],
            user_code=data["user_code"],
            verification_uri=_VERIFICATION_URI,
            expires_in=self._parse_expires_in(data),
            interval=int(data.get("interval", 5)),
        )

    @staticmethod
    def _parse_expires_in(data: dict) -> int:
        """Derive expires_in (seconds) from either expires_in or expires_at fields."""
        if "expires_in" in data:
            return int(data["expires_in"])
        if "expires_at" in data:
            try:
                expires_at = datetime.datetime.fromisoformat(data["expires_at"])
                now = datetime.datetime.now(datetime.UTC)
                return max(0, int((expires_at - now).total_seconds()))
            except (ValueError, TypeError):
                pass
        return 900

    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. device_code is the device_auth_id from request_device_code.

        Non-200 responses mean still pending — do not raise. Returns access_token
        or None if not yet authorized.
        """
        resp = httpx.post(
            _POLL_URL,
            json={"device_auth_id": device_code, "user_code": self._user_code},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Accept both field name variants seen across implementations
        auth_code = data.get("authorization_code") or data.get("code")
        code_verifier = data.get("code_verifier") or data.get("verifier")
        if not auth_code or not code_verifier:
            # Authorized but unexpected format — surface the raw response as an error
            raise RuntimeError(
                f"Unexpected poll response (keys: {list(data.keys())}). "
                "Please report this at github.com/your-org/breqy."
            )
        return self._exchange_code(auth_code, code_verifier)

    def _exchange_code(self, code: str, code_verifier: str) -> str | None:
        """Exchange the server-issued authorization_code + code_verifier for an access token."""
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": _CLIENT_ID,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": _REDIRECT_URI,
            },
        )
        if not resp.is_success:
            raise RuntimeError(f"Token exchange failed {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"No access_token in exchange response: {list(data.keys())}")
        self._store.set(self.provider_name, token)
        return token
