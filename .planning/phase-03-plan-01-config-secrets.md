# Phase 3 Plan 01: Config, Secrets & Logging

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement typed configuration loading from YAML/env, a SecretProvider ABC with keyring and env-var implementations, and structured logging setup.

**Architecture:** Three independent modules under `breqy/config/`, `breqy/secrets/`, and `breqy/utils/`. Config models use Pydantic v2 with env-var defaults. SecretProvider is an ABC with two implementations: `KeyringSecretProvider` (OS keyring) and `EnvSecretProvider` (env vars, dev-only). Logging wired via structlog.

**Tech Stack:** Python 3.12, pydantic v2, pyyaml, structlog, keyring

**Worktree:** `/home/andrey/projects/breqy/.worktrees/exp-full-build`
**Run tests with:** `uv run pytest`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `breqy/config/__init__.py` | Create | Package init |
| `breqy/config/models.py` | Create | `EngineConfig`, `AgentConfig` Pydantic models |
| `breqy/config/loader.py` | Create | `load_engine_config()`, `load_agent_config()` |
| `breqy/secrets/__init__.py` | Create | Package init |
| `breqy/secrets/provider.py` | Create | `SecretProvider` ABC, `EnvSecretProvider`, `KeyringSecretProvider` |
| `breqy/utils/__init__.py` | Create | Package init |
| `breqy/utils/logging.py` | Create | `setup_logging(level)` |
| `tests/unit/config/__init__.py` | Create | Test package stub |
| `tests/unit/config/test_config.py` | Create | Config model + loader tests |
| `tests/unit/secrets/__init__.py` | Create | Test package stub |
| `tests/unit/secrets/test_provider.py` | Create | SecretProvider tests |

---

## Task 1: Config Models

**Files:**
- Create: `breqy/config/__init__.py`
- Create: `breqy/config/models.py`
- Create: `tests/unit/config/__init__.py`
- Create: `tests/unit/config/test_config.py` (partial — models only)

- [ ] **Step 1: Write the failing tests for config models**

Create `tests/unit/config/__init__.py` (empty) and `tests/unit/config/test_config.py`:

```python
"""Tests for config models."""
from __future__ import annotations

import os

import pytest

from breqy.config.models import AgentConfig, EngineConfig


def test_engine_config_defaults():
    """EngineConfig has sensible defaults from env or hardcoded fallback."""
    cfg = EngineConfig()
    assert cfg.socket_path  # non-empty
    assert cfg.data_dir  # non-empty
    assert cfg.db_path  # non-empty
    assert cfg.log_level == "INFO"
    assert cfg.default_agent_id == "breqy"


def test_engine_config_from_env(monkeypatch):
    """EngineConfig reads from BREQY_* env vars."""
    monkeypatch.setenv("BREQY_ENGINE_SOCKET", "/tmp/test.sock")
    monkeypatch.setenv("BREQY_DATA_DIR", "/tmp/data")
    monkeypatch.setenv("BREQY_DB_PATH", "/tmp/data/breqy.db")
    monkeypatch.setenv("BREQY_LOG_LEVEL", "DEBUG")
    cfg = EngineConfig()
    assert cfg.socket_path == "/tmp/test.sock"
    assert cfg.data_dir == "/tmp/data"
    assert cfg.db_path == "/tmp/data/breqy.db"
    assert cfg.log_level == "DEBUG"


def test_agent_config_required_fields():
    """AgentConfig requires id and name; others have defaults."""
    cfg = AgentConfig(id="breqy", name="Breqy Agent")
    assert cfg.id == "breqy"
    assert cfg.name == "Breqy Agent"
    assert cfg.autonomy_level == "supervised"
    assert isinstance(cfg.tool_permissions, list)


def test_agent_config_full():
    """AgentConfig accepts all optional fields."""
    cfg = AgentConfig(
        id="test-agent",
        name="Test Agent",
        display_name="Test",
        port=9000,
        autonomy_level="autonomous",
        tool_permissions=["shell", "fs"],
    )
    assert cfg.port == 9000
    assert cfg.tool_permissions == ["shell", "fs"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/config/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.config'`

- [ ] **Step 3: Create `breqy/config/__init__.py`** (empty)

- [ ] **Step 4: Create `breqy/config/models.py`**

