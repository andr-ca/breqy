# Python 3.12 Modular Development Instructions

## Overview

This document provides guidance for developing highly modular Python applications using Python 3.12, with emphasis on design patterns and dependency injection. The goal is to create code where modules are independently testable, replaceable, and composable.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Project Structure](#project-structure)
3. [Dependency Injection](#dependency-injection)
4. [Design Patterns](#design-patterns)
5. [Module Organization](#module-organization)
6. [Import Strategy](#import-strategy)
7. [Testing Modular Code](#testing-modular-code)
8. [Best Practices](#best-practices)

---

## Core Principles

### 1. Single Responsibility Principle (SRP)

Each module, class, and function should have ONE reason to change.

```python
# ❌ BAD: Multiple responsibilities
class UserManager:
    def validate_user(self, data):
        # validation logic
        pass

    def save_to_database(self, user):
        # database logic
        pass

    def send_email(self, user):
        # email logic
        pass

# ✅ GOOD: Separated concerns
class UserValidator:
    def validate(self, data) -> bool:
        pass

class UserRepository:
    def save(self, user) -> None:
        pass

class EmailService:
    def send(self, user) -> None:
        pass
```

### 2. Dependency Inversion Principle (DIP)

Depend on abstractions (interfaces), not concrete implementations.

```python
# ❌ BAD: Depends on concrete class
class UserService:
    def __init__(self):
        self.db = PostgresDatabase()  # Hard-coded dependency

# ✅ GOOD: Depends on abstraction
from abc import ABC, abstractmethod

class Database(ABC):
    @abstractmethod
    def save(self, data): pass

class UserService:
    def __init__(self, db: Database):
        self.db = db  # Injected abstraction
```

### 3. Interface Segregation Principle (ISP)

Clients should not be forced to depend on interfaces they don't use.

```python
# ❌ BAD: Bloated interface
class StorageBackend(ABC):
    @abstractmethod
    def read(self): pass
    @abstractmethod
    def write(self): pass
    @abstractmethod
    def stream(self): pass
    @abstractmethod
    def delete(self): pass

# ✅ GOOD: Segregated interfaces
class Readable(ABC):
    @abstractmethod
    def read(self): pass

class Writable(ABC):
    @abstractmethod
    def write(self): pass

class DiskStorage(Readable, Writable):
    def read(self): ...
    def write(self): ...
```

---

## Project Structure

### Recommended Layout

```
src/
├── __init__.py
├── main.py                          # Entry point
├── core/                            # Core abstractions
│   ├── __init__.py
│   ├── interfaces.py                # All abstract base classes
│   └── exceptions.py                # Custom exceptions
├── providers/                       # AI provider integrations
│   ├── __init__.py
│   ├── base.py                      # Provider interface
│   ├── claude/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── models.py
│   ├── copilot/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── models.py
│   └── gemini/
│       ├── __init__.py
│       ├── client.py
│       └── models.py
├── commands/                        # CLI command handlers
│   ├── __init__.py
│   ├── base.py                      # Command interface
│   ├── chat.py
│   ├── code_gen.py
│   └── help.py
├── channels/                        # Communication channels
│   ├── __init__.py
│   ├── base.py                      # Channel interface
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── bot.py
│   ├── whatsapp/
│   │   ├── __init__.py
│   │   └── client.py
│   └── cli/
│       ├── __init__.py
│       └── handler.py
├── config/                          # Configuration management
│   ├── __init__.py
│   ├── settings.py                  # Settings class
│   ├── loader.py                    # Config loading logic
│   └── validators.py                # Config validation
├── infrastructure/                  # Infrastructure services
│   ├── __init__.py
│   ├── container.py                 # DI container
│   ├── logger.py
│   ├── auth.py                      # OAuth/Auth handlers
│   └── storage.py                   # File/data storage
└── utils/                           # Utilities
    ├── __init__.py
    └── helpers.py

tests/
├── unit/
│   ├── test_providers/
│   ├── test_commands/
│   ├── test_channels/
│   └── test_config/
├── integration/
│   ├── test_provider_integration/
│   └── test_channel_integration/
└── fixtures/
    ├── mock_providers.py
    └── test_data.py
```

### Module Boundaries

Each folder is a module with clear:
- **Public interface** (exposed via `__init__.py`)
- **Implementation details** (private modules)
- **No circular imports**

```python
# src/providers/__init__.py
from .base import Provider
from .claude import ClaudeProvider
from .copilot import CopilotProvider

__all__ = ['Provider', 'ClaudeProvider', 'CopilotProvider']
```

---

## Dependency Injection

### Pattern 1: Constructor Injection (Preferred)

Pass dependencies through `__init__`.

```python
from typing import Protocol

class Logger(Protocol):
    def log(self, message: str) -> None: ...

class ChatCommand:
    def __init__(self, provider: Provider, logger: Logger):
        self.provider = provider
        self.logger = logger

    def execute(self, prompt: str) -> str:
        self.logger.log(f"Processing: {prompt}")
        return self.provider.complete(prompt)
```

**Advantages:**
- Dependencies are explicit
- Easy to test (swap implementations)
- Clear at instantiation time

**When to use:** Almost always — for classes with stable dependencies

### Pattern 2: Setter Injection

Set dependencies after instantiation.

```python
class Service:
    def __init__(self):
        self._config = None

    def set_config(self, config: Config) -> None:
        self._config = config
```

**When to use:** Optional dependencies, circular dependency avoidance

### Pattern 3: Factory Pattern

Create objects without specifying exact classes.

```python
from typing import Literal

class ProviderFactory:
    @staticmethod
    def create(provider_type: Literal['claude', 'copilot', 'gemini']) -> Provider:
        providers = {
            'claude': ClaudeProvider,
            'copilot': CopilotProvider,
            'gemini': GeminiProvider,
        }
        ProviderClass = providers[provider_type]
        return ProviderClass()
```

**When to use:** Multiple implementations of an interface, runtime selection

### Pattern 4: Service Locator (DI Container)

Central registry for all dependencies.

```python
class Container:
    def __init__(self):
        self._services = {}

    def register(self, name: str, factory):
        self._services[name] = factory

    def get(self, name: str):
        if name not in self._services:
            raise ValueError(f"Service '{name}' not registered")
        return self._services[name]()

# Usage
container = Container()
container.register('provider', lambda: ClaudeProvider())
container.register('logger', lambda: ConsoleLogger())

# In your code
provider = container.get('provider')
logger = container.get('logger')
```

### Recommended: Use `injector` Library

```python
from injector import Injector, inject, Binder

def configure(binder: Binder):
    binder.bind(Provider, to=ClaudeProvider)
    binder.bind(Logger, to=ConsoleLogger)
    binder.bind(Config, to=load_config())

injector = Injector([configure])
service = injector.get(UserService)
```

**Installation:**
```bash
pip install injector
```

**Advantages:**
- Automatic wiring
- Type-safe
- Minimal boilerplate
- Explicit configuration

---

## Design Patterns

### 1. Strategy Pattern

Encapsulate interchangeable algorithms.

```python
from abc import ABC, abstractmethod

class CompletionStrategy(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str: ...

class FastStrategy(CompletionStrategy):
    def complete(self, prompt: str) -> str:
        return "fast response"

class AccurateStrategy(CompletionStrategy):
    def complete(self, prompt: str) -> str:
        return "slow but accurate response"

class ChatService:
    def __init__(self, strategy: CompletionStrategy):
        self.strategy = strategy

    def execute(self, prompt: str) -> str:
        return self.strategy.complete(prompt)

# Usage
fast_service = ChatService(FastStrategy())
accurate_service = ChatService(AccurateStrategy())
```

### 2. Adapter Pattern

Make incompatible interfaces work together.

```python
class ExternalAPI:
    def fetch_data(self) -> dict:
        return {'user_id': 123, 'name': 'John'}

class UserAdapter:
    def __init__(self, api: ExternalAPI):
        self.api = api

    def get_user(self) -> User:
        data = self.api.fetch_data()
        return User(id=data['user_id'], name=data['name'])
```

### 3. Observer Pattern

Allow objects to notify others of state changes.

```python
from typing import Callable, List

class EventEmitter:
    def __init__(self):
        self._listeners: dict[str, List[Callable]] = {}

    def on(self, event: str, callback: Callable) -> None:
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)

    def emit(self, event: str, *args, **kwargs) -> None:
        for callback in self._listeners.get(event, []):
            callback(*args, **kwargs)

class ChatService(EventEmitter):
    def process(self, prompt: str):
        self.emit('processing_started', prompt)
        result = self._execute(prompt)
        self.emit('processing_completed', result)
        return result

# Usage
service = ChatService()
service.on('processing_completed', lambda result: print(f"Done: {result}"))
service.process("Hello")
```

### 4. Factory Method Pattern

Create objects without specifying exact classes.

```python
class ChannelFactory(ABC):
    @abstractmethod
    def create_handler(self) -> ChannelHandler: ...

class TelegramFactory(ChannelFactory):
    def create_handler(self) -> ChannelHandler:
        return TelegramHandler()

class WhatsAppFactory(ChannelFactory):
    def create_handler(self) -> ChannelHandler:
        return WhatsAppHandler()

# Client code doesn't know about concrete classes
def setup_channel(factory: ChannelFactory):
    handler = factory.create_handler()
    return handler
```

### 5. Decorator Pattern

Add behavior to objects dynamically.

```python
from functools import wraps

def log_execution(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        print(f"Executing {func.__name__}")
        result = func(*args, **kwargs)
        print(f"Completed {func.__name__}")
        return result
    return wrapper

class Provider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str: ...

class LoggingProviderDecorator(Provider):
    def __init__(self, provider: Provider, logger: Logger):
        self.provider = provider
        self.logger = logger

    def complete(self, prompt: str) -> str:
        self.logger.log(f"Starting completion for: {prompt}")
        result = self.provider.complete(prompt)
        self.logger.log(f"Completion finished: {result[:50]}...")
        return result
```

---

## Module Organization

### 1. Abstraction Module

Define all interfaces/protocols first.

```python
# src/core/interfaces.py
from abc import ABC, abstractmethod
from typing import Protocol

class Provider(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str: ...

    @abstractmethod
    def get_model_info(self) -> dict: ...

class Logger(Protocol):
    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def error(self, msg: str, exc: Exception = None) -> None: ...

class Config(Protocol):
    api_key: str
    model: str
    timeout: int
```

### 2. Implementation Module

Concrete implementations in separate files.

```python
# src/providers/claude.py
from src.core.interfaces import Provider

class ClaudeProvider(Provider):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = self._init_client()

    def complete(self, prompt: str) -> str:
        # Implementation
        pass

    def get_model_info(self) -> dict:
        # Implementation
        pass

    def _init_client(self):
        # Private initialization
        pass
```

### 3. Public API

Export only what's needed.

```python
# src/providers/__init__.py
from .base import Provider
from .claude import ClaudeProvider
from .copilot import CopilotProvider
from .gemini import GeminiProvider

__all__ = ['Provider', 'ClaudeProvider', 'CopilotProvider', 'GeminiProvider']
```

### 4. Configuration Module

Centralize all configuration.

```python
# src/config/settings.py
from dataclasses import dataclass
from pathlib import Path

@dataclass
class ProviderConfig:
    name: str
    api_key: str
    model: str
    timeout: int = 30

@dataclass
class ApplicationConfig:
    debug: bool
    providers: dict[str, ProviderConfig]
    channels: list[str]
    log_level: str

# src/config/loader.py
class ConfigLoader:
    @staticmethod
    def load_from_env() -> ApplicationConfig:
        # Load from environment variables
        pass

    @staticmethod
    def load_from_file(path: Path) -> ApplicationConfig:
        # Load from YAML/JSON file
        pass
```

---

## Import Strategy

### ❌ BAD: Avoid Circular Imports

```python
# src/providers/claude.py
from src.commands import ChatCommand  # Creates circular import

# src/commands/__init__.py
from src.providers import ClaudeProvider  # Circular!
```

### ✅ GOOD: Use Dependency Injection

```python
# src/providers/claude.py
class ClaudeProvider(Provider):
    def complete(self, prompt: str) -> str:
        pass

# src/commands/chat.py
class ChatCommand:
    def __init__(self, provider: Provider):  # Accept abstraction
        self.provider = provider
```

### Import Rules

1. **Never import downward in hierarchy**
   ```
   good:  providers → core
   bad:   core → providers
   ```

2. **Use TYPE_CHECKING for forward references**
   ```python
   from typing import TYPE_CHECKING

   if TYPE_CHECKING:
       from src.providers import Provider

   class Command:
       def __init__(self, provider: 'Provider'):
           self.provider = provider
   ```

3. **Group imports**
   ```python
   # Standard library
   import os
   from abc import ABC, abstractmethod

   # Third-party
   import requests

   # Local
   from src.core.interfaces import Logger
   from src.providers import Provider
   ```

---

## Testing Modular Code

### 1. Test Module Isolation

Each module tested independently with mocked dependencies.

```python
# tests/unit/test_chat_command.py
from unittest.mock import Mock
import pytest
from src.commands.chat import ChatCommand
from src.core.interfaces import Provider

@pytest.fixture
def mock_provider():
    provider = Mock(spec=Provider)
    provider.complete.return_value = "AI response"
    return provider

def test_chat_command_success(mock_provider):
    command = ChatCommand(mock_provider)
    result = command.execute("Hello")

    assert result == "AI response"
    mock_provider.complete.assert_called_once_with("Hello")

def test_chat_command_handles_error(mock_provider):
    mock_provider.complete.side_effect = Exception("API error")
    command = ChatCommand(mock_provider)

    with pytest.raises(Exception):
        command.execute("Hello")
```

### 2. Test Implementations

Create test doubles for interfaces.

```python
# tests/fixtures/mock_providers.py
from src.core.interfaces import Provider

class TestProvider(Provider):
    def __init__(self, response: str = "test response"):
        self.response = response
        self.calls = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.response

    def get_model_info(self) -> dict:
        return {"model": "test", "version": "1.0"}

# tests/unit/test_service.py
from tests.fixtures.mock_providers import TestProvider

def test_service_with_test_provider():
    provider = TestProvider("fixed response")
    service = ChatService(provider)

    result = service.process("test prompt")

    assert result == "fixed response"
    assert provider.calls == ["test prompt"]
```

### 3. Test Configuration Injection

Test with different configurations.

```python
@pytest.fixture
def fast_config():
    return ApplicationConfig(debug=False, strategy='fast', ...)

@pytest.fixture
def debug_config():
    return ApplicationConfig(debug=True, strategy='accurate', ...)

def test_service_respects_config(fast_config):
    service = ChatService(fast_config)
    # Should behave differently based on config
    pass
```

### 4. Integration Tests

Test multiple modules working together.

```python
# tests/integration/test_provider_flow.py
def test_end_to_end_chat_flow():
    config = load_test_config()
    container = Container()
    container.register('config', lambda: config)
    container.register('provider', lambda: ClaudeProvider(config.api_key))
    container.register('command', lambda: ChatCommand(container.get('provider')))

    command = container.get('command')
    result = command.execute("Test prompt")

    assert isinstance(result, str)
    assert len(result) > 0
```

---

## Best Practices

### 1. Use Type Hints Everywhere

```python
from typing import Optional, List, Dict, Protocol

class Repository(Protocol):
    def find_by_id(self, id: str) -> Optional[User]: ...
    def find_all(self) -> List[User]: ...
    def save(self, user: User) -> None: ...

def process_users(repository: Repository, filters: Dict[str, str]) -> List[User]:
    # Type hints enable IDE support and documentation
    pass
```

### 2. Prefer Composition Over Inheritance

```python
# ❌ BAD: Deep inheritance hierarchy
class Animal: pass
class Mammal(Animal): pass
class Canine(Mammal): pass
class Dog(Canine): pass

# ✅ GOOD: Composition
class Dog:
    def __init__(self, brain: Brain, body: Body, behavior: Behavior):
        self.brain = brain
        self.body = body
        self.behavior = behavior
```

### 3. Use Dataclasses for Data Objects

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Message:
    id: str
    content: str
    sender: str
    timestamp: float
    metadata: Optional[Dict] = None
```

### 4. Use Enums for Constants

```python
from enum import Enum, auto

class ProviderType(str, Enum):
    CLAUDE = "claude"
    COPILOT = "copilot"
    GEMINI = "gemini"

class CommandStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
```

### 5. Use Context Managers for Resource Management

```python
from contextlib import contextmanager

@contextmanager
def get_database_connection():
    conn = database.connect()
    try:
        yield conn
    finally:
        conn.close()

# Usage
with get_database_connection() as conn:
    result = conn.query("SELECT ...")
```

### 6. Explicit is Better Than Implicit

```python
# ❌ BAD: Magic behavior
def process(data):
    # What does this do? Not clear
    pass

# ✅ GOOD: Clear intent
def validate_and_normalize_user_email(email: str) -> str:
    """Validate email format and normalize to lowercase."""
    pass
```

### 7. Keep Functions Small and Focused

```python
# ❌ BAD: Too many responsibilities
def process_user_data(data):
    user = parse(data)
    user = validate(user)
    user = normalize(user)
    user = save(user)
    send_email(user)
    return user

# ✅ GOOD: Single responsibility
def process_user_data(raw_data: dict) -> User:
    user = UserFactory.create_from_raw(raw_data)
    return user

def save_user(user: User) -> None:
    repository.save(user)

def notify_user_created(user: User) -> None:
    email_service.send_welcome(user)
```

### 8. Error Handling with Custom Exceptions

```python
# src/core/exceptions.py
class MinimeError(Exception):
    """Base exception for minime"""
    pass

class ProviderError(MinimeError):
    """Raised when provider fails"""
    pass

class AuthenticationError(MinimeError):
    """Raised when authentication fails"""
    pass

# Usage
class ClaudeProvider(Provider):
    def complete(self, prompt: str) -> str:
        try:
            return self.client.message(prompt)
        except APIError as e:
            raise ProviderError(f"Claude API failed: {e}") from e
```

### 9. Logging Strategy

```python
import logging

logger = logging.getLogger(__name__)

class Service:
    def __init__(self, logger: logging.Logger = logger):
        self.logger = logger

    def execute(self, input_data):
        self.logger.debug(f"Executing with {input_data}")
        try:
            result = self._do_work(input_data)
            self.logger.info(f"Execution successful")
            return result
        except Exception as e:
            self.logger.error(f"Execution failed", exc_info=True)
            raise
```

### 10. Configuration Validation

```python
from pydantic import BaseModel, Field, validator

class ProviderConfig(BaseModel):
    name: str
    api_key: str
    model: str
    timeout: int = Field(default=30, ge=1, le=300)

    @validator('api_key')
    def api_key_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('API key cannot be empty')
        return v

# Usage
config = ProviderConfig(name="claude", api_key="sk-...", model="claude-3")
# Raises validation error if invalid
```

---

## Checklist: Creating a New Module

- [ ] Define interface/protocol in `core/interfaces.py`
- [ ] Create implementation in isolated file
- [ ] Export public API in `__init__.py`
- [ ] Write unit tests with mocked dependencies
- [ ] Use constructor injection for dependencies
- [ ] Document public methods
- [ ] No circular imports
- [ ] Type hints on all public methods
- [ ] Custom exceptions for module-specific errors
- [ ] Integration tests with other modules

---

## Resources

- **Dependency Injection**: https://refactoring.guru/design-patterns/dependency-injection
- **SOLID Principles**: https://en.wikipedia.org/wiki/SOLID
- **Design Patterns**: https://refactoring.guru/design-patterns
- **Python Type Hints**: https://docs.python.org/3.12/library/typing.html
- **Injector Library**: https://github.com/python-injector/injector
- **Pydantic**: https://docs.pydantic.dev/
