"""Phase definitions for the iteration loop.

Each phase has a single responsibility per 02-iteration-loop.md:
- Orient: Re-anchor in current reality and intent
- Propose: Suggest the next step (stubbed for M6)
- Authorize: Enforce authority and trust constraints
- Execute: Perform the authorized action
- Observe: Capture what actually happened
- Reconcile: Compare expected vs actual outcomes
- Decide: Determine how to proceed
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from substrate.iteration.proposal import StubProposal
    from substrate.runtime.execution import CommandResult
    from substrate.runtime.state import SubstrateState
    from substrate.tools.permissions import AuthorizationResult, PermissionGate


class PhaseStatus(Enum):
    """Status of a phase execution."""

    SUCCESS = "success"
    FAILED = "failed"
    DENIED = "denied"
    SKIPPED = "skipped"


def _default_data() -> dict[str, Any]:
    """Default factory for data field."""
    return {}


@dataclass
class PhaseResult:
    """Result of executing a phase.

    Attributes:
        phase_name: Name of the phase
        status: Execution status
        data: Phase-specific output data
        error: Error message if failed
    """

    phase_name: str
    status: PhaseStatus
    data: dict[str, Any] = field(default_factory=_default_data)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging."""
        return {
            "phase_name": self.phase_name,
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
        }


class Phase(ABC):
    """Abstract base class for iteration phases."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Phase name for logging."""
        ...

    @abstractmethod
    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Execute the phase.

        Args:
            context: Shared context dictionary passed between phases

        Returns:
            PhaseResult with status and output data
        """
        ...


class OrientPhase(Phase):
    """Orient phase: Re-anchor in current reality and intent.

    Loads the directive and assembles context for the iteration.
    """

    def __init__(self, state: SubstrateState) -> None:
        self._state = state

    @property
    def name(self) -> str:
        return "orient"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Load directive and current node state."""
        active = self._state.load_active()
        if active is None:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error="No active state found",
            )

        node = self._state.load_node(active.active_node_id)
        if node is None:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error=f"Node {active.active_node_id} not found",
            )

        # Populate context for subsequent phases
        context["node_id"] = node.node_id
        context["directive"] = node.directive
        context["mode"] = node.mode
        context["workspace_path"] = active.active_workspace_path
        context["oracle_summary"] = node.oracle_summary
        context["permission_level"] = node.permissions_snapshot.get("level", 0)

        return PhaseResult(
            phase_name=self.name,
            status=PhaseStatus.SUCCESS,
            data={
                "node_id": node.node_id,
                "directive": node.directive,
                "mode": node.mode,
            },
        )


class ProposePhase(Phase):
    """Propose phase: Suggest the next step.

    For M6, this is a deterministic stub that proposes running oracles.
    """

    def __init__(self, proposal_stub: StubProposal) -> None:
        self._stub = proposal_stub

    @property
    def name(self) -> str:
        return "propose"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Return a stubbed proposal."""
        proposal = self._stub.get_proposal(context)

        context["proposed_action"] = proposal["action"]
        context["proposed_tool"] = proposal["tool"]
        context["proposed_args"] = proposal["args"]

        return PhaseResult(
            phase_name=self.name,
            status=PhaseStatus.SUCCESS,
            data=proposal,
        )


class AuthorizePhase(Phase):
    """Authorize phase: Enforce authority and trust constraints.

    Checks if the proposed action is permitted at the current trust level.
    """

    def __init__(self, gate: PermissionGate) -> None:
        self._gate = gate

    @property
    def name(self) -> str:
        return "authorize"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Check authorization for the proposed tool."""
        tool_name = context.get("proposed_tool", "")
        if not tool_name:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error="No tool proposed",
            )

        result: AuthorizationResult = self._gate.authorize(tool_name)
        context["authorization"] = result

        if result.authorized:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data=result.to_dict(),
            )
        else:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.DENIED,
                data=result.to_dict(),
                error=result.reason,
            )