```python
"""Configuration dataclasses for engine and agent."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class EngineConfig(BaseModel):
    """Engine daemon configuration."""

    socket_path: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_ENGINE_SOCKET", "/tmp/breqy-engine.sock"
        )
    )
    data_dir: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_DATA_DIR", str(Path.home() / ".breqy" / "data")
        )
    )
    db_path: str = Field(
        default_factory=lambda: os.getenv(
            "BREQY_DB_PATH",
            str(Path.home() / ".breqy" / "data" / "breqy.db"),
        )
    )
    log_level: str = Field(
        default_factory=lambda: os.getenv("BREQY_LOG_LEVEL", "INFO")
    )
    default_agent_id: str = "breqy"


class AgentConfig(BaseModel):
    """Agent process configuration loaded from agent.yaml."""

    id: str
    name: str
    display_name: str = ""
    port: int | None = None
    engine_socket: str = "/tmp/breqy-engine.sock"
    persona_file: str = "persona.md"
    autonomy_level: str = "supervised"
    tool_permissions: list[str] = Field(default_factory=list)
    skill_permissions: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    log_path: str = ""
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/config/test_config.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add breqy/config/__init__.py breqy/config/models.py \
        tests/unit/config/__init__.py tests/unit/config/test_config.py
git commit -m "feat(config): add EngineConfig and AgentConfig Pydantic models"
```

---

## Task 2: Config Loader

**Files:**
- Create: `breqy/config/loader.py`
- Modify: `tests/unit/config/test_config.py` (add loader tests)

- [ ] **Step 1: Write failing tests for the loader**

Add to `tests/unit/config/test_config.py`:

```python
import tempfile
from pathlib import Path

import yaml

from breqy.config.loader import load_agent_config, load_engine_config


def test_load_engine_config_no_file():
    """load_engine_config() with no path returns defaults."""
    cfg = load_engine_config()
    assert isinstance(cfg, EngineConfig)


def test_load_engine_config_from_yaml(tmp_path):
    """load_engine_config() with valid YAML overrides defaults."""
    config_file = tmp_path / "engine.yaml"
    config_file.write_text(
        yaml.dump({"socket_path": "/tmp/my.sock", "log_level": "DEBUG"})
    )
    cfg = load_engine_config(str(config_file))
    assert cfg.socket_path == "/tmp/my.sock"
    assert cfg.log_level == "DEBUG"


def test_load_agent_config_valid(tmp_path):
    """load_agent_config() reads agent.yaml from directory."""
    (tmp_path / "agent.yaml").write_text(
        yaml.dump({"id": "my-agent", "name": "My Agent", "autonomy_level": "supervised"})
    )
    cfg = load_agent_config(str(tmp_path))
    assert cfg.id == "my-agent"
    assert cfg.name == "My Agent"


def test_load_agent_config_missing_file(tmp_path):
    """load_agent_config() raises FileNotFoundError if agent.yaml absent."""
    import pytest
    with pytest.raises(FileNotFoundError):
        load_agent_config(str(tmp_path))


def test_load_agent_config_invalid_yaml(tmp_path):
    """load_agent_config() raises ValidationError for missing required fields."""
    from pydantic import ValidationError
    (tmp_path / "agent.yaml").write_text(yaml.dump({"display_name": "Missing id and name"}))
    with pytest.raises(ValidationError):
        load_agent_config(str(tmp_path))
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/config/test_config.py -v -k "loader or yaml or missing"
```
Expected: `ImportError: cannot import name 'load_agent_config'`

- [ ] **Step 3: Create `breqy/config/loader.py`**

```python
"""Load configuration from YAML files and environment."""
from __future__ import annotations

from pathlib import Path

import yaml

from breqy.config.models import AgentConfig, EngineConfig


def load_engine_config(config_path: str | None = None) -> EngineConfig:
    """Load engine config from env vars, optionally supplemented by YAML."""
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return EngineConfig(**data)
    return EngineConfig()


def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load agent config from agent.yaml in the given directory."""
    config_path = Path(agent_dir) / "agent.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent config not found: {config_path}")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/config/test_config.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add breqy/config/loader.py tests/unit/config/test_config.py
git commit -m "feat(config): add load_engine_config and load_agent_config"
```

---

## Task 3: SecretProvider

**Files:**
- Create: `breqy/secrets/__init__.py`
- Create: `breqy/secrets/provider.py`
- Create: `tests/unit/secrets/__init__.py`
- Create: `tests/unit/secrets/test_provider.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/secrets/__init__.py` (empty) and `tests/unit/secrets/test_provider.py`:

