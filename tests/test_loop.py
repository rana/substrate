"""Tests for the agentic loop module."""

import json
from pathlib import Path

from substrate.loop.controller import LoopController
from substrate.loop.model import (
    StubModel,
    create_completion_response,
    create_tool_use_response,
)
from substrate.loop.types import LoopState, ModelResponse, ToolCall
from substrate.tools.permissions import PermissionGate
from substrate.tools.registry import create_default_registry
from substrate.tools.schemas import PermissionLevel


class TestLoopStates:
    """Test loop state transitions."""

    def test_initial_state_is_pending(self) -> None:
        """Loop starts in PENDING state."""
        model = StubModel()
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)

        assert controller.state == LoopState.PENDING

    def test_simple_completion_transitions_to_completed(self) -> None:
        """Simple completion response transitions to COMPLETED."""
        model = StubModel([create_completion_response("Done!")])
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Hello")

        final_state = controller.run()

        assert final_state == LoopState.COMPLETED
        assert controller.state == LoopState.COMPLETED

    def test_tool_use_transitions_through_tool_use_state(self) -> None:
        """Tool use response transitions through TOOL_USE state."""
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Read a file")

        # First step should be TOOL_USE
        turn1 = controller.step()
        assert turn1 is not None
        assert turn1.state == LoopState.TOOL_USE
        assert controller.state == LoopState.TOOL_USE

        # Second step should complete
        turn2 = controller.step()
        assert turn2 is not None
        assert turn2.state == LoopState.COMPLETED

    def test_max_turns_causes_failure(self) -> None:
        """Exceeding max turns transitions to FAILED."""
        # Model that always requests tools (never completes)
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, f"call_{i}")
            for i in range(20)
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, max_turns=3)
        controller.add_user_message("Keep going")

        final_state = controller.run()

        assert final_state == LoopState.FAILED
        assert controller.turn_count <= 4  # max_turns + 1 for failure turn


class TestTurnStructure:
    """Test turn structure and serialization."""

    def test_turn_captures_request_and_response(self) -> None:
        """Turn captures the model request and response."""
        model = StubModel([create_completion_response("Hello!")])
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Hi")

        controller.run()

        assert len(controller.turns) == 1
        turn = controller.turns[0]
        assert turn.request is not None
        assert turn.response is not None
        assert turn.response.content == "Hello!"

    def test_turn_captures_tool_results(self) -> None:
        """Turn captures tool call results."""
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Read a file")

        controller.run()

        # First turn should have tool results
        turn1 = controller.turns[0]
        assert len(turn1.tool_results) == 1
        assert turn1.tool_results[0].call_id == "call_1"

    def test_turn_serializes_to_dict(self) -> None:
        """Turn can be serialized to dictionary."""
        model = StubModel([create_completion_response("Done!")])
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Hello")

        controller.run()

        turn_dict = controller.turns[0].to_dict()
        assert turn_dict["turn_number"] == 1
        assert turn_dict["state"] == "completed"
        assert turn_dict["response"]["content"] == "Done!"

    def test_tool_call_serializes_correctly(self) -> None:
        """ToolCall serializes all fields."""
        tool_call = ToolCall(
            tool_name="read_file",
            tool_input={"path": "/test.txt"},
            call_id="abc123",
        )

        result = tool_call.to_dict()

        assert result["tool_name"] == "read_file"
        assert result["tool_input"]["path"] == "/test.txt"
        assert result["call_id"] == "abc123"

    def test_model_response_serializes_tool_calls(self) -> None:
        """ModelResponse serializes nested tool calls."""
        response = ModelResponse(
            content="I'll read that file.",
            tool_calls=(
                ToolCall("read_file", {"path": "a.txt"}, "call_1"),
                ToolCall("read_file", {"path": "b.txt"}, "call_2"),
            ),
            stop_reason="tool_use",
        )

        result = response.to_dict()

        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["tool_name"] == "read_file"


class TestMaxTurnsTermination:
    """Test max turns termination behavior."""

    def test_terminates_at_max_turns(self) -> None:
        """Loop terminates when max turns is reached."""
        # Infinite tool use
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, f"call_{i}")
            for i in range(100)
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, max_turns=5)
        controller.add_user_message("Go")

        final_state = controller.run()

        assert final_state == LoopState.FAILED
        # Should have exactly max_turns + 1 (the failure turn)
        assert controller.turn_count <= 6

    def test_max_turns_error_message(self) -> None:
        """Failure turn contains max turns error message."""
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, f"call_{i}")
            for i in range(10)
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, max_turns=2)
        controller.add_user_message("Go")

        controller.run()

        # Last turn should be the failure
        failure_turn = controller.turns[-1]
        assert failure_turn.error is not None
        assert "Maximum turns" in failure_turn.error

    def test_single_turn_max_completes_normally(self) -> None:
        """With max_turns=1, a completion response works."""
        model = StubModel([create_completion_response("Quick!")])
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, max_turns=1)
        controller.add_user_message("Be quick")

        final_state = controller.run()

        assert final_state == LoopState.COMPLETED


