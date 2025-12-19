"""CLI command implementations.

Each command is a function that returns an exit code.
Commands are explicit, logged, and side-effect free where possible.
"""

import sys
from pathlib import Path

from substrate.runtime.state import SubstrateState
from substrate.runtime.types import PermissionLevel


def init_command(workspace_path: Path) -> int:
    """Initialize a Substrate workspace.

    Creates the .substrate directory structure and initial node.
    Idempotent: safe to run multiple times.

    Args:
        workspace_path: Root directory for the workspace.

    Returns:
        Exit code (0 for success).
    """
    state = SubstrateState(workspace_path)
    success, message = state.initialize()

    print(message)
    return 0 if success else 1


def status_command(workspace_path: Path) -> int:
    """Display current workspace status.

    Shows active node, workspace path, mode, and permission level.
    This command is side-effect free.

    Args:
        workspace_path: Root directory for the workspace.

    Returns:
        Exit code (0 for success, 1 if not initialized).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    config = state.load_config()
    active = state.load_active()

    if config is None or active is None:
        print("Error: Failed to load Substrate state", file=sys.stderr)
        return 1

    node = state.load_node(active.active_node_id)
    if node is None:
        print(f"Error: Active node {active.active_node_id} not found", file=sys.stderr)
        return 1

    # Get permission level
    perm_level = node.permissions_snapshot.get("level", 0)
    perm_name = _permission_level_name(perm_level)

    # Log status check
    state.event_log.append(
        event="status",
        node_id=active.active_node_id,
        payload={},
    )

    # Display status
    print("Substrate Status")
    print("=" * 40)
    print(f"Active node:      {active.active_node_id}")
    print(f"Workspace path:   {active.active_workspace_path}")
    print(f"Mode:             {node.mode}")
    print(f"Permission level: {perm_level} ({perm_name})")
    print(f"Last updated:     {active.last_updated}")

    if node.directive:
        print(f"Directive:        {node.directive}")

    # Oracle summary if present
    if node.oracle_summary:
        print("\nOracle Summary:")
        for oracle_type in node.oracle_summary:
            summary = node.oracle_summary[oracle_type]
            if isinstance(summary, dict) and "ok" in summary:
                status = "✓" if summary["ok"] else "✗"
                print(f"  {oracle_type}: {status}")
    else:
        print("\nOracle Summary:   (none)")

    return 0


def _permission_level_name(level: int) -> str:
    """Get human-readable name for permission level."""
    names: dict[int, str] = {
        PermissionLevel.OBSERVE: "observe",
        PermissionLevel.PER_ACTION: "per-action",
        PermissionLevel.SCOPED_PHASE: "scoped-phase",
        PermissionLevel.CONDITIONAL: "conditional",
        PermissionLevel.TRUSTED: "trusted",
    }
    return names.get(level, "unknown")
