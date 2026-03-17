# tests/unit/orchestrator/auth/test_base.py
from system.orchestrator.auth.base import (
    AuthFlowType,
    AuthProvider,
    DeviceFlowProvider,
    PkceProvider,
    ApiKeyProvider,
    DeviceCodeResponse,
)


def test_auth_flow_type_values():
    assert AuthFlowType.DEVICE_FLOW == "device_flow"
    assert AuthFlowType.PKCE == "pkce"
    assert AuthFlowType.API_KEY == "api_key"


def test_device_code_response_fields():
    dcr = DeviceCodeResponse(
        device_code="dcode",
        user_code="ABCD-1234",
        verification_uri="https://example.com/activate",
        expires_in=900,
        interval=5,
    )
    assert dcr.device_code == "dcode"
    assert dcr.user_code == "ABCD-1234"


def test_device_flow_provider_is_abstract():
    import inspect
    assert inspect.isabstract(DeviceFlowProvider)


def test_pkce_provider_is_abstract():
    import inspect
    assert inspect.isabstract(PkceProvider)


def test_api_key_provider_is_abstract():
    import inspect
    assert inspect.isabstract(ApiKeyProvider)
