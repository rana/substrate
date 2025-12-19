"""Core type definitions for Substrate runtime."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any


class PermissionLevel(IntEnum):
    """Permission levels for Substrate operations.

    Level 0: Observation only - read files, inspect, propose
    Level 1: Per-action authorization - each action requires approval
    Level 2: Scoped phase authorization - bounded set of actions
    Level 3: Conditional delegation - actions satisfying constraints
    Level 4: Local trusted operation - broad execution, fully logged
    """

    OBSERVE = 0
    PER_ACTION = 1
    SCOPED_PHASE = 2
    CONDITIONAL = 3
    TRUSTED = 4


class TaskMode:
    """Task modes that influence iteration behavior."""

    MANUAL = "manual"
    GREENFIELD = "greenfield"
    FEATURE = "feature"
    REFACTOR = "refactor"


@dataclass
class NodeRecord:
    """Immutable record of a workspace node.

    Each node represents a concrete filesystem state with associated metadata.
    Nodes are immutable once recorded.
    """

    node_id: str
    parent_node_id: str | None
    created_at: str
    mode: str
    directive: str
    workspace_path: str
    patch_path: str | None
    oracle_summary: dict[str, Any]  # e.g., {"tests": {"ok": True, "passed": 5}}
    permissions_snapshot: dict[str, int]  # e.g., {"level": 0}
    promotion_status: str  # "none" | "promoted"
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "node_id": self.node_id,
            "parent_node_id": self.parent_node_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "directive": self.directive,
            "workspace_path": self.workspace_path,
            "patch_path": self.patch_path,
            "oracle_summary": self.oracle_summary,
            "permissions_snapshot": self.permissions_snapshot,
            "promotion_status": self.promotion_status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeRecord:
        """Create NodeRecord from dictionary."""
        return cls(
            node_id=str(data["node_id"]),
            parent_node_id=data.get("parent_node_id"),
            created_at=str(data["created_at"]),
            mode=str(data["mode"]),
            directive=str(data["directive"]),
            workspace_path=str(data["workspace_path"]),
            patch_path=data.get("patch_path"),
            oracle_summary=data.get("oracle_summary", {}),
            permissions_snapshot=data.get("permissions_snapshot", {"level": 0}),
            promotion_status=str(data.get("promotion_status", "none")),
            notes=data.get("notes"),
        )


@dataclass
class ActiveState:
    """Current active workspace state."""

    active_node_id: str
    active_workspace_path: str
    last_updated: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "active_node_id": self.active_node_id,
            "active_workspace_path": self.active_workspace_path,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActiveState:
        """Create ActiveState from dictionary."""
        return cls(
            active_node_id=str(data["active_node_id"]),
            active_workspace_path=str(data["active_workspace_path"]),
            last_updated=str(data["last_updated"]),
        )


def _default_oracles() -> dict[str, Any]:
    """Default factory for oracles field."""
    return {}


def _default_safety() -> dict[str, Any]:
    """Default factory for safety field."""
    return {
        "allow_shell": True,
        "max_command_seconds": 300,
    }


@dataclass
class Config:
    """Substrate configuration."""

    project_root: str
    default_mode: str
    cli_name: str
    oracles: dict[str, Any] = field(default_factory=_default_oracles)
    safety: dict[str, Any] = field(default_factory=_default_safety)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "project_root": self.project_root,
            "default_mode": self.default_mode,
            "cli_name": self.cli_name,
            "oracles": self.oracles,
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create Config from dictionary."""
        return cls(
            project_root=str(data["project_root"]),
            default_mode=str(data["default_mode"]),
            cli_name=str(data["cli_name"]),
            oracles=data.get("oracles", {}),
            safety=data.get("safety", {"allow_shell": True, "max_command_seconds": 300}),
        )


def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(UTC).isoformat()
