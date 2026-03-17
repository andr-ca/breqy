# tests/unit/orchestrator/test_auth_panel.py
from unittest.mock import MagicMock, patch
from system.orchestrator.tui.panels.auth_panel import AuthPanel
from system.orchestrator.auth.base import AuthFlowType


def _make_device_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.DEVICE_FLOW
    p.provider_name = "copilot"
    p.is_authenticated.return_value = authenticated
    return p


def _make_pkce_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.PKCE
    p.provider_name = "claude"
    p.is_authenticated.return_value = authenticated
    return p


def _make_key_provider(authenticated=False):
    p = MagicMock()
    p.flow_type = AuthFlowType.API_KEY
    p.provider_name = "qwen"
    p.is_authenticated.return_value = authenticated
    return p


def test_auth_panel_instantiates():
    providers = {
        "copilot": _make_device_provider(),
        "claude": _make_pkce_provider(),
        "qwen": _make_key_provider(),
    }
    panel = AuthPanel(providers=providers)
    assert panel is not None


def test_auth_panel_status_summary():
    providers = {
        "copilot": _make_device_provider(authenticated=True),
        "claude": _make_pkce_provider(authenticated=False),
    }
    panel = AuthPanel(providers=providers)
    summary = panel.get_status_summary()
    assert summary["copilot"] is True
    assert summary["claude"] is False
