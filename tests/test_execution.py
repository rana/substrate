"""Tests for the Execution Engine.

Covers:
- Command execution with stdout/stderr capture
- Command timeout behavior
- Workspace confinement rejection
- File write with diff summary
- Execution logging format
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from substrate.runtime.execution import (
    CommandResult,
    ExecutionEngine,
    WorkspaceConfinementError,
    WriteResult,
)
from substrate.runtime.logging import EventLog


class TestCommandExecution:
    """Test command execution with stdout/stderr capture."""

    def test_simple_command_stdout(self, tmp_path: Path) -> None:
        """Test capturing stdout from a simple command."""
        engine = ExecutionEngine(tmp_path)

        result = engine.run_command(["echo", "hello world"])

        assert result.exit_code == 0
        assert "hello world" in result.stdout
        assert result.stderr == ""
        assert not result.timed_out
        assert result.duration_ms >= 0

    def test_command_stderr(self, tmp_path: Path) -> None:
        """Test capturing stderr from a command."""
        engine = ExecutionEngine(tmp_path)

        # Use Python to write to stderr
        result = engine.run_command(
            [sys.executable, "-c", "import sys; sys.stderr.write('error output')"]
        )

        assert result.exit_code == 0
        assert "error output" in result.stderr

    def test_command_exit_code(self, tmp_path: Path) -> None:
        """Test capturing non-zero exit code."""
        engine = ExecutionEngine(tmp_path)

        result = engine.run_command([sys.executable, "-c", "exit(42)"])

        assert result.exit_code == 42

    def test_command_with_args(self, tmp_path: Path) -> None:
        """Test command with multiple arguments."""
        engine = ExecutionEngine(tmp_path)

        result = engine.run_command(["echo", "arg1", "arg2", "arg3"])

        assert result.exit_code == 0
        assert "arg1" in result.stdout
        assert "arg2" in result.stdout
        assert "arg3" in result.stdout

    def test_command_not_found(self, tmp_path: Path) -> None:
        """Test handling of non-existent command."""
        engine = ExecutionEngine(tmp_path)

        result = engine.run_command(["nonexistent_command_12345"])

        assert result.exit_code == 127  # Standard "command not found"
        assert "not found" in result.stderr.lower()

    def test_empty_argv_raises(self, tmp_path: Path) -> None:
        """Test that empty argv raises ValueError."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(ValueError, match="argv cannot be empty"):
            engine.run_command([])

    def test_command_result_serialization(self, tmp_path: Path) -> None:
        """Test CommandResult serializes correctly."""
        result = CommandResult(
            argv=("echo", "test"),
            cwd="/tmp",
            exit_code=0,
            stdout="test\n",
            stderr="",
            timed_out=False,
            duration_ms=10,
        )

        data = result.to_dict()

        assert data["argv"] == ["echo", "test"]
        assert data["cwd"] == "/tmp"
        assert data["exit_code"] == 0
        assert data["stdout"] == "test\n"
        assert data["stderr"] == ""
        assert data["timed_out"] is False
        assert data["duration_ms"] == 10


class TestCommandTimeout:
    """Test command timeout behavior."""

    def test_command_timeout(self, tmp_path: Path) -> None:
        """Test that commands are killed after timeout."""
        engine = ExecutionEngine(tmp_path, default_timeout=1)

        # Sleep for longer than timeout
        result = engine.run_command([sys.executable, "-c", "import time; time.sleep(10)"])

        assert result.timed_out is True
        assert result.exit_code == -1

    def test_command_completes_before_timeout(self, tmp_path: Path) -> None:
        """Test that fast commands complete normally."""
        engine = ExecutionEngine(tmp_path, default_timeout=10)

        result = engine.run_command(["echo", "fast"])

        assert result.timed_out is False
        assert result.exit_code == 0

    def test_custom_timeout_per_command(self, tmp_path: Path) -> None:
        """Test per-command timeout override."""
        engine = ExecutionEngine(tmp_path, default_timeout=10)

        # Use very short timeout
        result = engine.run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            timeout=1,
        )

        assert result.timed_out is True


