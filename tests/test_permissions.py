"""Tests for Permission Gate (M3).

Tests cover:
- Default permission level is OBSERVE (0)
- Authorization checks against tool requirements
- Permission level changes
- Logging of authorization decisions
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.tools.permissions import AuthorizationResult, PermissionGate
from substrate.tools.registry import ToolRegistry, create_default_registry
from substrate.tools.schemas import PermissionLevel, SideEffectClass, ToolSchema


class TestPermissionGateDefaults:
    """Tests for default permission gate behavior."""

    def test_default_level_is_observe(self) -> None:
        """Default permission level is OBSERVE (0)."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        assert gate.current_level == PermissionLevel.OBSERVE

    def test_custom_initial_level(self) -> None:
        """Can initialize with custom permission level."""
        registry = create_default_registry()
        gate = PermissionGate(registry, initial_level=PermissionLevel.ACT_LOCAL)

        assert gate.current_level == PermissionLevel.ACT_LOCAL


class TestAuthorization:
    """Tests for authorization checks."""

    def test_authorize_read_at_observe(self) -> None:
        """read_file is allowed at OBSERVE level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("read_file")

        assert result.authorized is True
        assert result.tool_name == "read_file"
        assert result.required_level == PermissionLevel.OBSERVE.value
        assert result.current_level == PermissionLevel.OBSERVE.value

    def test_authorize_write_denied_at_observe(self) -> None:
        """write_file is denied at OBSERVE level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("write_file")

        assert result.authorized is False
        assert result.tool_name == "write_file"
        assert result.required_level == PermissionLevel.ACT_LOCAL.value

    def test_authorize_write_allowed_at_act_local(self) -> None:
        """write_file is allowed at ACT_LOCAL level."""
        registry = create_default_registry()
        gate = PermissionGate(registry, initial_level=PermissionLevel.ACT_LOCAL)

        result = gate.authorize("write_file")

        assert result.authorized is True

    def test_authorize_command_denied_at_observe(self) -> None:
        """run_command is denied at OBSERVE level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("run_command")

        assert result.authorized is False
        assert result.required_level == PermissionLevel.ACT_EXTERNAL.value

    def test_authorize_command_allowed_at_external(self) -> None:
        """run_command is allowed at ACT_EXTERNAL level."""
        registry = create_default_registry()
        gate = PermissionGate(registry, initial_level=PermissionLevel.ACT_EXTERNAL)

        result = gate.authorize("run_command")

        assert result.authorized is True

    def test_authorize_unknown_tool(self) -> None:
        """Unknown tool returns unauthorized with -1 required level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        result = gate.authorize("nonexistent_tool")

        assert result.authorized is False
        assert result.required_level == -1
        assert "not found" in result.reason


class TestPermissionLevelChanges:
    """Tests for permission level changes."""

    def test_set_level(self) -> None:
        """Can change permission level."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        gate.set_level(PermissionLevel.ACT_LOCAL)

        assert gate.current_level == PermissionLevel.ACT_LOCAL

    def test_level_change_affects_authorization(self) -> None:
        """Changing level affects subsequent authorizations."""
        registry = create_default_registry()
        gate = PermissionGate(registry)

        # Initially denied
        result1 = gate.authorize("write_file")
        assert result1.authorized is False

        # Change level
        gate.set_level(PermissionLevel.ACT_LOCAL)

        # Now allowed
        result2 = gate.authorize("write_file")
        assert result2.authorized is True


class TestPermissionLogging:
    """Tests for permission logging."""

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

        assert event["event"] == "authorization_check"
        assert event["payload"]["tool_name"] == "read_file"
        assert event["payload"]["authorized"] is True
        assert "ts" in event

    def test_denied_authorization_logged(self, tmp_path: Path) -> None:
        """Denied authorizations are also logged."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.authorize("run_command")

        with open(event_log) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["payload"]["authorized"] is False
        assert event["payload"]["tool_name"] == "run_command"

    def test_level_change_logged(self, tmp_path: Path) -> None:
        """Permission level changes are logged."""
        event_log = tmp_path / "events.ndjson"
        registry = create_default_registry()
        gate = PermissionGate(registry, event_log_path=event_log)

        gate.set_level(PermissionLevel.ACT_LOCAL)

        with open(event_log) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["event"] == "permission_level_changed"
        assert event["payload"]["old_level"] == PermissionLevel.OBSERVE.value
        assert event["payload"]["new_level"] == PermissionLevel.ACT_LOCAL.value

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
        assert events[0]["payload"]["tool_name"] == "read_file"
        assert events[1]["payload"]["tool_name"] == "write_file"
        assert events[2]["event"] == "permission_level_changed"
        assert events[3]["payload"]["authorized"] is True


class TestAuthorizationResult:
    """Tests for AuthorizationResult dataclass."""

    def test_to_dict(self) -> None:
        """AuthorizationResult serializes correctly."""
        result = AuthorizationResult(
            authorized=True,
            tool_name="test_tool",
            required_level=2,
            current_level=3,
            reason="Test reason",
        )

        data = result.to_dict()

        assert data["authorized"] is True
        assert data["tool_name"] == "test_tool"
        assert data["required_level"] == 2
        assert data["current_level"] == 3
        assert data["reason"] == "Test reason"