class ExecutePhase(Phase):
    """Execute phase: Perform the authorized action.

    Invokes the execution engine to run the proposed command.
    """

    def __init__(self, state: SubstrateState) -> None:
        self._state = state

    @property
    def name(self) -> str:
        return "execute"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Execute the proposed action."""
        from pathlib import Path

        from substrate.runtime.execution import ExecutionEngine

        authorization = context.get("authorization")
        if authorization is None or not authorization.authorized:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SKIPPED,
                error="Not authorized",
            )

        workspace_path = context.get("workspace_path", "")
        if not workspace_path:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error="No workspace path in context",
            )

        args = context.get("proposed_args", {})
        command = args.get("command", [])
        if not command:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error="No command specified",
            )

        # Create execution engine for the workspace
        engine = ExecutionEngine(
            workspace_root=Path(workspace_path),
            execution_log=self._state.event_log,
        )

        try:
            result: CommandResult = engine.run_command(
                argv=command,
                timeout=args.get("timeout", 60),
            )
            context["execution_result"] = result

            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data={
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "duration_ms": result.duration_ms,
                },
            )
        except Exception as e:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.FAILED,
                error=str(e),
            )


class ObservePhase(Phase):
    """Observe phase: Capture what actually happened.

    Extracts diagnostics and results from execution output.
    """

    @property
    def name(self) -> str:
        return "observe"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Capture execution results."""
        result = context.get("execution_result")
        if result is None:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SKIPPED,
                error="No execution result to observe",
            )

        # Parse basic test results from pytest output
        observation = self._parse_output(result)
        context["observation"] = observation

        return PhaseResult(
            phase_name=self.name,
            status=PhaseStatus.SUCCESS,
            data=observation,
        )

    def _parse_output(self, result: CommandResult) -> dict[str, Any]:
        """Parse execution output into structured observation."""
        stdout = result.stdout
        stderr = result.stderr

        # Basic pytest result parsing
        passed = 0
        failed = 0
        errors = 0

        # Look for pytest summary line: "X passed, Y failed"
        for line in stdout.split("\n"):
            if "passed" in line or "failed" in line or "error" in line:
                parts = line.lower().split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        with contextlib.suppress(ValueError):
                            passed = int(parts[i - 1])
                    elif part == "failed" and i > 0:
                        with contextlib.suppress(ValueError):
                            failed = int(parts[i - 1])
                    elif part == "error" in part and i > 0:
                        with contextlib.suppress(ValueError):
                            errors = int(parts[i - 1])

        return {
            "exit_code": result.exit_code,
            "success": result.exit_code == 0,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "stdout_lines": len(stdout.split("\n")),
            "stderr_lines": len(stderr.split("\n")),
        }


class ReconcilePhase(Phase):
    """Reconcile phase: Compare expected vs actual outcomes.

    Updates node metadata with oracle results.
    """

    def __init__(self, state: SubstrateState) -> None:
        self._state = state

    @property
    def name(self) -> str:
        return "reconcile"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Reconcile observation with expected outcomes."""
        observation = context.get("observation")
        if observation is None:
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SKIPPED,
                error="No observation to reconcile",
            )

        # Build oracle summary
        proposed_action = context.get("proposed_action", "unknown")
        oracle_type = "tests" if "test" in proposed_action.lower() else "analysis"

        oracle_summary: dict[str, Any] = {
            oracle_type: {
                "ok": observation.get("success", False),
                "passed": observation.get("passed", 0),
                "failed": observation.get("failed", 0),
                "errors": observation.get("errors", 0),
            }
        }
        context["oracle_summary"] = oracle_summary

        # Determine if we met expectations
        success = observation.get("success", False)
        context["reconciliation_success"] = success

        return PhaseResult(
            phase_name=self.name,
            status=PhaseStatus.SUCCESS,
            data={
                "oracle_summary": oracle_summary,
                "success": success,
            },
        )


class DecidePhase(Phase):
    """Decide phase: Determine how to proceed.

    Based on reconciliation, decides whether iteration is complete,
    should continue, or has failed.
    """

    @property
    def name(self) -> str:
        return "decide"

    def execute(self, context: dict[str, Any]) -> PhaseResult:
        """Decide next state based on reconciliation."""
        reconciliation_success = context.get("reconciliation_success")

        # Check if authorization was denied
        authorization = context.get("authorization")
        if authorization is not None and not authorization.authorized:
            context["decision"] = "denied"
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data={"decision": "denied", "reason": "Authorization denied"},
            )

        # Check if execution was skipped
        if context.get("execution_result") is None:
            context["decision"] = "skipped"
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data={"decision": "skipped", "reason": "No execution performed"},
            )

        if reconciliation_success:
            context["decision"] = "complete"
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data={"decision": "complete", "reason": "Oracle passed"},
            )
        else:
            context["decision"] = "failed"
            return PhaseResult(
                phase_name=self.name,
                status=PhaseStatus.SUCCESS,
                data={"decision": "failed", "reason": "Oracle failed"},
            )
