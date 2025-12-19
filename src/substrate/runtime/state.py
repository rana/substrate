"""State management for Substrate runtime.

Manages the .substrate directory structure:
    .substrate/
        config.json
        state/
            active.json
            nodes/
                <node_id>.json
        workspaces/
            <node_id>/
                ...project files...
        logs/
            events.ndjson
"""

import json
import secrets
import shutil
from pathlib import Path
from typing import Any

from substrate.runtime.logging import EventLog
from substrate.runtime.types import (
    ActiveState,
    Config,
    NodeRecord,
    TaskMode,
    utc_now_iso,
)

SUBSTRATE_DIR = ".substrate"
CONFIG_FILE = "config.json"
STATE_DIR = "state"
ACTIVE_FILE = "active.json"
NODES_DIR = "nodes"
WORKSPACES_DIR = "workspaces"
LOGS_DIR = "logs"
EVENTS_LOG = "events.ndjson"


def generate_node_id() -> str:
    """Generate a unique node identifier.

    Uses 8 bytes of randomness (16 hex chars) which provides
    sufficient collision resistance for local single-user operation.
    """
    return secrets.token_hex(8)


class SubstrateState:
    """Manages Substrate workspace state.

    Provides access to configuration, active state, nodes, and event logging.
    All state operations are explicit and logged.
    """

    def __init__(self, workspace_root: Path) -> None:
        """Initialize state manager.

        Args:
            workspace_root: Root directory of the workspace.
        """
        self._root = workspace_root.resolve()
        self._substrate_dir = self._root / SUBSTRATE_DIR
        self._config_path = self._substrate_dir / CONFIG_FILE
        self._state_dir = self._substrate_dir / STATE_DIR
        self._active_path = self._state_dir / ACTIVE_FILE
        self._nodes_dir = self._state_dir / NODES_DIR
        self._workspaces_dir = self._substrate_dir / WORKSPACES_DIR
        self._logs_dir = self._substrate_dir / LOGS_DIR
        self._events_log_path = self._logs_dir / EVENTS_LOG

        self._event_log: EventLog | None = None

    @property
    def root(self) -> Path:
        """Return workspace root path."""
        return self._root

    @property
    def substrate_dir(self) -> Path:
        """Return .substrate directory path."""
        return self._substrate_dir

    @property
    def workspaces_dir(self) -> Path:
        """Return workspaces directory path."""
        return self._workspaces_dir

    @property
    def event_log(self) -> EventLog:
        """Return event log instance."""
        if self._event_log is None:
            self._event_log = EventLog(self._events_log_path)
        return self._event_log

    def is_initialized(self) -> bool:
        """Check if workspace is already initialized."""
        return self._config_path.exists()

    def initialize(self) -> tuple[bool, str]:
        """Initialize the Substrate workspace.

        Creates the directory structure and initial node.
        Idempotent: safe to call multiple times.

        Returns:
            Tuple of (success, message).
        """
        if self.is_initialized():
            self.event_log.ensure_exists()
            self.event_log.append(
                event="init_skipped",
                node_id=None,
                payload={"reason": "already_initialized"},
            )
            return True, f"Substrate already initialized at {self._substrate_dir}"

        self._substrate_dir.mkdir(parents=True, exist_ok=True)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._nodes_dir.mkdir(parents=True, exist_ok=True)
        self._workspaces_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

        self.event_log.ensure_exists()

        config = Config(
            project_root=str(self._root),
            default_mode=TaskMode.MANUAL,
            cli_name="sub",
            oracles={
                "python": {
                    "test_command": ["uv", "run", "pytest", "-q"],
                    "lint_command": ["uv", "run", "ruff", "check", "."],
                    "format_command": ["uv", "run", "ruff", "format", "."],
                    "typecheck_command": ["uv", "run", "pyright"],
                }
            },
            safety={
                "allow_shell": True,
                "max_command_seconds": 300,
            },
        )
        self._write_config(config)

        node_id = generate_node_id()
        now = utc_now_iso()

        root_node = NodeRecord(
            node_id=node_id,
            parent_node_id=None,
            created_at=now,
            mode=TaskMode.MANUAL,
            directive="",
            workspace_path=str(self._root),
            patch_path=None,
            oracle_summary={},
            permissions_snapshot={"level": 0},
            promotion_status="none",
            notes="Initial root node",
        )
        self._write_node(root_node)

        active = ActiveState(
            active_node_id=node_id,
            active_workspace_path=str(self._root),
            last_updated=now,
        )
        self._write_active(active)

        self.event_log.append(
            event="init",
            node_id=node_id,
            payload={
                "workspace_root": str(self._root),
                "substrate_dir": str(self._substrate_dir),
            },
        )

        return True, f"Substrate initialized at {self._substrate_dir}"

    def load_config(self) -> Config | None:
        """Load configuration from disk."""
        if not self._config_path.exists():
            return None

        with self._config_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return Config.from_dict(data)

    def load_active(self) -> ActiveState | None:
        """Load active state from disk."""
        if not self._active_path.exists():
            return None

        with self._active_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return ActiveState.from_dict(data)

    def load_node(self, node_id: str) -> NodeRecord | None:
        """Load a node record from disk."""
        node_path = self._nodes_dir / f"{node_id}.json"
        if not node_path.exists():
            return None

        with node_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return NodeRecord.from_dict(data)

    def list_nodes(self) -> list[str]:
        """List all node IDs in the workspace."""
        if not self._nodes_dir.exists():
            return []
        return [p.stem for p in self._nodes_dir.glob("*.json")]

    def node_exists(self, node_id: str) -> bool:
        """Check if a node exists."""
        node_path = self._nodes_dir / f"{node_id}.json"
        return node_path.exists()

    def get_workspace_path(self, node_id: str) -> Path:
        """Get the workspace directory path for a node.

        For the root node, returns the repository root.
        For child nodes, returns the workspace copy under .substrate/workspaces/.
        """
        node = self.load_node(node_id)
        if node is None:
            return self._workspaces_dir / node_id

        # Root node uses repository root
        if node.parent_node_id is None:
            return self._root

        # Child nodes use workspace copies
        return self._workspaces_dir / node_id

    def create_branch(self, parent_node_id: str) -> tuple[bool, str, str | None]:
        """Create a new branch from a parent node.

        Creates a child workspace by copying the parent workspace.

        Args:
            parent_node_id: ID of the parent node to branch from.

        Returns:
            Tuple of (success, message, new_node_id or None).
        """
        parent_node = self.load_node(parent_node_id)
        if parent_node is None:
            return False, f"Parent node {parent_node_id} not found", None

        # Generate new node ID
        new_node_id = generate_node_id()
        now = utc_now_iso()

        # Determine source workspace path
        source_workspace = self.get_workspace_path(parent_node_id)

        # Create workspace copy
        new_workspace_path = self._workspaces_dir / new_node_id
        self._copy_workspace(source_workspace, new_workspace_path)

        # Create new node record
        new_node = NodeRecord(
            node_id=new_node_id,
            parent_node_id=parent_node_id,
            created_at=now,
            mode=parent_node.mode,
            directive=parent_node.directive,
            workspace_path=str(new_workspace_path),
            patch_path=None,
            oracle_summary={},
            permissions_snapshot=parent_node.permissions_snapshot.copy(),
            promotion_status="none",
            notes=f"Branched from {parent_node_id}",
        )
        self._write_node(new_node)

        # Update active state
        active = ActiveState(
            active_node_id=new_node_id,
            active_workspace_path=str(new_workspace_path),
            last_updated=now,
        )
        self._write_active(active)

        # Log event
        self.event_log.append(
            event="branch",
            node_id=new_node_id,
            payload={
                "parent_node_id": parent_node_id,
                "workspace_path": str(new_workspace_path),
            },
        )

        return True, f"Created branch {new_node_id} from {parent_node_id}", new_node_id

    def rollback(self, target_node_id: str) -> tuple[bool, str]:
        """Switch active state to a different node.

        Does not delete any history or workspaces.

        Args:
            target_node_id: ID of the node to switch to.

        Returns:
            Tuple of (success, message).
        """
        target_node = self.load_node(target_node_id)
        if target_node is None:
            return False, f"Node {target_node_id} not found"

        now = utc_now_iso()
        workspace_path = self.get_workspace_path(target_node_id)

        # Verify workspace exists
        if not workspace_path.exists():
            return False, f"Workspace for node {target_node_id} not found at {workspace_path}"

        # Get current active for logging
        current_active = self.load_active()
        previous_node_id = current_active.active_node_id if current_active else None

        # Update active state
        active = ActiveState(
            active_node_id=target_node_id,
            active_workspace_path=str(workspace_path),
            last_updated=now,
        )
        self._write_active(active)

        # Log event
        self.event_log.append(
            event="rollback",
            node_id=target_node_id,
            payload={
                "previous_node_id": previous_node_id,
                "workspace_path": str(workspace_path),
            },
        )

        return True, f"Rolled back to node {target_node_id}"

    def promote(self, target_node_id: str) -> tuple[bool, str]:
        """Mark a node as promoted and make it active.

        Promotion marks the node as the new trunk.

        Args:
            target_node_id: ID of the node to promote.

        Returns:
            Tuple of (success, message).
        """
        target_node = self.load_node(target_node_id)
        if target_node is None:
            return False, f"Node {target_node_id} not found"

        if target_node.promotion_status == "promoted":
            return True, f"Node {target_node_id} is already promoted"

        now = utc_now_iso()
        workspace_path = self.get_workspace_path(target_node_id)

        # Verify workspace exists
        if not workspace_path.exists():
            return False, f"Workspace for node {target_node_id} not found at {workspace_path}"

        # Update node record with promotion status
        promoted_node = NodeRecord(
            node_id=target_node.node_id,
            parent_node_id=target_node.parent_node_id,
            created_at=target_node.created_at,
            mode=target_node.mode,
            directive=target_node.directive,
            workspace_path=target_node.workspace_path,
            patch_path=target_node.patch_path,
            oracle_summary=target_node.oracle_summary,
            permissions_snapshot=target_node.permissions_snapshot,
            promotion_status="promoted",
            notes=target_node.notes,
        )
        self._write_node(promoted_node)

        # Update active state
        active = ActiveState(
            active_node_id=target_node_id,
            active_workspace_path=str(workspace_path),
            last_updated=now,
        )
        self._write_active(active)

        # Log event
        self.event_log.append(
            event="promote",
            node_id=target_node_id,
            payload={
                "workspace_path": str(workspace_path),
            },
        )

        return True, f"Promoted node {target_node_id}"

    def compare_nodes(
        self, node_a_id: str, node_b_id: str
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Compare two nodes.

        Returns diff statistics between the two workspaces.

        Args:
            node_a_id: ID of the first node.
            node_b_id: ID of the second node.

        Returns:
            Tuple of (success, message, comparison_data or None).
        """
        node_a = self.load_node(node_a_id)
        if node_a is None:
            return False, f"Node {node_a_id} not found", None

        node_b = self.load_node(node_b_id)
        if node_b is None:
            return False, f"Node {node_b_id} not found", None

        workspace_a = self.get_workspace_path(node_a_id)
        workspace_b = self.get_workspace_path(node_b_id)

        if not workspace_a.exists():
            return False, f"Workspace for node {node_a_id} not found", None

        if not workspace_b.exists():
            return False, f"Workspace for node {node_b_id} not found", None

        # Collect file differences
        comparison = self._compute_diff_stats(workspace_a, workspace_b)

        # Log event
        self.event_log.append(
            event="compare",
            node_id=None,
            payload={
                "node_a_id": node_a_id,
                "node_b_id": node_b_id,
                "summary": {
                    "files_only_in_a": len(comparison["only_in_a"]),
                    "files_only_in_b": len(comparison["only_in_b"]),
                    "files_modified": len(comparison["modified"]),
                    "files_identical": len(comparison["identical"]),
                },
            },
        )

        return True, "Comparison complete", comparison

    def _copy_workspace(self, source: Path, destination: Path) -> None:
        """Copy workspace directory, excluding .substrate.

        Args:
            source: Source directory path.
            destination: Destination directory path.
        """
        destination.mkdir(parents=True, exist_ok=True)

        for item in source.iterdir():
            # Skip .substrate directory
            if item.name == SUBSTRATE_DIR:
                continue

            dest_item = destination / item.name
            if item.is_dir():
                shutil.copytree(item, dest_item, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest_item)

    def _compute_diff_stats(
        self, workspace_a: Path, workspace_b: Path
    ) -> dict[str, list[str]]:
        """Compute diff statistics between two workspaces.

        Args:
            workspace_a: First workspace path.
            workspace_b: Second workspace path.

        Returns:
            Dictionary with keys: only_in_a, only_in_b, modified, identical
        """
        files_a = self._list_files_relative(workspace_a)
        files_b = self._list_files_relative(workspace_b)

        only_in_a: list[str] = []
        only_in_b: list[str] = []
        modified: list[str] = []
        identical: list[str] = []

        all_files = files_a | files_b

        for rel_path in sorted(all_files):
            in_a = rel_path in files_a
            in_b = rel_path in files_b

            if in_a and not in_b:
                only_in_a.append(rel_path)
            elif in_b and not in_a:
                only_in_b.append(rel_path)
            else:
                # Both exist, compare contents
                path_a = workspace_a / rel_path
                path_b = workspace_b / rel_path

                if self._files_identical(path_a, path_b):
                    identical.append(rel_path)
                else:
                    modified.append(rel_path)

        return {
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "modified": modified,
            "identical": identical,
        }

    def _list_files_relative(self, workspace: Path) -> set[str]:
        """List all files in workspace relative to workspace root.

        Excludes .substrate directory.
        """
        files: set[str] = set()
        for path in workspace.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(workspace)
                # Skip .substrate directory
                if rel_path.parts and rel_path.parts[0] == SUBSTRATE_DIR:
                    continue
                files.add(str(rel_path))
        return files

    def _files_identical(self, path_a: Path, path_b: Path) -> bool:
        """Check if two files have identical contents."""
        try:
            return path_a.read_bytes() == path_b.read_bytes()
        except OSError:
            return False

    def _write_config(self, config: Config) -> None:
        """Write configuration to disk."""
        with self._config_path.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
            f.write("\n")

    def _write_active(self, active: ActiveState) -> None:
        """Write active state to disk."""
        with self._active_path.open("w", encoding="utf-8") as f:
            json.dump(active.to_dict(), f, indent=2)
            f.write("\n")

    def _write_node(self, node: NodeRecord) -> None:
        """Write node record to disk."""
        node_path = self._nodes_dir / f"{node.node_id}.json"
        with node_path.open("w", encoding="utf-8") as f:
            json.dump(node.to_dict(), f, indent=2)
            f.write("\n")
