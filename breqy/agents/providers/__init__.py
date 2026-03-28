"""Public Breqy provider contracts and adapters."""
from breqy.agents.providers.adapters import build_model_providers
from breqy.agents.providers.base import (
    CompletionMetadata,
    ModelProvider,
    ProviderEvent,
    ProviderRequest,
    ToolCallDelta,
    ToolDefinition,
)
from breqy.agents.providers.copilot import CopilotProvider
from breqy.agents.providers.copilot_auth import (
    CopilotAuthenticator,
    CopilotAuthError,
    DeviceFlowInfo,
)
from breqy.agents.providers.copilot_client import CopilotApiClient, CopilotApiError

__all__ = [
    "CompletionMetadata",
    "CopilotApiClient",
    "CopilotApiError",
    "CopilotAuthError",
    "CopilotAuthenticator",
    "CopilotProvider",
    "DeviceFlowInfo",
    "ModelProvider",
    "ProviderEvent",
    "ProviderRequest",
    "ToolCallDelta",
    "ToolDefinition",
    "build_model_providers",
]
