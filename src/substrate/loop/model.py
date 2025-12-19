"""Model interface and stub implementation.

Provides an abstract interface for model interaction and a stub
implementation for testing the loop mechanics without real AI calls.
"""

from abc import ABC, abstractmethod
from typing import Any

from substrate.loop.types import ModelRequest, ModelResponse, ToolCall


class ModelInterface(ABC):
    """Abstract interface for model interaction.

    Implementations must provide the query method that takes a request
    and returns a response. The actual model (Bedrock, etc.) is injected
    through concrete implementations.
    """

    @abstractmethod
    def query(self, request: ModelRequest) -> ModelResponse:
        """Send a request to the model and get a response.

        Args:
            request: The model request containing messages, tools, and system prompt

        Returns:
            ModelResponse with content and optional tool calls
        """
        ...


class StubModel(ModelInterface):
    """Stub model that returns canned responses for testing.

    Supports configurable response sequences to test different loop behaviors:
    - Simple completion (no tool calls)
    - Tool use requests
    - Multi-turn conversations

    The stub cycles through responses in order, repeating the last one
    if more queries are made than responses configured.
    """

    def __init__(self, responses: list[ModelResponse] | None = None) -> None:
        """Initialize with optional canned responses.

        Args:
            responses: List of responses to return in order.
                      If None, returns a simple completion response.
        """
        if responses is None:
            responses = [
                ModelResponse(
                    content="Task completed successfully.",
                    tool_calls=(),
                    stop_reason="end_turn",
                )
            ]
        self._responses = responses
        self._call_count = 0
        self._requests: list[ModelRequest] = []

    @property
    def call_count(self) -> int:
        """Number of times query has been called."""
        return self._call_count

    @property
    def requests(self) -> list[ModelRequest]:
        """All requests received (for test verification)."""
        return self._requests.copy()

    def query(self, request: ModelRequest) -> ModelResponse:
        """Return the next canned response.

        Args:
            request: The model request (stored for test verification)

        Returns:
            Next response in sequence, or last response if exhausted
        """
        self._requests.append(request)
        index = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[index]


def create_tool_use_response(
    tool_name: str,
    tool_input: dict[str, Any],
    call_id: str,
    content: str = "",
) -> ModelResponse:
    """Helper to create a response that requests tool use.

    Args:
        tool_name: Name of the tool to call
        tool_input: Input parameters for the tool
        call_id: Unique identifier for the call
        content: Optional text content before tool use

    Returns:
        ModelResponse with a tool call
    """
    return ModelResponse(
        content=content,
        tool_calls=(
            ToolCall(
                tool_name=tool_name,
                tool_input=tool_input,
                call_id=call_id,
            ),
        ),
        stop_reason="tool_use",
    )


def create_completion_response(content: str = "Done.") -> ModelResponse:
    """Helper to create a simple completion response.

    Args:
        content: Text content of the response

    Returns:
        ModelResponse with no tool calls and end_turn stop reason
    """
    return ModelResponse(
        content=content,
        tool_calls=(),
        stop_reason="end_turn",
    )