class TestWorkspaceConfinement:
    """Test workspace confinement rejection."""

    def test_write_inside_workspace_allowed(self, tmp_path: Path) -> None:
        """Test that writes inside workspace succeed."""
        engine = ExecutionEngine(tmp_path)

        result = engine.write_file("test.txt", "content")

        assert result.success is True
        assert (tmp_path / "test.txt").read_text() == "content"

    def test_write_outside_workspace_rejected(self, tmp_path: Path) -> None:
        """Test that writes outside workspace are rejected."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(WorkspaceConfinementError) as exc_info:
            engine.write_file("/tmp/outside.txt", "content")

        assert "outside workspace root" in str(exc_info.value)

    def test_write_parent_traversal_rejected(self, tmp_path: Path) -> None:
        """Test that parent directory traversal is rejected."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(WorkspaceConfinementError):
            engine.write_file("../outside.txt", "content")

    def test_read_outside_workspace_rejected(self, tmp_path: Path) -> None:
        """Test that reads outside workspace are rejected."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(WorkspaceConfinementError):
            engine.read_file("/etc/passwd")

    def test_cwd_outside_workspace_rejected(self, tmp_path: Path) -> None:
        """Test that cwd outside workspace is rejected."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(WorkspaceConfinementError):
            engine.run_command(["echo", "test"], cwd=Path("/tmp"))

    def test_cwd_inside_workspace_allowed(self, tmp_path: Path) -> None:
        """Test that cwd inside workspace is allowed."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        engine = ExecutionEngine(tmp_path)

        result = engine.run_command(["pwd"], cwd=subdir)

        assert result.exit_code == 0
        assert str(subdir) in result.stdout

    def test_nested_path_inside_workspace(self, tmp_path: Path) -> None:
        """Test writing to nested paths inside workspace."""
        engine = ExecutionEngine(tmp_path)

        result = engine.write_file("a/b/c/test.txt", "nested content")

        assert result.success is True
        assert (tmp_path / "a/b/c/test.txt").read_text() == "nested content"

    def test_workspace_confinement_error_details(self, tmp_path: Path) -> None:
        """Test that WorkspaceConfinementError includes path details."""
        engine = ExecutionEngine(tmp_path)

        try:
            engine.write_file("/outside/path.txt", "content")
            pytest.fail("Expected WorkspaceConfinementError")
        except WorkspaceConfinementError as e:
            assert e.workspace_root == tmp_path
            assert "/outside/path.txt" in str(e.path) or "outside" in str(e.path)


class TestFileWrite:
    """Test file write with diff summary."""

    def test_write_new_file(self, tmp_path: Path) -> None:
        """Test writing a new file."""
        engine = ExecutionEngine(tmp_path)

        result = engine.write_file("new.txt", "new content")

        assert result.success is True
        assert result.bytes_written == len(b"new content")
        assert result.hash_before is None
        assert result.size_before is None
        assert result.hash_after is not None
        assert result.size_after == result.bytes_written

    def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        """Test overwriting an existing file captures before/after."""
        engine = ExecutionEngine(tmp_path)

        # Create initial file
        (tmp_path / "existing.txt").write_text("original")

        result = engine.write_file("existing.txt", "updated")

        assert result.success is True
        assert result.hash_before is not None
        assert result.hash_after is not None
        assert result.hash_before != result.hash_after
        assert result.size_before == len(b"original")
        assert result.size_after == len(b"updated")

    def test_write_same_content(self, tmp_path: Path) -> None:
        """Test writing same content results in same hash."""
        engine = ExecutionEngine(tmp_path)

        content = "same content"
        (tmp_path / "same.txt").write_text(content)

        result = engine.write_file("same.txt", content)

        assert result.success is True
        assert result.hash_before == result.hash_after

    def test_write_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that write creates parent directories."""
        engine = ExecutionEngine(tmp_path)

        result = engine.write_file("deep/nested/path/file.txt", "content")

        assert result.success is True
        assert (tmp_path / "deep/nested/path/file.txt").exists()

    def test_write_result_serialization(self, tmp_path: Path) -> None:
        """Test WriteResult serializes correctly."""
        result = WriteResult(
            path="/test/path.txt",
            success=True,
            bytes_written=100,
            hash_before="abc123",
            hash_after="def456",
            size_before=50,
            size_after=100,
        )

        data = result.to_dict()

        assert data["path"] == "/test/path.txt"
        assert data["success"] is True
        assert data["bytes_written"] == 100
        assert data["hash_before"] == "abc123"
        assert data["hash_after"] == "def456"
        assert data["size_before"] == 50
        assert data["size_after"] == 100
        assert data["error"] is None


