"""Tests for Permission Gate.

Covers level enforcement and authorization logging per M3 requirements.
"""

import json
from pathlib import Path

from substrate.tools import (
    PermissionGate,
    PermissionLevel,
    create_default_registry,
)


class TestPermissionGate:
    """Test PermissionGate authorization logic."""

    def test_default_level_is_observe(self) -> None:
        """Permission gate defaults to level 0 (observe only)."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        assert gate.current_level == PermissionLevel.OBSERVE

    def test_authorize_read_file_at_level_0(self) -> None:
        """read_file is authorized at observe level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("read_file")

        assert result.authorized is True
        assert result.tool_name == "read_file"
        assert result.required_level == 0
        assert result.current_level == 0

    def test_deny_write_file_at_level_0(self) -> None:
        """write_file is denied at observe level (requires level 2)."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("write_file")

        assert result.authorized is False
        assert result.tool_name == "write_file"
        assert result.required_level == 2
        assert result.current_level == 0
        assert "< required level" in result.reason

    def test_deny_run_command_at_level_0(self) -> None:
        """run_command is denied at observe level (requires level 3)."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("run_command")

        assert result.authorized is False
        assert result.required_level == 3

    def test_authorize_after_level_change(self) -> None:
        """Tools become authorized when level is elevated."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        # Initially denied
        result1 = gate.authorize("write_file")
        assert result1.authorized is False

        # Elevate to ACT_LOCAL
        gate.set_level(PermissionLevel.ACT_LOCAL)

        # Now authorized
        result2 = gate.authorize("write_file")
        assert result2.authorized is True
        assert result2.current_level == 2

    def test_authorize_nonexistent_tool(self) -> None:
        """Authorizing unknown tool returns not authorized."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("nonexistent_tool")

        assert result.authorized is False
        assert "not found" in result.reason

    def test_initial_level_parameter(self) -> None:
        """Gate can be initialized with a specific level."""
        registry = create_default_registry()
        gate = PermissionGate(registry, initial_level=PermissionLevel.ACT_EXTERNAL)

        assert gate.current_level == PermissionLevel.ACT_EXTERNAL

        # All tools should be accessible at level 3
        for tool_name in registry.list_tools():
            result = gate.authorize(tool_name)
            assert result.authorized is True, f"{tool_name} should be authorized"


class TestPermissionLogging:
    """Test authorization logging to events.ndjson."""

    def test_authorization_logged(self, tmp_path: Path) -> None:
        """Authorization checks are logged to events.ndjson."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.authorize("read_file")

        assert event_log.exists()

        with open(event_log) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["type"] == "authorization_check"
        assert event["data"]["tool_name"] == "read_file"
        assert event["data"]["authorized"] is True
        assert "timestamp" in event

    def test_denied_authorization_logged(self, tmp_path: Path) -> None:
        """Denied authorizations are also logged."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.authorize("run_command")

        with open(event_log) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["data"]["authorized"] is False
        assert event["data"]["tool_name"] == "run_command"

    def test_level_change_logged(self, tmp_path: Path) -> None:
        """Permission level changes are logged."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.set_level(PermissionLevel.ACT_LOCAL)

        with open(event_log) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["type"] == "permission_level_changed"
        assert event["data"]["old_level"] == 0
        assert event["data"]["new_level"] == 2

    def test_multiple_events_appended(self, tmp_path: Path) -> None:
        """Multiple events are appended to log file."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.authorize("read_file")
        gate.authorize("write_file")
        gate.set_level(PermissionLevel.ACT_LOCAL)
        gate.authorize("write_file")

        with open(event_log) as f:
            lines = f.readlines()

        assert len(lines) == 4

        # Verify each line is valid JSON
        events = [json.loads(line) for line in lines]
        assert events[0]["data"]["tool_name"] == "read_file"
        assert events[1]["data"]["tool_name"] == "write_file"
        assert events[2]["type"] == "permission_level_changed"
        assert events[3]["data"]["authorized"] is True

    def test_log_creates_parent_directory(self, tmp_path: Path) -> None:
        """Log file creation creates parent directories."""
        event_log = tmp_path / "nested" / "dir" / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.authorize("read_file")

        assert event_log.exists()

    def test_no_logging_without_path(self) -> None:
        """No logging occurs when event_log_path is None."""
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=None)

        # Should not raise, just silently skip logging
        gate.authorize("read_file")
        gate.set_level(PermissionLevel.ACT_EXTERNAL)


class TestAuthorizationResult:
    """Test AuthorizationResult serialization."""

    def test_to_dict(self) -> None:
        """AuthorizationResult serializes correctly."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("read_file")
        data = result.to_dict()

        assert data["authorized"] is True
        assert data["tool_name"] == "read_file"
        assert data["required_level"] == 0
        assert data["current_level"] == 0
        assert isinstance(data["reason"], str)
