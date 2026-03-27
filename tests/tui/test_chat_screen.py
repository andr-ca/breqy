"""Tests for breqy.tui.screens.chat — ChatScreen assembly of all chat widgets."""
from __future__ import annotations

import pytest

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Input

from breqy.domain.enums import (
    ApprovalStatus,
    EventType,
    MessageRole,
    TaskStatus,
    ToolStatus,
)
from breqy.domain.events import (
    AgentLifecycleEvent,
    ApprovalRequestedEvent,
    MessageChunkEvent,
    MessageSentEvent,
    TaskUpdatedEvent,
    ToolInvocationCompletedEvent,
    ToolInvocationFailedEvent,
    ToolInvocationStartedEvent,
    ToolOutputChunkEvent,
)
from breqy.domain.models import ApprovalRequest
from breqy.tui.screens.chat import ChatScreen
from breqy.tui.widgets.agent_status import AgentStatusBar
from breqy.tui.widgets.approval_prompt import ApprovalPrompt
from breqy.tui.widgets.chat_view import ChatView
from breqy.tui.widgets.control_bar import ControlBar
from breqy.tui.widgets.message_input import MessageInput, MessageSubmitted
from breqy.tui.widgets.task_panel import TaskPanel
from breqy.tui.widgets.tool_panel import ToolPanel


SESSION_ID = "ses_test123"


class ChatScreenApp(App[None]):
    """Minimal app that pushes a ChatScreen for testing."""

    SCREENS = {}

    def on_mount(self) -> None:
        self.push_screen(ChatScreen(session_id=SESSION_ID))


def _get_screen(app: App) -> ChatScreen:
    """Return the active ChatScreen from the app."""
    screen = app.screen
    assert isinstance(screen, ChatScreen)
    return screen


# --------------------------------------------------------------------------- #
# Composition tests
# --------------------------------------------------------------------------- #


