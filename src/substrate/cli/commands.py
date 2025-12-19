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

    perm_level = node.permissions_snapshot.get("level", 0)
    perm_name = _permission_level_name(perm_level)

    state.event_log.append(
        event="status",
        node_id=active.active_node_id,
        payload={},
    )

    print("Substrate Status")
    print("=" * 40)
    print(f"Active node:      {active.active_node_id}")
    print(f"Workspace path:   {active.active_workspace_path}")
    print(f"Mode:             {node.mode}")
    print(f"Permission level: {perm_level} ({perm_name})")
    print(f"Promotion status: {node.promotion_status}")
    print(f"Parent node:      {node.parent_node_id or '(none - root)'}")
    print(f"Last updated:     {active.last_updated}")

    if node.directive:
        print(f"Directive:        {node.directive}")

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


def branch_command(workspace_path: Path) -> int:
    """Create a new branch from the current node.

    Creates a child workspace by copying the parent workspace.
    The new branch becomes the active node.

    Args:
        workspace_path: Root directory for the workspace.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    active = state.load_active()
    if active is None:
        print("Error: Failed to load active state", file=sys.stderr)
        return 1

    success, message, new_node_id = state.create_branch(active.active_node_id)

    if success:
        print(message)
        print(f"New active node: {new_node_id}")
    else:
        print(f"Error: {message}", file=sys.stderr)

    return 0 if success else 1


def rollback_command(workspace_path: Path, target_node_id: str) -> int:
    """Switch active state to a different node.

    Does not delete any history or workspaces.

    Args:
        workspace_path: Root directory for the workspace.
        target_node_id: ID of the node to switch to.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    success, message = state.rollback(target_node_id)

    if success:
        print(message)
    else:
        print(f"Error: {message}", file=sys.stderr)

    return 0 if success else 1


def promote_command(workspace_path: Path, target_node_id: str) -> int:
    """Mark a node as promoted and make it active.

    Promotion marks the node as the new trunk.

    Args:
        workspace_path: Root directory for the workspace.
        target_node_id: ID of the node to promote.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    success, message = state.promote(target_node_id)

    if success:
        print(message)
    else:
        print(f"Error: {message}", file=sys.stderr)

    return 0 if success else 1


def compare_command(workspace_path: Path, node_a_id: str, node_b_id: str) -> int:
    """Compare two nodes.

    Shows diff statistics between the two workspaces.

    Args:
        workspace_path: Root directory for the workspace.
        node_a_id: ID of the first node.
        node_b_id: ID of the second node.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    success, message, comparison = state.compare_nodes(node_a_id, node_b_id)

    if not success or comparison is None:
        print(f"Error: {message}", file=sys.stderr)
        return 1

    print(f"Comparison: {node_a_id} vs {node_b_id}")
    print("=" * 50)

    only_in_a: list[str] = comparison["only_in_a"]
    only_in_b: list[str] = comparison["only_in_b"]
    modified: list[str] = comparison["modified"]
    identical: list[str] = comparison["identical"]

    print(f"\nFiles only in {node_a_id[:8]}...: {len(only_in_a)}")
    for f in only_in_a[:10]:
        print(f"  - {f}")
    if len(only_in_a) > 10:
        print(f"  ... and {len(only_in_a) - 10} more")

    print(f"\nFiles only in {node_b_id[:8]}...: {len(only_in_b)}")
    for f in only_in_b[:10]:
        print(f"  + {f}")
    if len(only_in_b) > 10:
        print(f"  ... and {len(only_in_b) - 10} more")

    print(f"\nModified files: {len(modified)}")
    for f in modified[:10]:
        print(f"  ~ {f}")
    if len(modified) > 10:
        print(f"  ... and {len(modified) - 10} more")

    print(f"\nIdentical files: {len(identical)}")

    total_changes = len(only_in_a) + len(only_in_b) + len(modified)
    if total_changes == 0:
        print("\nWorkspaces are identical.")

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
