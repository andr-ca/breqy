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
    provider_name: str
    flow_type: AuthFlowType

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
    def poll_for_token(self, device_code: str) -> str | None: ...


class PkceProvider(AuthProvider):
    flow_type = AuthFlowType.PKCE

    @abstractmethod
    def get_auth_url(self) -> str: ...

    @abstractmethod
    def exchange_code(self, auth_code: str) -> None: ...


class ApiKeyProvider(AuthProvider):
    flow_type = AuthFlowType.API_KEY

    @abstractmethod
    def set_key(self, api_key: str) -> None: ...
