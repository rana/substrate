"""Tests for sub init and sub status commands."""

import json
import tempfile
from pathlib import Path

import pytest

from substrate.cli.commands import init_command, status_command


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_substrate_directory(self) -> None:
        """Init creates .substrate directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = init_command(workspace)

            assert result == 0
            assert (workspace / ".substrate").is_dir()
            assert (workspace / ".substrate" / "config.json").is_file()
            assert (workspace / ".substrate" / "state" / "active.json").is_file()
            assert (workspace / ".substrate" / "state" / "nodes").is_dir()
            assert (workspace / ".substrate" / "logs" / "events.ndjson").is_file()

    def test_init_creates_root_node(self) -> None:
        """Init creates an initial root node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            init_command(workspace)

            # Load active state to get node ID
            active_path = workspace / ".substrate" / "state" / "active.json"
            with active_path.open() as f:
                active = json.load(f)

            node_id = active["active_node_id"]
            node_path = workspace / ".substrate" / "state" / "nodes" / f"{node_id}.json"

            assert node_path.is_file()

            with node_path.open() as f:
                node = json.load(f)

            assert node["node_id"] == node_id
            assert node["parent_node_id"] is None
            assert node["mode"] == "manual"
            assert node["permissions_snapshot"]["level"] == 0

    def test_init_is_idempotent(self) -> None:
        """Running init twice does not overwrite existing state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # First init
            init_command(workspace)

            # Get original node ID
            active_path = workspace / ".substrate" / "state" / "active.json"
            with active_path.open() as f:
                original_active = json.load(f)
            original_node_id = original_active["active_node_id"]

            # Second init
            result = init_command(workspace)

            assert result == 0

            # Node ID should be unchanged
            with active_path.open() as f:
                new_active = json.load(f)
            assert new_active["active_node_id"] == original_node_id

    def test_init_logs_event(self) -> None:
        """Init logs the initialization event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            init_command(workspace)

            log_path = workspace / ".substrate" / "logs" / "events.ndjson"
            with log_path.open() as f:
                lines = f.readlines()

            assert len(lines) >= 1
            event = json.loads(lines[0])
            assert event["event"] == "init"
            assert "ts" in event
            assert event["node_id"] is not None


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_fails_without_init(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status fails if workspace not initialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            result = status_command(workspace)

            assert result == 1
            captured = capsys.readouterr()
            assert "not initialized" in captured.err.lower()

    def test_status_shows_active_node(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status shows the active node ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            init_command(workspace)

            result = status_command(workspace)

            assert result == 0
            captured = capsys.readouterr()
            assert "Active node:" in captured.out

    def test_status_shows_workspace_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status shows the workspace path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            init_command(workspace)

            result = status_command(workspace)

            assert result == 0
            captured = capsys.readouterr()
            assert "Workspace path:" in captured.out
            assert tmpdir in captured.out

    def test_status_shows_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status shows the current mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            init_command(workspace)

            result = status_command(workspace)

            assert result == 0
            captured = capsys.readouterr()
            assert "Mode:" in captured.out
            assert "manual" in captured.out

    def test_status_shows_permission_level(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Status shows the permission level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            init_command(workspace)

            result = status_command(workspace)

            assert result == 0
            captured = capsys.readouterr()
            assert "Permission level:" in captured.out
            assert "0" in captured.out
            assert "observe" in captured.out

    def test_status_logs_event(self) -> None:
        """Status logs the status check event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            init_command(workspace)

            status_command(workspace)

            log_path = workspace / ".substrate" / "logs" / "events.ndjson"
            with log_path.open() as f:
                lines = f.readlines()

            # Should have init event and status event
            assert len(lines) >= 2
            status_event = json.loads(lines[-1])
            assert status_event["event"] == "status"