class TestExecutionLogging:
    """Test execution logging format."""

    def test_command_logged_to_ndjson(self, tmp_path: Path) -> None:
        """Test that command execution is logged."""
        log_path = tmp_path / "logs" / "execution.ndjson"
        event_log = EventLog(log_path)
        event_log.ensure_exists()
        engine = ExecutionEngine(tmp_path, execution_log=event_log)

        engine.run_command(["echo", "logged"])

        # Read and parse log
        log_content = log_path.read_text()
        lines = [line for line in log_content.strip().split("\n") if line]
        assert len(lines) >= 1

        event = json.loads(lines[-1])
        assert event["event"] == "run_command"
        assert "payload" in event
        assert event["payload"]["argv"] == ["echo", "logged"]
        assert "exit_code" in event["payload"]
        assert "stdout" in event["payload"]
        assert "stderr" in event["payload"]

    def test_write_logged_to_ndjson(self, tmp_path: Path) -> None:
        """Test that file writes are logged."""
        log_path = tmp_path / "logs" / "execution.ndjson"
        event_log = EventLog(log_path)
        event_log.ensure_exists()
        engine = ExecutionEngine(tmp_path, execution_log=event_log)

        engine.write_file("logged.txt", "content")

        # Read and parse log
        log_content = log_path.read_text()
        lines = [line for line in log_content.strip().split("\n") if line]
        assert len(lines) >= 1

        event = json.loads(lines[-1])
        assert event["event"] == "write_file"
        assert "payload" in event
        assert "logged.txt" in event["payload"]["path"]
        assert event["payload"]["success"] is True
        assert "hash_after" in event["payload"]

    def test_multiple_operations_logged(self, tmp_path: Path) -> None:
        """Test that multiple operations are appended to log."""
        log_path = tmp_path / "logs" / "execution.ndjson"
        event_log = EventLog(log_path)
        event_log.ensure_exists()
        engine = ExecutionEngine(tmp_path, execution_log=event_log)

        engine.run_command(["echo", "first"])
        engine.write_file("file.txt", "content")
        engine.run_command(["echo", "second"])

        log_content = log_path.read_text()
        lines = [line for line in log_content.strip().split("\n") if line]
        assert len(lines) == 3

        # Verify order
        events = [json.loads(line) for line in lines]
        assert events[0]["event"] == "run_command"
        assert events[1]["event"] == "write_file"
        assert events[2]["event"] == "run_command"

    def test_log_includes_timestamp(self, tmp_path: Path) -> None:
        """Test that log entries include timestamp."""
        log_path = tmp_path / "logs" / "execution.ndjson"
        event_log = EventLog(log_path)
        event_log.ensure_exists()
        engine = ExecutionEngine(tmp_path, execution_log=event_log)

        engine.run_command(["echo", "test"])

        log_content = log_path.read_text()
        event = json.loads(log_content.strip().split("\n")[-1])
        assert "ts" in event

    def test_no_log_when_none(self, tmp_path: Path) -> None:
        """Test that operations work without a log."""
        engine = ExecutionEngine(tmp_path, execution_log=None)

        result = engine.run_command(["echo", "no log"])

        assert result.exit_code == 0
        # Should not raise, even without log


class TestReadFile:
    """Test file reading with workspace confinement."""

    def test_read_existing_file(self, tmp_path: Path) -> None:
        """Test reading an existing file."""
        (tmp_path / "readable.txt").write_text("file content")
        engine = ExecutionEngine(tmp_path)

        content = engine.read_file("readable.txt")

        assert content == "file content"

    def test_read_nonexistent_file_raises(self, tmp_path: Path) -> None:
        """Test reading non-existent file raises FileNotFoundError."""
        engine = ExecutionEngine(tmp_path)

        with pytest.raises(FileNotFoundError):
            engine.read_file("nonexistent.txt")

    def test_read_with_absolute_path(self, tmp_path: Path) -> None:
        """Test reading with absolute path inside workspace."""
        file_path = tmp_path / "absolute.txt"
        file_path.write_text("absolute content")
        engine = ExecutionEngine(tmp_path)

        content = engine.read_file(str(file_path))

        assert content == "absolute content"
