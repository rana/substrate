"""Type definitions for the agentic loop."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LoopState(Enum):
    """States for the agentic execution loop.

    pending: Initial state, waiting to start
    running: Model is being queried
    tool_use: Model requested tool execution, awaiting authorization/result
    completed: Loop finished successfully
    failed: Loop terminated due to error
    """

    PENDING = "pending"
    RUNNING = "running"
    TOOL_USE = "tool_use"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model.

    Attributes:
        tool_name: Name of the tool to invoke
        tool_input: Input parameters for the tool
        call_id: Unique identifier for this call (for matching results)
    """

    tool_name: str
    tool_input: dict[str, Any]
    call_id: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "call_id": self.call_id,
        }


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool invocation.

    Attributes:
        call_id: Matches the ToolCall this is responding to
        success: Whether the tool executed successfully
        output: Tool output data
        error: Error message if success is False
    """

    call_id: str
    success: bool
    output: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "call_id": self.call_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }


@dataclass(frozen=True)
class ModelRequest:
    """Input to the model for a turn.

    Attributes:
        messages: Conversation history
        tools: Available tool schemas
        system_prompt: System-level instructions
    """

    messages: tuple[dict[str, Any], ...]
    tools: tuple[dict[str, Any], ...]
    system_prompt: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "messages": list(self.messages),
            "tools": list(self.tools),
            "system_prompt": self.system_prompt,
        }


@dataclass(frozen=True)
class ModelResponse:
    """Output from the model for a turn.

    Attributes:
        content: Text response from the model
        tool_calls: Tool invocations requested by the model
        stop_reason: Why the model stopped (end_turn, tool_use, max_tokens)
    """

    content: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "stop_reason": self.stop_reason,
        }


@dataclass
class Turn:
    """A single turn in the agentic loop.

    Captures the complete state of one iteration through the loop.

    Attributes:
        turn_number: Sequential number of this turn (1-indexed)
        state: Loop state at the end of this turn
        request: Input sent to the model
        response: Output received from the model
        tool_results: Results of any tool calls made this turn
        error: Error message if the turn failed
    """

    turn_number: int
    state: LoopState
    request: ModelRequest | None = None
    response: ModelResponse | None = None
    tool_results: tuple[ToolResult, ...] = field(default_factory=tuple)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "turn_number": self.turn_number,
            "state": self.state.value,
            "request": self.request.to_dict() if self.request else None,
            "response": self.response.to_dict() if self.response else None,
            "tool_results": [tr.to_dict() for tr in self.tool_results],
            "error": self.error,
        }
