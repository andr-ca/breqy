# system/orchestrator/auth/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class AuthFlowType(str, Enum):
    DEVICE_FLOW = "device_flow"
    PKCE = "pkce"
    API_KEY = "api_key"


@dataclass
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class AuthProvider(ABC):
    flow_type: AuthFlowType

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def is_authenticated(self) -> bool: ...

    @abstractmethod
    def get_token(self) -> str | None: ...

    @abstractmethod
    def revoke(self) -> None: ...


class DeviceFlowProvider(AuthProvider):
    flow_type = AuthFlowType.DEVICE_FLOW

    @abstractmethod
    def request_device_code(self) -> DeviceCodeResponse: ...

    @abstractmethod
    def poll_for_token(self, device_code: str) -> str | None:
        """Single poll attempt. Returns token string if authorized, None if still pending."""


class PkceProvider(AuthProvider):
    flow_type = AuthFlowType.PKCE

    @abstractmethod
    def get_auth_url(self) -> str:
        """Generate PKCE challenge, store verifier, return authorization URL."""

    @abstractmethod
    def exchange_code(self, auth_code: str) -> None:
        """Exchange authorization code for token; store in CredentialStore."""


class ApiKeyProvider(AuthProvider):
    flow_type = AuthFlowType.API_KEY
    key_url: str | None = None  # Override to show "Get a key at …" hint in the UI

    @abstractmethod
    def set_key(self, api_key: str) -> None: ...