```python
"""Tests for SecretProvider implementations."""
from __future__ import annotations

import pytest

from breqy.secrets.provider import EnvSecretProvider, SecretProvider


def test_secret_provider_is_abstract():
    """SecretProvider cannot be instantiated directly."""
    import inspect
    assert inspect.isabstract(SecretProvider)


def test_env_secret_provider_set_and_get(monkeypatch):
    """EnvSecretProvider round-trips a secret through env vars."""
    provider = EnvSecretProvider()
    provider.set("mykey", "myvalue")
    assert provider.get("mykey") == "myvalue"


def test_env_secret_provider_get_missing(monkeypatch):
    """EnvSecretProvider returns None for unknown key."""
    provider = EnvSecretProvider()
    assert provider.get("no_such_key_xyz") is None


def test_env_secret_provider_delete(monkeypatch):
    """EnvSecretProvider deletes a key."""
    provider = EnvSecretProvider()
    provider.set("delkey", "delvalue")
    provider.delete("delkey")
    assert provider.get("delkey") is None


def test_env_secret_provider_delete_missing_no_error():
    """EnvSecretProvider.delete() on non-existent key does not raise."""
    provider = EnvSecretProvider()
    provider.delete("key_that_does_not_exist_abc123")  # must not raise
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/secrets/test_provider.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.secrets'`

- [ ] **Step 3: Create `breqy/secrets/__init__.py`** (empty)

- [ ] **Step 4: Create `breqy/secrets/provider.py`**

```python
"""SecretProvider interface with keyring and env fallback implementations."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """Abstract secret storage interface."""

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class EnvSecretProvider(SecretProvider):
    """Read secrets from environment variables. Fallback for dev/testing."""

    def get(self, key: str) -> str | None:
        return os.environ.get(f"BREQY_SECRET_{key.upper()}")

    def set(self, key: str, value: str) -> None:
        os.environ[f"BREQY_SECRET_{key.upper()}"] = value

    def delete(self, key: str) -> None:
        os.environ.pop(f"BREQY_SECRET_{key.upper()}", None)


class KeyringSecretProvider(SecretProvider):
    """Use system keyring for secret storage.

    Secrets are stored under the 'breqy' service namespace.
    Import of keyring is deferred to avoid hard dependency at module load.
    """

    SERVICE_NAME = "breqy"

    def get(self, key: str) -> str | None:
        import keyring  # noqa: PLC0415
        return keyring.get_password(self.SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        import keyring  # noqa: PLC0415
        keyring.set_password(self.SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import keyring  # noqa: PLC0415
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/secrets/test_provider.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add breqy/secrets/__init__.py breqy/secrets/provider.py \
        tests/unit/secrets/__init__.py tests/unit/secrets/test_provider.py
git commit -m "feat(secrets): add SecretProvider ABC, EnvSecretProvider, KeyringSecretProvider"
```

---

## Task 4: Logging Utility

**Files:**
- Create: `breqy/utils/__init__.py`
- Create: `breqy/utils/logging.py`
- Create: `tests/unit/utils/__init__.py`
- Create: `tests/unit/utils/test_logging.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/utils/__init__.py` (empty) and `tests/unit/utils/test_logging.py`:

```python
"""Tests for structured logging setup."""
from __future__ import annotations

import logging


def test_setup_logging_does_not_raise():
    """setup_logging() with valid level runs without error."""
    from breqy.utils.logging import setup_logging
    setup_logging("INFO")  # must not raise


def test_setup_logging_debug_level():
    """setup_logging() accepts DEBUG level."""
    from breqy.utils.logging import setup_logging
    setup_logging("DEBUG")  # must not raise


def test_setup_logging_invalid_level_falls_back():
    """setup_logging() with unknown level falls back to INFO without raising."""
    from breqy.utils.logging import setup_logging
    setup_logging("BOGUS_LEVEL")  # must not raise
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest tests/unit/utils/test_logging.py -v
```
Expected: `ModuleNotFoundError: No module named 'breqy.utils'`

- [ ] **Step 3: Create `breqy/utils/__init__.py`** (empty)

- [ ] **Step 4: Create `breqy/utils/logging.py`**

```python
"""Structured logging setup using structlog."""
from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
    """Configure structlog with human-readable console output.

    Safe to call multiple times — structlog.configure() is idempotent.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/unit/utils/test_logging.py -v
```
Expected: 3 passed

- [ ] **Step 6: Run full suite — verify no regressions**

```bash
uv run pytest --tb=no -q
```
Expected: 388 + new tests = all passed

- [ ] **Step 7: Commit**

```bash
git add breqy/utils/__init__.py breqy/utils/logging.py \
        tests/unit/utils/__init__.py tests/unit/utils/test_logging.py
git commit -m "feat(utils): add setup_logging() via structlog"
```

---

## Final Verification

```bash
uv run pytest tests/unit/config/ tests/unit/secrets/ tests/unit/utils/ -v
```
Expected: all 17 new tests pass, full suite clean.
