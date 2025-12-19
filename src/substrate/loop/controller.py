"""Loop controller for turn-based agentic execution.

Manages the execution loop that alternates between model queries
and tool execution until completion or termination conditions.
"""

from pathlib import Path
from typing import Any

from substrate.loop.model import ModelInterface
from substrate.loop.types import (
    LoopState,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolResult,
    Turn,
)
from substrate.tools.permissions import AuthorizationResult, PermissionGate
from substrate.tools.registry import ToolRegistry


class LoopController:
    """Controls the turn-based agentic execution loop.

    The loop follows this pattern:
    1. Start in PENDING state
    2. Build request and query model (RUNNING)
    3. If model requests tools, check permissions (TOOL_USE)
    4. Execute authorized tools and feed results back
    5. Repeat until model signals completion or max turns reached
    6. End in COMPLETED or FAILED state

    All turns are logged to events.ndjson.
    """

    def __init__(
        self,
        model: ModelInterface,
        registry: ToolRegistry,
        permission_gate: PermissionGate,
        event_log_path: Path | None = None,
        max_turns: int = 10,
        system_prompt: str = "You are a helpful assistant.",
    ) -> None:
        """Initialize the loop controller.

        Args:
            model: Model interface for queries
            registry: Tool registry for available tools
            permission_gate: Gate for authorizing tool use
            event_log_path: Path to events.ndjson for logging
            max_turns: Maximum turns before forced termination
            system_prompt: System prompt for model queries
        """
        self._model = model
        self._registry = registry
        self._gate = permission_gate
        self._event_log_path = event_log_path
        self._max_turns = max_turns
        self._system_prompt = system_prompt

        self._state = LoopState.PENDING
        self._turns: list[Turn] = []
        self._messages: list[dict[str, Any]] = []

    @property
    def state(self) -> LoopState:
        """Current loop state."""
        return self._state

    @property
    def turns(self) -> list[Turn]:
        """All turns executed so far."""
        return self._turns.copy()

    @property
    def turn_count(self) -> int:
        """Number of turns executed."""
        return len(self._turns)

    def _is_terminal(self) -> bool:
        """Check if the loop is in a terminal state."""
        return self._state in (LoopState.COMPLETED, LoopState.FAILED)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: The user's message text
        """
        self._messages.append({"role": "user", "content": content})

    def run(self) -> LoopState:
        """Execute the loop until completion or termination.

        Returns:
            Final loop state (COMPLETED or FAILED)
        """
        if self._is_terminal():
            return self._state

        while not self._is_terminal():
            if self.turn_count >= self._max_turns:
                self._fail(f"Maximum turns ({self._max_turns}) exceeded")
                break

            self._execute_turn()

        return self._state

    def step(self) -> Turn | None:
        """Execute a single turn.

        Returns:
            The turn that was executed, or None if loop is terminated
        """
        if self._is_terminal():
            return None

        if self.turn_count >= self._max_turns:
            self._fail(f"Maximum turns ({self._max_turns}) exceeded")
            return self._turns[-1] if self._turns else None

        return self._execute_turn()

    def _execute_turn(self) -> Turn:
        """Execute one turn of the loop.

        Returns:
            The executed turn
        """
        turn_number = self.turn_count + 1
        self._state = LoopState.RUNNING

        # Build request
        request = self._build_request()

        # Query model
        try:
            response = self._model.query(request)
        except Exception as e:
            turn = Turn(
                turn_number=turn_number,
                state=LoopState.FAILED,
                request=request,
                error=str(e),
            )
            self._record_turn(turn)
            self._state = LoopState.FAILED
            return turn

        # Process response
        if response.tool_calls:
            return self._handle_tool_use(turn_number, request, response)
        else:
            return self._handle_completion(turn_number, request, response)

    def _build_request(self) -> ModelRequest:
        """Build a model request from current state."""
        tools = self._get_tool_schemas()
        return ModelRequest(
            messages=tuple(self._messages),
            tools=tuple(tools),
            system_prompt=self._system_prompt,
        )

    def _get_tool_schemas(self) -> list[dict[str, Any]]:
        """Get tool schemas from registry."""
        schemas: list[dict[str, Any]] = []
        for tool_name in self._registry.list_tools():
            tool = self._registry.get(tool_name)
            schemas.append(tool.to_dict())
        return schemas

    def _handle_tool_use(
        self,
        turn_number: int,
        request: ModelRequest,
        response: ModelResponse,
    ) -> Turn:
        """Handle a response that requests tool use.

        Args:
            turn_number: Current turn number
            request: The request that was sent
            response: The response with tool calls

        Returns:
            The completed turn
        """
        self._state = LoopState.TOOL_USE
        tool_results: list[ToolResult] = []

        for tool_call in response.tool_calls:
            result = self._execute_tool_call(tool_call)
            tool_results.append(result)

            # Add tool result to messages for next turn
            self._messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": [tc.to_dict() for tc in response.tool_calls],
            })
            self._messages.append({
                "role": "tool",
                "tool_call_id": result.call_id,
                "content": str(result.output) if result.success else str(result.error),
            })

        turn = Turn(
            turn_number=turn_number,
            state=LoopState.TOOL_USE,
            request=request,
            response=response,
            tool_results=tuple(tool_results),
        )
        self._record_turn(turn)
        return turn

    def _execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call (stubbed).

        Checks permission gate but returns stubbed results.

        Args:
            tool_call: The tool call to execute

        Returns:
            Tool result (stubbed success or authorization failure)
        """
        # Check authorization
        auth_result: AuthorizationResult = self._gate.authorize(tool_call.tool_name)

        if not auth_result.authorized:
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output={},
                error=f"Authorization denied: {auth_result.reason}",
            )

        # Return stubbed success result
        # In M5+, this would actually execute the tool
        return ToolResult(
            call_id=tool_call.call_id,
            success=True,
            output={"status": "stubbed", "tool": tool_call.tool_name},
            error=None,
        )

    def _handle_completion(
        self,
        turn_number: int,
        request: ModelRequest,
        response: ModelResponse,
    ) -> Turn:
        """Handle a response that signals completion.

        Args:
            turn_number: Current turn number
            request: The request that was sent
            response: The completion response

        Returns:
            The completed turn
        """
        self._state = LoopState.COMPLETED

        # Add assistant response to messages
        self._messages.append({
            "role": "assistant",
            "content": response.content,
        })

        turn = Turn(
            turn_number=turn_number,
            state=LoopState.COMPLETED,
            request=request,
            response=response,
        )
        self._record_turn(turn)
        return turn

    def _fail(self, error: str) -> None:
        """Transition to failed state with error.

        Args:
            error: Error message explaining the failure
        """
        self._state = LoopState.FAILED
        turn = Turn(
            turn_number=self.turn_count + 1,
            state=LoopState.FAILED,
            error=error,
        )
        self._record_turn(turn)

    def _record_turn(self, turn: Turn) -> None:
        """Record a turn in history and log it.

        Args:
            turn: The turn to record
        """
        self._turns.append(turn)
        self._log_turn(turn)

    def _log_turn(self, turn: Turn) -> None:
        """Log a turn to events.ndjson.

        Args:
            turn: The turn to log
        """
        if self._event_log_path is None:
            return

        import json
        from datetime import UTC, datetime

        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "loop_turn",
            "data": turn.to_dict(),
        }

        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._event_log_path, "a") as f:
            f.write(json.dumps(event) + "\n")
