"""Permission Gate for tool authorization.

Enforces permission levels per 05-trust-and-permissions.md.
All authorization decisions are logged to events.ndjson.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from substrate.tools.registry import ToolRegistry
from substrate.tools.schemas import PermissionLevel, ToolSchema


@dataclass(frozen=True)
class AuthorizationResult:
    """Result of an authorization check.

    Attributes:
        authorized: Whether the action is permitted
        tool_name: Name of the tool checked
        required_level: Level required by the tool
        current_level: Current session permission level
        reason: Human-readable explanation of the decision
    """

    authorized: bool
    tool_name: str
    required_level: int
    current_level: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "authorized": self.authorized,
            "tool_name": self.tool_name,
            "required_level": self.required_level,
            "current_level": self.current_level,
            "reason": self.reason,
        }


class PermissionGate:
    """Gate that authorizes tool execution based on permission levels.

    Default permission level is 0 (observe only).
    All authorization decisions are logged.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        event_log_path: Path | None = None,
        initial_level: PermissionLevel = PermissionLevel.OBSERVE,
    ) -> None:
        """Initialize the permission gate.

        Args:
            registry: Tool registry for looking up tool requirements
            event_log_path: Path to events.ndjson for logging decisions
            initial_level: Starting permission level (default: OBSERVE/0)
        """
        self._registry = registry
        self._event_log_path = event_log_path
        self._current_level = initial_level

    @property
    def current_level(self) -> PermissionLevel:
        """Current permission level."""
        return self._current_level

    def set_level(self, level: PermissionLevel) -> None:
        """Set the current permission level.

        In production, this would require human authorization.
        For M3, we allow direct setting for testing.
        """
        old_level = self._current_level
        self._current_level = level
        self._log_event(
            "permission_level_changed",
            {
                "old_level": old_level.value,
                "new_level": level.value,
            },
        )

    def authorize(self, tool_name: str) -> AuthorizationResult:
        """Check if a tool can be executed at the current permission level.

        Args:
            tool_name: Name of the tool to authorize

        Returns:
            AuthorizationResult with decision and explanation
        """
        # Check if tool exists
        if tool_name not in self._registry:
            result = AuthorizationResult(
                authorized=False,
                tool_name=tool_name,
                required_level=-1,
                current_level=self._current_level.value,
                reason=f"Tool '{tool_name}' not found in registry",
            )
            self._log_authorization(result)
            return result

        tool: ToolSchema = self._registry.get(tool_name)
        required = tool.required_level.value
        current = self._current_level.value

        if current >= required:
            result = AuthorizationResult(
                authorized=True,
                tool_name=tool_name,
                required_level=required,
                current_level=current,
                reason=f"Permission level {current} >= required level {required}",
            )
        else:
            result = AuthorizationResult(
                authorized=False,
                tool_name=tool_name,
                required_level=required,
                current_level=current,
                reason=f"Permission level {current} < required level {required}",
            )

        self._log_authorization(result)
        return result

    def _log_authorization(self, result: AuthorizationResult) -> None:
        """Log an authorization decision to events.ndjson."""
        self._log_event("authorization_check", result.to_dict())

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Append an event to the event log.

        Events are NDJSON format per design docs.
        """
        if self._event_log_path is None:
            return

        import json

        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            "data": data,
        }

        # Ensure parent directory exists
        self._event_log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self._event_log_path, "a") as f:
            f.write(json.dumps(event) + "\n")
