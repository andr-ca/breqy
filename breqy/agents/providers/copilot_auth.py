"""GitHub Copilot OAuth device flow authenticator."""
from __future__ import annotations

import time

import httpx
import structlog
from pydantic import BaseModel, SecretStr

from breqy.agents.credentials import CredentialStore
from breqy.agents.models import ProviderCredential
from breqy.domain.enums import CredentialKind

logger = structlog.get_logger(__name__)


class CopilotAuthError(Exception):
    """Raised when device flow fails (expired, denied, network error)."""


class DeviceFlowInfo(BaseModel):
    """Response from GitHub device flow initiation."""

    user_code: str
    verification_uri: str
    device_code: str
    interval: int
    expires_in: int


class CopilotAuthenticator:
    """Manages GitHub OAuth device flow and token persistence for Copilot."""

    GITHUB_CLIENT_ID: str = "Ov23li8tweQw6odWQebz"
    DEVICE_CODE_URL: str = "https://github.com/login/device/code"
    ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    OAUTH_SCOPE: str = "read:user"
    POLLING_SAFETY_MARGIN_S: float = 3.0

    def __init__(self, credential_store: CredentialStore) -> None:
        self._credential_store = credential_store

    def get_token(self) -> str | None:
        """Retrieve stored OAuth token, or None if not authenticated."""
        credential = self._credential_store.get("copilot")
        if credential is None:
            return None
        return credential.secret_value.get_secret_value()

    def clear_token(self) -> None:
        """Remove stored token (used on 401 to force re-auth)."""
        self._credential_store.delete("copilot")
        logger.info("copilot_token_cleared")

    def _store_token(self, access_token: str) -> None:
        """Persist OAuth token to credential store."""
        self._credential_store.set(
            "copilot",
            ProviderCredential(
                provider="copilot",
                credential_kind=CredentialKind.ACCESS_TOKEN,
                secret_value=SecretStr(access_token),
                metadata={"auth_flow": "device"},
            ),
        )
        logger.info("copilot_token_stored")

    def start_device_flow(self) -> DeviceFlowInfo:
        """Initiate GitHub OAuth device flow."""
        try:
            response = httpx.post(
                self.DEVICE_CODE_URL,
                json={
                    "client_id": self.GITHUB_CLIENT_ID,
                    "scope": self.OAUTH_SCOPE,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CopilotAuthError(
                f"Failed to initiate device flow: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CopilotAuthError(
                f"Failed to initiate device flow: {exc}"
            ) from exc

        data = response.json()
        info = DeviceFlowInfo(
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            device_code=data["device_code"],
            interval=data["interval"],
            expires_in=data.get("expires_in", 900),
        )
        logger.info(
            "copilot_device_flow_started",
            user_code=info.user_code,
            verification_uri=info.verification_uri,
        )
        return info

    def poll_for_token(self, device_code: str, interval: int) -> str:
        """Poll GitHub until user authorizes. Returns OAuth access token."""
        current_interval = interval

        while True:
            try:
                response = httpx.post(
                    self.ACCESS_TOKEN_URL,
                    json={
                        "client_id": self.GITHUB_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                raise CopilotAuthError(
                    f"Network error during token poll: {exc}"
                ) from exc
            data = response.json()

            access_token = data.get("access_token")
            if access_token:
                self._store_token(access_token)
                logger.info("copilot_device_flow_authorized")
                return access_token

            error = data.get("error")
            if error == "authorization_pending":
                logger.debug("copilot_device_flow_pending")
                time.sleep(current_interval + self.POLLING_SAFETY_MARGIN_S)
                continue

            if error == "slow_down":
                server_interval = data.get("interval")
                if isinstance(server_interval, int) and server_interval > 0:
                    current_interval = server_interval
                else:
                    current_interval = current_interval + 5
                logger.debug("copilot_device_flow_slow_down", new_interval=current_interval)
                time.sleep(current_interval + self.POLLING_SAFETY_MARGIN_S)
                continue

            if error == "expired_token":
                raise CopilotAuthError("Device code expired — please restart authentication")

            if error == "access_denied":
                raise CopilotAuthError("User denied authorization")

            if error:
                raise CopilotAuthError(f"Device flow error: {error}")
