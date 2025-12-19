"""State management for Substrate runtime.

Manages the .substrate directory structure:
    .substrate/
        config.json
        state/
            active.json
            nodes/
                <node_id>.json
        logs/
            events.ndjson
"""

import json
import secrets
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

        # Create directory structure
        self._substrate_dir.mkdir(parents=True, exist_ok=True)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._nodes_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

        # Initialize event log
        self.event_log.ensure_exists()

        # Create initial configuration
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

        # Create root node
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

        # Set active state
        active = ActiveState(
            active_node_id=node_id,
            active_workspace_path=str(self._root),
            last_updated=now,
        )
        self._write_active(active)

        # Log initialization
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
