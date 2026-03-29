"""Tests for M2 Phase 1: Model-related domain events and ModelEntry model.

Covers MAE-01 success criteria:
1. EventType has 4 new values
2. 4 event classes inheriting FixedEventTypeEvent are instantiable
3. All 4 registered in EVENT_TYPE_MAP and round-trip through envelope
4. ModelEntry has required fields
5. ModelListResponseEvent.models serializes/deserializes ModelEntry list
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# SC-1: EventType has 4 new model-related values
# --------------------------------------------------------------------------- #


class TestModelEventTypes:
    """EventType enum has MODEL_INFO, MODEL_LIST_REQUESTED, MODEL_LIST_RESPONSE, MODEL_SWITCH_REQUESTED."""

    def test_model_info_value(self):
        from breqy.domain.enums import EventType

        assert EventType.MODEL_INFO == "model.info"

    def test_model_list_requested_value(self):
        from breqy.domain.enums import EventType

        assert EventType.MODEL_LIST_REQUESTED == "model.list.requested"

    def test_model_list_response_value(self):
        from breqy.domain.enums import EventType

        assert EventType.MODEL_LIST_RESPONSE == "model.list.response"

    def test_model_switch_requested_value(self):
        from breqy.domain.enums import EventType

        assert EventType.MODEL_SWITCH_REQUESTED == "model.switch.requested"


# --------------------------------------------------------------------------- #
# SC-2: 4 event classes inheriting FixedEventTypeEvent
# --------------------------------------------------------------------------- #


class TestModelInfoEvent:
    """ModelInfoEvent carries provider_id and model_id."""

    def test_instantiation(self):
        from breqy.domain.events import ModelInfoEvent
        from breqy.domain.enums import EventType

        e = ModelInfoEvent(
            session_id="ses_test",
            provider_id="copilot",
            model_id="gpt-4o",
        )
        assert e.event_type == EventType.MODEL_INFO
        assert e.provider_id == "copilot"
        assert e.model_id == "gpt-4o"

    def test_rejects_wrong_event_type(self):
        from pydantic import ValidationError
        from breqy.domain.events import ModelInfoEvent
        from breqy.domain.enums import EventType

        with pytest.raises(ValidationError):
            ModelInfoEvent(
                session_id="ses_test",
                event_type=EventType.MESSAGE_SENT,
                provider_id="copilot",
                model_id="gpt-4o",
            )

    def test_is_fixed_event_type(self):
        from breqy.domain.events import ModelInfoEvent, FixedEventTypeEvent

        assert issubclass(ModelInfoEvent, FixedEventTypeEvent)


class TestModelListRequestedEvent:
    """ModelListRequestedEvent has no extra required fields beyond session_id."""

    def test_instantiation(self):
        from breqy.domain.events import ModelListRequestedEvent
        from breqy.domain.enums import EventType

        e = ModelListRequestedEvent(session_id="ses_test")
        assert e.event_type == EventType.MODEL_LIST_REQUESTED

    def test_rejects_wrong_event_type(self):
        from pydantic import ValidationError
        from breqy.domain.events import ModelListRequestedEvent
        from breqy.domain.enums import EventType

        with pytest.raises(ValidationError):
            ModelListRequestedEvent(
                session_id="ses_test",
                event_type=EventType.MESSAGE_SENT,
            )


class TestModelListResponseEvent:
    """ModelListResponseEvent carries models list and current provider/model."""

    def test_instantiation_with_models(self):
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry
        from breqy.domain.enums import EventType

        entry = ModelEntry(
            provider="copilot",
            model_id="gpt-4o",
            display_name="GPT-4o",
            is_authenticated=True,
        )
        e = ModelListResponseEvent(
            session_id="ses_test",
            models=[entry],
            current_provider="copilot",
            current_model="gpt-4o",
        )
        assert e.event_type == EventType.MODEL_LIST_RESPONSE
        assert len(e.models) == 1
        assert e.models[0].provider == "copilot"
        assert e.current_provider == "copilot"
        assert e.current_model == "gpt-4o"

    def test_empty_models_list_by_default(self):
        from breqy.domain.events import ModelListResponseEvent

        e = ModelListResponseEvent(session_id="ses_test")
        assert e.models == []
        assert e.current_provider == ""
        assert e.current_model == ""

    def test_rejects_wrong_event_type(self):
        from pydantic import ValidationError
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.enums import EventType

        with pytest.raises(ValidationError):
            ModelListResponseEvent(
                session_id="ses_test",
                event_type=EventType.MESSAGE_SENT,
            )


class TestModelSwitchRequestedEvent:
    """ModelSwitchRequestedEvent carries provider_id and model_id."""

    def test_instantiation(self):
        from breqy.domain.events import ModelSwitchRequestedEvent
        from breqy.domain.enums import EventType

        e = ModelSwitchRequestedEvent(
            session_id="ses_test",
            provider_id="claude",
            model_id="sonnet",
        )
        assert e.event_type == EventType.MODEL_SWITCH_REQUESTED
        assert e.provider_id == "claude"
        assert e.model_id == "sonnet"

    def test_rejects_wrong_event_type(self):
        from pydantic import ValidationError
        from breqy.domain.events import ModelSwitchRequestedEvent
        from breqy.domain.enums import EventType

        with pytest.raises(ValidationError):
            ModelSwitchRequestedEvent(
                session_id="ses_test",
                event_type=EventType.MESSAGE_SENT,
                provider_id="claude",
                model_id="sonnet",
            )


# --------------------------------------------------------------------------- #
# SC-3: EVENT_TYPE_MAP registration and envelope round-trip
# --------------------------------------------------------------------------- #


class TestEventTypeMapRegistration:
    """All 4 model event types are registered in EVENT_TYPE_MAP."""

    def test_model_info_in_map(self):
        from breqy.domain.events import EVENT_TYPE_MAP, ModelInfoEvent
        from breqy.domain.enums import EventType

        assert EVENT_TYPE_MAP[EventType.MODEL_INFO] is ModelInfoEvent

    def test_model_list_requested_in_map(self):
        from breqy.domain.events import EVENT_TYPE_MAP, ModelListRequestedEvent
        from breqy.domain.enums import EventType

        assert EVENT_TYPE_MAP[EventType.MODEL_LIST_REQUESTED] is ModelListRequestedEvent

    def test_model_list_response_in_map(self):
        from breqy.domain.events import EVENT_TYPE_MAP, ModelListResponseEvent
        from breqy.domain.enums import EventType

        assert EVENT_TYPE_MAP[EventType.MODEL_LIST_RESPONSE] is ModelListResponseEvent

    def test_model_switch_requested_in_map(self):
        from breqy.domain.events import EVENT_TYPE_MAP, ModelSwitchRequestedEvent
        from breqy.domain.enums import EventType

        assert EVENT_TYPE_MAP[EventType.MODEL_SWITCH_REQUESTED] is ModelSwitchRequestedEvent


class TestModelEventEnvelopeRoundTrip:
    """Model events survive Envelope.from_event → to_event round-trip."""

    def test_model_info_round_trip(self):
        from breqy.a2a.envelope import Envelope
        from breqy.domain.events import ModelInfoEvent

        original = ModelInfoEvent(
            session_id="ses_rt",
            provider_id="copilot",
            model_id="gpt-4o",
        )
        env = Envelope.from_event(original)
        restored = env.to_event()
        assert isinstance(restored, ModelInfoEvent)
        assert restored.provider_id == "copilot"
        assert restored.model_id == "gpt-4o"
        assert restored.session_id == "ses_rt"

    def test_model_list_requested_round_trip(self):
        from breqy.a2a.envelope import Envelope
        from breqy.domain.events import ModelListRequestedEvent

        original = ModelListRequestedEvent(session_id="ses_rt")
        env = Envelope.from_event(original)
        restored = env.to_event()
        assert isinstance(restored, ModelListRequestedEvent)
        assert restored.session_id == "ses_rt"

    def test_model_list_response_round_trip(self):
        from breqy.a2a.envelope import Envelope
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="copilot", model_id="gpt-4o", display_name="GPT-4o", is_authenticated=True),
            ModelEntry(provider="claude", model_id="sonnet", display_name="Claude Sonnet", is_authenticated=False),
        ]
        original = ModelListResponseEvent(
            session_id="ses_rt",
            models=entries,
            current_provider="copilot",
            current_model="gpt-4o",
        )
        env = Envelope.from_event(original)
        restored = env.to_event()
        assert isinstance(restored, ModelListResponseEvent)
        assert len(restored.models) == 2
        assert restored.models[0].provider == "copilot"
        assert restored.models[1].is_authenticated is False
        assert restored.current_provider == "copilot"
        assert restored.current_model == "gpt-4o"

    def test_model_switch_requested_round_trip(self):
        from breqy.a2a.envelope import Envelope
        from breqy.domain.events import ModelSwitchRequestedEvent

        original = ModelSwitchRequestedEvent(
            session_id="ses_rt",
            provider_id="gemini",
            model_id="gemini-2.0-flash",
        )
        env = Envelope.from_event(original)
        restored = env.to_event()
        assert isinstance(restored, ModelSwitchRequestedEvent)
        assert restored.provider_id == "gemini"
        assert restored.model_id == "gemini-2.0-flash"

    def test_model_info_encode_decode_round_trip(self):
        """Full wire format: encode_envelope → decode_envelope."""
        from breqy.a2a.envelope import Envelope, encode_envelope, decode_envelope
        from breqy.domain.events import ModelInfoEvent

        original = ModelInfoEvent(
            session_id="ses_wire",
            provider_id="qwen",
            model_id="qwen-max",
        )
        env = Envelope.from_event(original)
        encoded = encode_envelope(env)
        decoded = decode_envelope(encoded)
        restored = decoded.to_event()
        assert isinstance(restored, ModelInfoEvent)
        assert restored.provider_id == "qwen"
        assert restored.model_id == "qwen-max"

    def test_model_list_response_encode_decode_with_models(self):
        """Full wire format with nested ModelEntry list."""
        from breqy.a2a.envelope import Envelope, encode_envelope, decode_envelope
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="copilot", model_id="gpt-4o", display_name="GPT-4o", is_authenticated=True),
        ]
        original = ModelListResponseEvent(
            session_id="ses_wire",
            models=entries,
            current_provider="copilot",
            current_model="gpt-4o",
        )
        env = Envelope.from_event(original)
        encoded = encode_envelope(env)
        decoded = decode_envelope(encoded)
        restored = decoded.to_event()
        assert isinstance(restored, ModelListResponseEvent)
        assert len(restored.models) == 1
        assert restored.models[0].model_id == "gpt-4o"


# --------------------------------------------------------------------------- #
# SC-4: ModelEntry Pydantic model
# --------------------------------------------------------------------------- #


class TestModelEntry:
    """ModelEntry has provider, model_id, display_name, is_authenticated."""

    def test_instantiation(self):
        from breqy.domain.models import ModelEntry

        m = ModelEntry(
            provider="copilot",
            model_id="gpt-4o",
            display_name="GPT-4o",
            is_authenticated=True,
        )
        assert m.provider == "copilot"
        assert m.model_id == "gpt-4o"
        assert m.display_name == "GPT-4o"
        assert m.is_authenticated is True

    def test_unauthenticated_by_default_false(self):
        """is_authenticated has no default — must be explicitly provided."""
        from pydantic import ValidationError
        from breqy.domain.models import ModelEntry

        with pytest.raises(ValidationError):
            ModelEntry(
                provider="copilot",
                model_id="gpt-4o",
                display_name="GPT-4o",
            )

    def test_serialization_round_trip(self):
        from breqy.domain.models import ModelEntry

        m = ModelEntry(
            provider="claude",
            model_id="sonnet",
            display_name="Claude Sonnet",
            is_authenticated=False,
        )
        data = m.model_dump()
        restored = ModelEntry.model_validate(data)
        assert restored.provider == "claude"
        assert restored.is_authenticated is False

    def test_json_round_trip(self):
        from breqy.domain.models import ModelEntry

        m = ModelEntry(
            provider="gemini",
            model_id="gemini-2.0-flash",
            display_name="Gemini 2.0 Flash",
            is_authenticated=True,
        )
        json_str = m.model_dump_json()
        restored = ModelEntry.model_validate_json(json_str)
        assert restored.model_id == "gemini-2.0-flash"
        assert restored.display_name == "Gemini 2.0 Flash"


# --------------------------------------------------------------------------- #
# SC-5: ModelListResponseEvent.models serialization
# --------------------------------------------------------------------------- #


class TestModelListResponseSerialization:
    """ModelListResponseEvent with ModelEntry list survives full serialization."""

    def test_model_dump_preserves_models(self):
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="copilot", model_id="gpt-4o", display_name="GPT-4o", is_authenticated=True),
            ModelEntry(provider="copilot", model_id="o3-mini", display_name="O3 Mini", is_authenticated=True),
        ]
        e = ModelListResponseEvent(
            session_id="ses_ser",
            models=entries,
            current_provider="copilot",
            current_model="gpt-4o",
        )
        data = e.model_dump()
        assert len(data["models"]) == 2
        assert data["models"][0]["provider"] == "copilot"
        assert data["models"][1]["model_id"] == "o3-mini"

    def test_model_validate_restores_models(self):
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="qwen", model_id="qwen-max", display_name="Qwen Max", is_authenticated=False),
        ]
        e = ModelListResponseEvent(
            session_id="ses_ser",
            models=entries,
            current_provider="qwen",
            current_model="qwen-max",
        )
        data = e.model_dump()
        restored = ModelListResponseEvent.model_validate(data)
        assert isinstance(restored.models[0], ModelEntry)
        assert restored.models[0].provider == "qwen"
        assert restored.models[0].is_authenticated is False

    def test_json_round_trip_with_models(self):
        from breqy.domain.events import ModelListResponseEvent
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="copilot", model_id="gpt-4o", display_name="GPT-4o", is_authenticated=True),
            ModelEntry(provider="claude", model_id="opus", display_name="Claude Opus", is_authenticated=False),
            ModelEntry(provider="gemini", model_id="gemini-2.5-pro", display_name="Gemini 2.5 Pro", is_authenticated=True),
        ]
        e = ModelListResponseEvent(
            session_id="ses_json",
            models=entries,
            current_provider="copilot",
            current_model="gpt-4o",
        )
        json_str = e.model_dump_json()
        restored = ModelListResponseEvent.model_validate_json(json_str)
        assert len(restored.models) == 3
        assert restored.models[2].display_name == "Gemini 2.5 Pro"

    def test_deserialize_event_restores_model_list_response(self):
        """deserialize_event() correctly reconstructs ModelListResponseEvent."""
        from breqy.domain.events import ModelListResponseEvent, deserialize_event
        from breqy.domain.models import ModelEntry

        entries = [
            ModelEntry(provider="copilot", model_id="gpt-4o", display_name="GPT-4o", is_authenticated=True),
        ]
        original = ModelListResponseEvent(
            session_id="ses_deser",
            models=entries,
            current_provider="copilot",
            current_model="gpt-4o",
        )
        data = original.model_dump()
        # datetime fields need string conversion for deserialize_event
        data["timestamp"] = original.timestamp.isoformat()
        restored = deserialize_event(data)
        assert isinstance(restored, ModelListResponseEvent)
        assert len(restored.models) == 1
        assert restored.models[0].model_id == "gpt-4o"