class TestChatScreenComposition:
    """Test that ChatScreen composes all required widgets."""

    @pytest.mark.asyncio
    async def test_composes_chat_view(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            views = screen.query(ChatView)
            assert len(views) >= 1

    @pytest.mark.asyncio
    async def test_composes_message_input(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            inputs = screen.query(MessageInput)
            assert len(inputs) >= 1

    @pytest.mark.asyncio
    async def test_composes_task_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            panels = screen.query(TaskPanel)
            assert len(panels) >= 1

    @pytest.mark.asyncio
    async def test_composes_tool_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            panels = screen.query(ToolPanel)
            assert len(panels) >= 1

    @pytest.mark.asyncio
    async def test_composes_control_bar(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            bars = screen.query(ControlBar)
            assert len(bars) >= 1

    @pytest.mark.asyncio
    async def test_composes_agent_status_bar(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            bars = screen.query(AgentStatusBar)
            assert len(bars) >= 1

    @pytest.mark.asyncio
    async def test_composes_approval_prompt(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            prompts = screen.query(ApprovalPrompt)
            assert len(prompts) >= 1

    @pytest.mark.asyncio
    async def test_session_id_stored(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            assert screen.session_id == SESSION_ID


# --------------------------------------------------------------------------- #
# Event routing tests — MessageSentEvent
# --------------------------------------------------------------------------- #


class TestChatScreenMessageSent:
    """Test that incoming MessageSentEvent is routed to ChatView."""

    @pytest.mark.asyncio
    async def test_handle_message_sent_routes_to_chat_view(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = MessageSentEvent(
                session_id=SESSION_ID,
                message_id="msg_001",
                role=MessageRole.USER,
                content="Hello there!",
            )
            screen.handle_message_sent(event)
            await pilot.pause()
            chat_view = screen.query_one(ChatView)
            assert len(chat_view.log_widget.lines) == 1


# --------------------------------------------------------------------------- #
# Event routing tests — MessageChunkEvent (streaming)
# --------------------------------------------------------------------------- #


class TestChatScreenMessageChunk:
    """Test that incoming MessageChunkEvent is routed to ChatView streaming."""

    @pytest.mark.asyncio
    async def test_handle_message_chunk_accumulates_in_chat_view(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            chunk1 = MessageChunkEvent(
                session_id=SESSION_ID,
                message_id="msg_002",
                chunk="Hello",
                chunk_index=0,
            )
            chunk2 = MessageChunkEvent(
                session_id=SESSION_ID,
                message_id="msg_002",
                chunk=" world",
                chunk_index=1,
            )
            screen.handle_message_chunk(chunk1)
            screen.handle_message_chunk(chunk2)
            chat_view = screen.query_one(ChatView)
            assert chat_view._stream_buffer.get_text("msg_002") == "Hello world"


# --------------------------------------------------------------------------- #
# Event routing tests — TaskUpdatedEvent
# --------------------------------------------------------------------------- #


class TestChatScreenTaskUpdated:
    """Test that incoming TaskUpdatedEvent is routed to TaskPanel."""

    @pytest.mark.asyncio
    async def test_handle_task_updated_routes_to_task_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = TaskUpdatedEvent(
                session_id=SESSION_ID,
                task_id="tsk_001",
                title="Fix the bug",
                status=TaskStatus.RUNNING,
            )
            screen.handle_task_updated(event)
            await pilot.pause()
            task_panel = screen.query_one(TaskPanel)
            # TaskPanel tracks tasks internally
            assert "tsk_001" in task_panel._tasks


# --------------------------------------------------------------------------- #
# Event routing tests — ToolInvocationStartedEvent
# --------------------------------------------------------------------------- #


class TestChatScreenToolStarted:
    """Test that incoming ToolInvocationStartedEvent is routed to ToolPanel."""

    @pytest.mark.asyncio
    async def test_handle_tool_started_routes_to_tool_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = ToolInvocationStartedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_001",
                tool_name="shell",
                arguments={"command": "ls"},
                summary="List files",
            )
            screen.handle_tool_started(event)
            await pilot.pause()
            tool_panel = screen.query_one(ToolPanel)
            assert "inv_001" in tool_panel._entries


# --------------------------------------------------------------------------- #
# Event routing tests — ToolInvocationCompletedEvent
# --------------------------------------------------------------------------- #


class TestChatScreenToolCompleted:
    """Test that ToolInvocationCompletedEvent routes to ToolPanel."""

    @pytest.mark.asyncio
    async def test_handle_tool_completed_routes_to_tool_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            # First start the tool
            start_event = ToolInvocationStartedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_001",
                tool_name="shell",
                arguments={"command": "ls"},
            )
            screen.handle_tool_started(start_event)
            # Then complete it
            complete_event = ToolInvocationCompletedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_001",
                tool_name="shell",
                status=ToolStatus.COMPLETED,
                summary="Done",
            )
            screen.handle_tool_completed(complete_event)
            await pilot.pause()
            tool_panel = screen.query_one(ToolPanel)
            entry = tool_panel._entries["inv_001"]
            assert entry.status == ToolStatus.COMPLETED


# --------------------------------------------------------------------------- #
# Event routing tests — ToolInvocationFailedEvent
# --------------------------------------------------------------------------- #


class TestChatScreenToolFailed:
    """Test that ToolInvocationFailedEvent routes to ToolPanel."""

    @pytest.mark.asyncio
    async def test_handle_tool_failed_routes_to_tool_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            # First start the tool
            start_event = ToolInvocationStartedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_002",
                tool_name="shell",
                arguments={"command": "bad_cmd"},
            )
            screen.handle_tool_started(start_event)
            # Then fail it
            fail_event = ToolInvocationFailedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_002",
                tool_name="shell",
                error="Command not found",
            )
            screen.handle_tool_failed(fail_event)
            await pilot.pause()
            tool_panel = screen.query_one(ToolPanel)
            entry = tool_panel._entries["inv_002"]
            assert entry.status == ToolStatus.FAILED
            assert entry.error == "Command not found"


# --------------------------------------------------------------------------- #
# Event routing tests — ToolOutputChunkEvent
# --------------------------------------------------------------------------- #


class TestChatScreenToolOutput:
    """Test that ToolOutputChunkEvent routes to ToolPanel."""

    @pytest.mark.asyncio
    async def test_handle_tool_output_routes_to_tool_panel(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            # First start the tool
            start_event = ToolInvocationStartedEvent(
                session_id=SESSION_ID,
                invocation_id="inv_003",
                tool_name="shell",
                arguments={"command": "echo hi"},
            )
            screen.handle_tool_started(start_event)
            # Then send output
            output_event = ToolOutputChunkEvent(
                session_id=SESSION_ID,
                invocation_id="inv_003",
                chunk="hi\n",
                chunk_index=0,
            )
            screen.handle_tool_output(output_event)
            await pilot.pause()
            tool_panel = screen.query_one(ToolPanel)
            entry = tool_panel._entries["inv_003"]
            assert entry.output_chunks == ["hi\n"]


# --------------------------------------------------------------------------- #
# Event routing tests — ApprovalRequestedEvent
# --------------------------------------------------------------------------- #


class TestChatScreenApprovalRequested:
    """Test that ApprovalRequestedEvent shows ApprovalPrompt."""

    @pytest.mark.asyncio
    async def test_handle_approval_requested_shows_prompt(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = ApprovalRequestedEvent(
                session_id=SESSION_ID,
                approval_id="apr_001",
                invocation_id="inv_001",
                description="Execute shell command: rm -rf /",
            )
            screen.handle_approval_requested(event)
            await pilot.pause()
            prompt = screen.query_one(ApprovalPrompt)
            assert prompt.current_request is not None
            assert prompt.current_request.id == "apr_001"
            assert "Execute shell command: rm -rf /" in prompt.current_request.description


# --------------------------------------------------------------------------- #
# Event routing tests — AgentLifecycleEvent
# --------------------------------------------------------------------------- #


class TestChatScreenAgentLifecycle:
    """Test that AgentLifecycleEvent is routed to AgentStatusBar."""

    @pytest.mark.asyncio
    async def test_handle_agent_connected(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = AgentLifecycleEvent(
                session_id=SESSION_ID,
                agent_id="agt_breqy",
                event_type=EventType.AGENT_CONNECTED,
            )
            screen.handle_agent_lifecycle(event)
            await pilot.pause()
            status_bar = screen.query_one(AgentStatusBar)
            assert "agt_breqy" in status_bar._agents
            assert status_bar._agents["agt_breqy"] is True

    @pytest.mark.asyncio
    async def test_handle_agent_disconnected(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            # First connect
            connect_event = AgentLifecycleEvent(
                session_id=SESSION_ID,
                agent_id="agt_breqy",
                event_type=EventType.AGENT_CONNECTED,
            )
            screen.handle_agent_lifecycle(connect_event)
            # Then disconnect
            disconnect_event = AgentLifecycleEvent(
                session_id=SESSION_ID,
                agent_id="agt_breqy",
                event_type=EventType.AGENT_DISCONNECTED,
            )
            screen.handle_agent_lifecycle(disconnect_event)
            await pilot.pause()
            status_bar = screen.query_one(AgentStatusBar)
            assert status_bar._agents["agt_breqy"] is False


# --------------------------------------------------------------------------- #
# User interaction tests — MessageSubmitted
# --------------------------------------------------------------------------- #


class TestChatScreenUserMessage:
    """Test that user typing a message sends MessageSubmitted."""

    @pytest.mark.asyncio
    async def test_user_submits_message(self) -> None:
        messages: list[MessageSubmitted] = []

        class CapturingApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(ChatScreen(session_id=SESSION_ID))

            def on_message_submitted(self, event: MessageSubmitted) -> None:
                messages.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            msg_input = screen.query_one(MessageInput)
            inner_input = msg_input.query_one("#message-input", Input)
            inner_input.value = "Hello agent!"
            await inner_input.action_submit()
            await pilot.pause()
            assert len(messages) == 1
            assert messages[0].text == "Hello agent!"


# --------------------------------------------------------------------------- #
# User interaction tests — Approval decision
# --------------------------------------------------------------------------- #


class TestChatScreenApprovalDecision:
    """Test that user approval decisions post Approved/Denied messages."""

    @pytest.mark.asyncio
    async def test_user_approves_sends_approved(self) -> None:
        approved: list[ApprovalPrompt.Approved] = []

        class CapturingApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(ChatScreen(session_id=SESSION_ID))

            def on_approval_prompt_approved(
                self, event: ApprovalPrompt.Approved
            ) -> None:
                approved.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = ApprovalRequestedEvent(
                session_id=SESSION_ID,
                approval_id="apr_002",
                invocation_id="inv_002",
                description="Execute: ls",
            )
            screen.handle_approval_requested(event)
            await pilot.pause()
            prompt = screen.query_one(ApprovalPrompt)
            prompt.action_approve()
            await pilot.pause()
            assert len(approved) == 1
            assert approved[0].approval_id == "apr_002"

    @pytest.mark.asyncio
    async def test_user_denies_sends_denied(self) -> None:
        denied: list[ApprovalPrompt.Denied] = []

        class CapturingApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(ChatScreen(session_id=SESSION_ID))

            def on_approval_prompt_denied(
                self, event: ApprovalPrompt.Denied
            ) -> None:
                denied.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            event = ApprovalRequestedEvent(
                session_id=SESSION_ID,
                approval_id="apr_003",
                invocation_id="inv_003",
                description="Execute: rm file",
            )
            screen.handle_approval_requested(event)
            await pilot.pause()
            prompt = screen.query_one(ApprovalPrompt)
            prompt.action_deny()
            await pilot.pause()
            assert len(denied) == 1
            assert denied[0].approval_id == "apr_003"


# --------------------------------------------------------------------------- #
# User interaction tests — ControlAction
# --------------------------------------------------------------------------- #


class TestChatScreenControlAction:
    """Test that user control sends ControlAction."""

    @pytest.mark.asyncio
    async def test_user_sends_control_action(self) -> None:
        actions: list[ControlBar.ControlAction] = []

        class CapturingApp(App[None]):
            def on_mount(self) -> None:
                self.push_screen(ChatScreen(session_id=SESSION_ID))

            def on_control_bar_control_action(
                self, event: ControlBar.ControlAction
            ) -> None:
                actions.append(event)

        app = CapturingApp()
        async with app.run_test() as pilot:
            screen = _get_screen(app)
            # Circuit break is always enabled
            cb_btn = screen.query_one("#btn-circuit-break", Button)
            cb_btn.press()
            await pilot.pause()
            assert len(actions) == 1
            assert actions[0].event_type == EventType.CONTROL_CIRCUIT_BREAK


# --------------------------------------------------------------------------- #
# Escape key — pops screen
# --------------------------------------------------------------------------- #


class TestChatScreenEscape:
    """Test that Escape key pops the screen."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen(self) -> None:
        app = ChatScreenApp()
        async with app.run_test() as pilot:
            # Verify we are on ChatScreen
            assert isinstance(app.screen, ChatScreen)
            await pilot.press("escape")
            await pilot.pause()
            # After escape, ChatScreen should be popped
            assert not isinstance(app.screen, ChatScreen)
