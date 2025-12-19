"""Iteration loop controller.

Orchestrates the execution of phases in sequence:
orient → propose → authorize → execute → observe → reconcile → decide

Each phase is logged to runtime.ndjson. A new node is created per step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from substrate.iteration.phases import (
    AuthorizePhase,
    DecidePhase,
    ExecutePhase,
    ObservePhase,
    OrientPhase,
    Phase,
    PhaseResult,
    PhaseStatus,
    ProposePhase,
    ReconcilePhase,
)
from substrate.iteration.proposal import ProposalStub, StubProposal
from substrate.runtime.state import SubstrateState, generate_node_id
from substrate.runtime.types import ActiveState, NodeRecord, utc_now_iso
from substrate.tools.permissions import PermissionGate
from substrate.tools.registry import ToolRegistry
from substrate.tools.schemas import PermissionLevel


def _default_phase_results() -> list[PhaseResult]:
    """Default factory for phase_results field."""
    return []


@dataclass
class IterationResult:
    """Result of a complete iteration.

    Attributes:
        success: Whether the iteration completed successfully
        decision: Final decision (complete/continue/failed/denied)
        new_node_id: ID of the newly created node
        phase_results: Results from each phase
        error: Error message if iteration failed
    """

    success: bool
    decision: str
    new_node_id: str | None
    phase_results: list[PhaseResult] = field(default_factory=_default_phase_results)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "success": self.success,
            "decision": self.decision,
            "new_node_id": self.new_node_id,
            "phase_results": [pr.to_dict() for pr in self.phase_results],
            "error": self.error,
        }


class IterationLoop:
    """Controller for the iteration loop.

    Executes phases in sequence and creates a new node with results.
    """

    def __init__(
        self,
        state: SubstrateState,
        registry: ToolRegistry | None = None,
        permission_level: PermissionLevel = PermissionLevel.ACT_EXTERNAL,
        proposal_stub: StubProposal | None = None,
    ) -> None:
        """Initialize the iteration loop.

        Args:
            state: Substrate state manager
            registry: Tool registry (uses default if None)
            permission_level: Current permission level
            proposal_stub: Stub proposal to use (defaults to pytest)
        """
        self._state = state

        if registry is None:
            from substrate.tools.registry import create_default_registry

            registry = create_default_registry()
        self._registry = registry

        self._gate = PermissionGate(
            registry=self._registry,
            event_log_path=state.event_log.path,
            initial_level=permission_level,
        )

        if proposal_stub is None:
            proposal_stub = ProposalStub.run_pytest()
        self._proposal_stub = proposal_stub

    def step(self) -> IterationResult:
        """Execute a single iteration step.

        Returns:
            IterationResult with phase outcomes and new node ID
        """
        context: dict[str, Any] = {}
        phase_results: list[PhaseResult] = []

        # Define phases in order
        phases: list[Phase] = [
            OrientPhase(self._state),
            ProposePhase(self._proposal_stub),
            AuthorizePhase(self._gate),
            ExecutePhase(self._state),
            ObservePhase(),
            ReconcilePhase(self._state),
            DecidePhase(),
        ]

        # Execute each phase
        for phase in phases:
            result = phase.execute(context)
            phase_results.append(result)
            self._log_phase(phase.name, result, context)

            # Stop on critical failures
            if result.status == PhaseStatus.FAILED:
                return IterationResult(
                    success=False,
                    decision="failed",
                    new_node_id=None,
                    phase_results=phase_results,
                    error=result.error,
                )

            # Stop on authorization denial but create node
            if result.status == PhaseStatus.DENIED:
                new_node_id = self._create_step_node(context, phase_results)
                return IterationResult(
                    success=False,
                    decision="denied",
                    new_node_id=new_node_id,
                    phase_results=phase_results,
                    error=result.error,
                )

        # Create new node with results
        new_node_id = self._create_step_node(context, phase_results)

        decision = context.get("decision", "unknown")
        success = decision == "complete"

        return IterationResult(
            success=success,
            decision=decision,
            new_node_id=new_node_id,
            phase_results=phase_results,
        )

    def _create_step_node(self, context: dict[str, Any], phase_results: list[PhaseResult]) -> str:
        """Create a new node recording the step results.

        Args:
            context: Iteration context with results
            phase_results: Results from all phases

        Returns:
            ID of the new node
        """
        active = self._state.load_active()
        if active is None:
            raise RuntimeError("No active state")

        parent_node = self._state.load_node(active.active_node_id)
        if parent_node is None:
            raise RuntimeError(f"Parent node {active.active_node_id} not found")

        new_node_id = generate_node_id()
        now = utc_now_iso()

        # Get workspace path
        workspace_path = self._state.get_workspace_path(parent_node.node_id)

        # Build oracle summary from context
        oracle_summary = context.get("oracle_summary", parent_node.oracle_summary)

        # Build notes from phase results
        phase_summary = ", ".join(f"{pr.phase_name}:{pr.status.value}" for pr in phase_results)
        decision = context.get("decision", "unknown")
        notes = f"Step result: {decision}. Phases: {phase_summary}"

        new_node = NodeRecord(
            node_id=new_node_id,
            parent_node_id=parent_node.node_id,
            created_at=now,
            mode=parent_node.mode,
            directive=parent_node.directive,
            workspace_path=str(workspace_path),
            patch_path=None,
            oracle_summary=oracle_summary,
            permissions_snapshot=parent_node.permissions_snapshot.copy(),
            promotion_status="none",
            notes=notes,
        )

        # Write node using public method
        self._state.save_node(new_node)

        # Update active state using public method
        new_active = ActiveState(
            active_node_id=new_node_id,
            active_workspace_path=str(workspace_path),
            last_updated=now,
        )
        self._state.save_active(new_active)

        # Log node creation
        self._state.event_log.append(
            event="step_node_created",
            node_id=new_node_id,
            payload={
                "parent_node_id": parent_node.node_id,
                "decision": decision,
                "oracle_summary": oracle_summary,
            },
        )

        return new_node_id

    def _log_phase(self, phase_name: str, result: PhaseResult, context: dict[str, Any]) -> None:
        """Log phase execution to runtime.ndjson.

        Args:
            phase_name: Name of the phase
            result: Phase result
            context: Current iteration context
        """
        node_id = context.get("node_id")

        self._state.event_log.append(
            event=f"phase_{phase_name}",
            node_id=node_id,
            payload=result.to_dict(),
        )