class TestPermissionGateIntegration:
    """Test permission gate integration for tool calls."""

    def test_authorized_tool_succeeds(self) -> None:
        """Authorized tool call returns success."""
        responses = [
            create_tool_use_response("read_file", {"path": "test.txt"}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Read a file")

        controller.run()

        turn1 = controller.turns[0]
        assert turn1.tool_results[0].success is True

    def test_unauthorized_tool_fails(self) -> None:
        """Unauthorized tool call returns failure."""
        # run_command requires ACT_EXTERNAL (level 3)
        responses = [
            create_tool_use_response("run_command", {"command": "ls"}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        # Default level is OBSERVE (0), which is insufficient
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Run a command")

        controller.run()

        turn1 = controller.turns[0]
        assert turn1.tool_results[0].success is False
        assert "Authorization denied" in (turn1.tool_results[0].error or "")

    def test_elevated_permission_allows_tool(self) -> None:
        """Elevated permission level allows previously denied tool."""
        responses = [
            create_tool_use_response("run_command", {"command": "ls"}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        gate.set_level(PermissionLevel.ACT_EXTERNAL)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Run a command")

        controller.run()

        turn1 = controller.turns[0]
        assert turn1.tool_results[0].success is True

    def test_unknown_tool_fails(self) -> None:
        """Unknown tool name returns failure."""
        responses = [
            create_tool_use_response("nonexistent_tool", {}, "call_1"),
            create_completion_response("Done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate)
        controller.add_user_message("Use unknown tool")

        controller.run()

        turn1 = controller.turns[0]
        assert turn1.tool_results[0].success is False
        assert "not found" in (turn1.tool_results[0].error or "").lower()


class TestEventLogging:
    """Test event logging to events.ndjson."""

    def test_turns_logged_to_file(self, tmp_path: Path) -> None:
        """Turns are logged to events.ndjson."""
        log_path = tmp_path / "logs" / "events.ndjson"
        model = StubModel([create_completion_response("Done!")])
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, event_log_path=log_path)
        controller.add_user_message("Hello")

        controller.run()

        assert log_path.exists()
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1

        event = json.loads(lines[0])
        assert event["type"] == "loop_turn"
        assert event["data"]["turn_number"] == 1

    def test_multiple_turns_all_logged(self, tmp_path: Path) -> None:
        """All turns in multi-turn conversation are logged."""
        log_path = tmp_path / "events.ndjson"
        responses = [
            create_tool_use_response("read_file", {"path": "a.txt"}, "call_1"),
            create_tool_use_response("read_file", {"path": "b.txt"}, "call_2"),
            create_completion_response("All done!"),
        ]
        model = StubModel(responses)
        registry = create_default_registry()
        gate = PermissionGate(registry)
        controller = LoopController(model, registry, gate, event_log_path=log_path)
        controller.add_user_message("Do things")

        controller.run()

        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 3

        for i, line in enumerate(lines, 1):
            event = json.loads(line)
            assert event["data"]["turn_number"] == i


class TestStubModel:
    """Test stub model behavior."""

    def test_default_response(self) -> None:
        """Default stub returns completion response."""
        model = StubModel()
        from substrate.loop.types import ModelRequest

        request = ModelRequest(
            messages=(),
            tools=(),
            system_prompt="Test",
        )

        response = model.query(request)

        assert response.stop_reason == "end_turn"
        assert len(response.tool_calls) == 0

    def test_cycles_through_responses(self) -> None:
        """Stub cycles through configured responses."""
        responses = [
            create_completion_response("First"),
            create_completion_response("Second"),
            create_completion_response("Third"),
        ]
        model = StubModel(responses)
        from substrate.loop.types import ModelRequest

        request = ModelRequest(messages=(), tools=(), system_prompt="Test")

        assert model.query(request).content == "First"
        assert model.query(request).content == "Second"
        assert model.query(request).content == "Third"
        # Repeats last
        assert model.query(request).content == "Third"

    def test_tracks_call_count(self) -> None:
        """Stub tracks number of calls."""
        model = StubModel()
        from substrate.loop.types import ModelRequest

        request = ModelRequest(messages=(), tools=(), system_prompt="Test")

        assert model.call_count == 0
        model.query(request)
        assert model.call_count == 1
        model.query(request)
        assert model.call_count == 2

    def test_stores_requests(self) -> None:
        """Stub stores all received requests."""
        model = StubModel()
        from substrate.loop.types import ModelRequest

        request1 = ModelRequest(
            messages=({"role": "user", "content": "Hello"},),
            tools=(),
            system_prompt="Test",
        )
        request2 = ModelRequest(
            messages=({"role": "user", "content": "Goodbye"},),
            tools=(),
            system_prompt="Test",
        )

        model.query(request1)
        model.query(request2)

        assert len(model.requests) == 2
        assert model.requests[0].messages[0]["content"] == "Hello"
        assert model.requests[1].messages[0]["content"] == "Goodbye"
