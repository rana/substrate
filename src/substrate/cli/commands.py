"""CLI command implementations.

Each command is a function that returns an exit code.
Commands are explicit, logged, and side-effect free where possible.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from substrate.runtime.state import SubstrateState
from substrate.runtime.types import NodeRecord, PermissionLevel

if TYPE_CHECKING:
    from substrate.iteration.proposal import StubProposal


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


def orient_command(workspace_path: Path, directive: str) -> int:
    """Set or update the task directive for the active node.

    Updates the directive field of the current node and logs the orientation.

    Args:
        workspace_path: Root directory for the workspace.
        directive: Task directive text.

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

    node = state.load_node(active.active_node_id)
    if node is None:
        print(f"Error: Node {active.active_node_id} not found", file=sys.stderr)
        return 1

    # Update node with new directive
    updated_node = NodeRecord(
        node_id=node.node_id,
        parent_node_id=node.parent_node_id,
        created_at=node.created_at,
        mode=node.mode,
        directive=directive,
        workspace_path=node.workspace_path,
        patch_path=node.patch_path,
        oracle_summary=node.oracle_summary,
        permissions_snapshot=node.permissions_snapshot,
        promotion_status=node.promotion_status,
        notes=node.notes,
    )
    state.save_node(updated_node)

    # Log orientation
    state.event_log.append(
        event="orient",
        node_id=node.node_id,
        payload={"directive": directive},
    )

    print(f"Oriented node {node.node_id}")
    print(f"Directive: {directive}")
    return 0


def step_command(
    workspace_path: Path,
    proposal_type: str = "pytest",
) -> int:
    """Execute a single iteration step.

    Runs the full iteration loop: orient → propose → authorize →
    execute → observe → reconcile → decide.

    Creates a new node with the results.

    Args:
        workspace_path: Root directory for the workspace.
        proposal_type: Type of proposal stub to use (pytest, ruff, pyright).

    Returns:
        Exit code (0 for success/complete, 1 for failure/denied).
    """
    state = SubstrateState(workspace_path)

    if not state.is_initialized():
        print("Error: Substrate not initialized", file=sys.stderr)
        print(f"Run 'sub init' in {workspace_path} first", file=sys.stderr)
        return 1

    # Select proposal stub
    from substrate.iteration.proposal import ProposalStub

    proposal_stub: StubProposal
    if proposal_type == "ruff":
        proposal_stub = ProposalStub.run_ruff_check()
    elif proposal_type == "pyright":
        proposal_stub = ProposalStub.run_pyright()
    else:
        proposal_stub = ProposalStub.run_pytest()

    # Create and run iteration loop
    from substrate.iteration.loop import IterationLoop
    from substrate.tools.schemas import PermissionLevel as ToolPermissionLevel

    loop = IterationLoop(
        state=state,
        permission_level=ToolPermissionLevel.ACT_EXTERNAL,
        proposal_stub=proposal_stub,
    )

    print(f"Executing step with proposal: {proposal_stub.action}")
    print("-" * 40)

    result = loop.step()

    # Print phase results
    for pr in result.phase_results:
        status_icon = "✓" if pr.status.value == "success" else "✗"
        print(f"  {status_icon} {pr.phase_name}: {pr.status.value}")
        if pr.error:
            print(f"    Error: {pr.error}")

    print("-" * 40)
    print(f"Decision: {result.decision}")

    if result.new_node_id:
        print(f"New node: {result.new_node_id}")

    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)

    # Return 0 for complete, 1 for anything else
    return 0 if result.decision == "complete" else 1


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
