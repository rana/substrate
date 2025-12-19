"""Execution Engine for Substrate runtime.

Provides safe subprocess execution and file operations with:
- Tokenized command invocation (no shell by default)
- Workspace confinement for all paths
- Timeout enforcement
- Structured result capture
- Execution logging to NDJSON
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from substrate.runtime.logging import EventLog


@dataclass(frozen=True)
class CommandResult:
    """Result of a command execution.

    Attributes:
        argv: Command and arguments that were executed
        cwd: Working directory for execution
        exit_code: Process exit code
        stdout: Captured standard output
        stderr: Captured standard error
        timed_out: Whether the command was killed due to timeout
        duration_ms: Execution duration in milliseconds
    """

    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class WriteResult:
    """Result of a file write operation.

    Attributes:
        path: Absolute path to the file
        success: Whether the write succeeded
        bytes_written: Number of bytes written
        hash_before: SHA256 hash of file before write (None if new file)
        hash_after: SHA256 hash of file after write
        size_before: File size before write (None if new file)
        size_after: File size after write
        error: Error message if write failed
    """

    path: str
    success: bool
    bytes_written: int
    hash_before: str | None
    hash_after: str | None
    size_before: int | None
    size_after: int | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "path": self.path,
            "success": self.success,
            "bytes_written": self.bytes_written,
            "hash_before": self.hash_before,
            "hash_after": self.hash_after,
            "size_before": self.size_before,
            "size_after": self.size_after,
            "error": self.error,
        }


class WorkspaceConfinementError(Exception):
    """Raised when an operation attempts to access paths outside the workspace."""

    def __init__(self, path: Path, workspace_root: Path) -> None:
        self.path = path
        self.workspace_root = workspace_root
        super().__init__(
            f"Path '{path}' is outside workspace root '{workspace_root}'"
        )


class ExecutionEngine:
    """Safe execution engine with workspace confinement.

    All operations are confined to the workspace root.
    All operations are logged to execution.ndjson.
    """

    def __init__(
        self,
        workspace_root: Path,
        execution_log: EventLog | None = None,
        default_timeout: int = 30,
    ) -> None:
        """Initialize the execution engine.

        Args:
            workspace_root: Root directory for workspace confinement
            execution_log: EventLog for recording operations
            default_timeout: Default command timeout in seconds
        """
        self._workspace_root = workspace_root.resolve()
        self._execution_log = execution_log
        self._default_timeout = default_timeout

    @property
    def workspace_root(self) -> Path:
        """Return the workspace root path."""
        return self._workspace_root

    def _resolve_path(self, path: str | Path) -> Path:
        """Resolve a path relative to workspace root.

        Args:
            path: Path to resolve (absolute or relative)

        Returns:
            Resolved absolute path

        Raises:
            WorkspaceConfinementError: If resolved path is outside workspace
        """
        path_obj = Path(path)

        if path_obj.is_absolute():
            resolved = path_obj.resolve()
        else:
            resolved = (self._workspace_root / path_obj).resolve()

        # Check confinement
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            raise WorkspaceConfinementError(resolved, self._workspace_root) from None

        return resolved

    def _check_cwd_confinement(self, cwd: Path | None) -> Path:
        """Check that working directory is within workspace.

        Args:
            cwd: Working directory to check (None means workspace root)

        Returns:
            Validated working directory path

        Raises:
            WorkspaceConfinementError: If cwd is outside workspace
        """
        if cwd is None:
            return self._workspace_root

        resolved_cwd = cwd.resolve()
        try:
            resolved_cwd.relative_to(self._workspace_root)
        except ValueError:
            raise WorkspaceConfinementError(resolved_cwd, self._workspace_root) from None

        return resolved_cwd

    def run_command(
        self,
        argv: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        """Execute a command with tokenized arguments.

        Args:
            argv: Command and arguments as a list (no shell interpretation)
            cwd: Working directory (must be within workspace, default: workspace root)
            timeout: Timeout in seconds (default: engine default)

        Returns:
            CommandResult with captured output and exit code

        Raises:
            WorkspaceConfinementError: If cwd is outside workspace
            ValueError: If argv is empty
        """
        if not argv:
            raise ValueError("argv cannot be empty")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        validated_cwd = self._check_cwd_confinement(cwd)

        import time

        start_time = time.monotonic()
        timed_out = False
        exit_code = -1
        stdout = ""
        stderr = ""

        try:
            result = subprocess.run(
                argv,
                cwd=validated_cwd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                shell=False,  # Explicit: no shell interpretation
            )
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
        except subprocess.TimeoutExpired as e:
            timed_out = True
            exit_code = -1
            stdout = e.stdout if e.stdout else ""
            stderr = e.stderr if e.stderr else ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
        except FileNotFoundError:
            exit_code = 127  # Standard "command not found" exit code
            stderr = f"Command not found: {argv[0]}"

        end_time = time.monotonic()
        duration_ms = int((end_time - start_time) * 1000)

        command_result = CommandResult(
            argv=tuple(argv),
            cwd=str(validated_cwd),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            duration_ms=duration_ms,
        )

        self._log_command(command_result)
        return command_result

    def write_file(
        self,
        path: str | Path,
        content: str,
    ) -> WriteResult:
        """Write content to a file within the workspace.

        Args:
            path: Path to write (absolute or relative to workspace root)
            content: Content to write

        Returns:
            WriteResult with diff summary

        Raises:
            WorkspaceConfinementError: If path is outside workspace
        """
        resolved_path = self._resolve_path(path)

        # Capture state before write
        hash_before: str | None = None
        size_before: int | None = None

        if resolved_path.exists():
            try:
                existing_content = resolved_path.read_bytes()
                hash_before = hashlib.sha256(existing_content).hexdigest()
                size_before = len(existing_content)
            except OSError:
                # File exists but couldn't read - treat as new file
                pass

        # Perform write
        try:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            content_bytes = content.encode("utf-8")
            resolved_path.write_bytes(content_bytes)

            hash_after = hashlib.sha256(content_bytes).hexdigest()
            size_after = len(content_bytes)

            result = WriteResult(
                path=str(resolved_path),
                success=True,
                bytes_written=size_after,
                hash_before=hash_before,
                hash_after=hash_after,
                size_before=size_before,
                size_after=size_after,
            )
        except OSError as e:
            result = WriteResult(
                path=str(resolved_path),
                success=False,
                bytes_written=0,
                hash_before=hash_before,
                hash_after=None,
                size_before=size_before,
                size_after=None,
                error=str(e),
            )

        self._log_write(result)
        return result

    def read_file(self, path: str | Path) -> str:
        """Read content from a file within the workspace.

        Args:
            path: Path to read (absolute or relative to workspace root)

        Returns:
            File content as string

        Raises:
            WorkspaceConfinementError: If path is outside workspace
            FileNotFoundError: If file does not exist
        """
        resolved_path = self._resolve_path(path)
        return resolved_path.read_text(encoding="utf-8")

    def _log_command(self, result: CommandResult) -> None:
        """Log a command execution to execution.ndjson."""
        if self._execution_log is None:
            return

        self._execution_log.append(
            event="run_command",
            node_id=None,
            payload=result.to_dict(),
        )

    def _log_write(self, result: WriteResult) -> None:
        """Log a file write to execution.ndjson."""
        if self._execution_log is None:
            return

        self._execution_log.append(
            event="write_file",
            node_id=None,
            payload=result.to_dict(),
        )
