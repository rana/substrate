"""Tests for iteration loop (M6).

Tests cover:
- sub orient updates node directive
- sub step executes all phases in order
- sub step creates new node
- sub step with denied permission halts
- sub step with oracle failure records failure
- Phase logging format
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.cli.commands import orient_command, step_command
from substrate.iteration.loop import IterationLoop
from substrate.iteration.phases import PhaseStatus
from substrate.iteration.proposal import ProposalStub
from substrate.runtime.state import SubstrateState
from substrate.tools.schemas import PermissionLevel


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create an initialized workspace for testing."""
    state = SubstrateState(tmp_path)
    state.initialize()
    return tmp_path


class TestOrientCommand:
    """Tests for sub orient command."""

    def test_orient_updates_directive(self, workspace: Path) -> None:
        """Orient command updates the node directive."""
        directive = "Fix the failing tests in module X"

        exit_code = orient_command(workspace, directive)

        assert exit_code == 0

        # Verify directive was updated
        state = SubstrateState(workspace)
        active = state.load_active()
        assert active is not None
        node = state.load_node(active.active_node_id)
        assert node is not None
        assert node.directive == directive

    def test_orient_logs_event(self, workspace: Path) -> None:
        """Orient command logs orientation event."""
        directive = "Test directive"

        orient_command(workspace, directive)

        # Check event log
        events_path = workspace / ".substrate" / "logs" / "events.ndjson"
        assert events_path.exists()

        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        orient_events = [e for e in events if e["event"] == "orient"]

        assert len(orient_events) >= 1
        assert orient_events[-1]["payload"]["directive"] == directive

    def test_orient_fails_without_init(self, tmp_path: Path) -> None:
        """Orient command fails if workspace not initialized."""
        exit_code = orient_command(tmp_path, "directive")
        assert exit_code == 1


class TestStepCommand:
    """Tests for sub step command."""

    def test_step_executes_all_phases(self, workspace: Path) -> None:
        """Step executes all phases in order."""
        # Use a simple command that will succeed
        state = SubstrateState(workspace)

        # Create custom proposal that runs echo
        proposal = ProposalStub.custom(
            action="Test echo",
            command=["echo", "hello"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        # Check all phases executed
        phase_names = [pr.phase_name for pr in result.phase_results]
        expected = ["orient", "propose", "authorize", "execute", "observe", "reconcile", "decide"]

        assert phase_names == expected

    def test_step_creates_new_node(self, workspace: Path) -> None:
        """Step creates a new node."""
        state = SubstrateState(workspace)
        active_before = state.load_active()
        assert active_before is not None
        original_node_id = active_before.active_node_id

        # Run step with simple command
        proposal = ProposalStub.custom(
            action="Test echo",
            command=["echo", "test"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        # Verify new node created
        assert result.new_node_id is not None
        assert result.new_node_id != original_node_id

        # Verify active changed
        active_after = state.load_active()
        assert active_after is not None
        assert active_after.active_node_id == result.new_node_id

        # Verify new node exists and has correct parent
        new_node = state.load_node(result.new_node_id)
        assert new_node is not None
        assert new_node.parent_node_id == original_node_id

    def test_step_denied_permission_halts(self, workspace: Path) -> None:
        """Step halts when permission is denied."""
        state = SubstrateState(workspace)

        # Use observe level which can't run commands
        proposal = ProposalStub.custom(
            action="Test command",
            command=["echo", "should not run"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.OBSERVE,  # Too low for run_command
            proposal_stub=proposal,
        )

        result = loop.step()

        # Should be denied
        assert result.decision == "denied"
        assert result.success is False

        # Check authorize phase shows denied
        auth_result = next(
            (pr for pr in result.phase_results if pr.phase_name == "authorize"),
            None,
        )
        assert auth_result is not None
        assert auth_result.status == PhaseStatus.DENIED

    def test_step_oracle_failure_records_failure(self, workspace: Path) -> None:
        """Step records failure when oracle fails."""
        state = SubstrateState(workspace)

        # Use a command that will fail
        proposal = ProposalStub.custom(
            action="Failing command",
            command=["false"],  # Always returns exit code 1
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        # Decision should be failed
        assert result.decision == "failed"

        # Check node was created with failure info
        assert result.new_node_id is not None
        new_node = state.load_node(result.new_node_id)
        assert new_node is not None
        assert new_node.notes is not None
        assert "failed" in new_node.notes.lower()


class TestPhaseLogging:
    """Tests for phase logging format."""

    def test_phase_logging_format(self, workspace: Path) -> None:
        """Each phase is logged with correct format."""
        state = SubstrateState(workspace)

        proposal = ProposalStub.custom(
            action="Test logging",
            command=["echo", "log test"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        loop.step()

        # Read events log
        events_path = workspace / ".substrate" / "logs" / "events.ndjson"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]

        # Check for phase events
        phase_events = [e for e in events if e["event"].startswith("phase_")]

        assert len(phase_events) >= 7  # All phases logged

        # Check each has required fields
        for event in phase_events:
            assert "ts" in event
            assert "event" in event
            assert "payload" in event
            assert "phase_name" in event["payload"]
            assert "status" in event["payload"]

    def test_step_node_created_logged(self, workspace: Path) -> None:
        """Step node creation is logged."""
        state = SubstrateState(workspace)

        proposal = ProposalStub.custom(
            action="Test node logging",
            command=["echo", "node test"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        # Read events log
        events_path = workspace / ".substrate" / "logs" / "events.ndjson"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]

        # Find node creation event
        node_events = [e for e in events if e["event"] == "step_node_created"]
        assert len(node_events) >= 1

        latest = node_events[-1]
        assert latest["node_id"] == result.new_node_id
        assert "parent_node_id" in latest["payload"]
        assert "decision" in latest["payload"]


class TestStepCLI:
    """Tests for step command via CLI."""

    def test_step_cli_basic(self, workspace: Path) -> None:
        """Step command works via CLI interface."""
        # Note: This will try to run pytest which may fail
        # but we're testing the command structure, not the oracle
        exit_code = step_command(workspace, proposal_type="pytest")

        # May succeed or fail depending on pytest in workspace
        # but should not raise exception
        assert exit_code in (0, 1)

    def test_step_cli_with_echo_proposal(self, workspace: Path) -> None:
        """Step command with custom proposal type."""
        # We can't easily inject custom proposal via CLI,
        # so just verify the proposal selection works
        exit_code = step_command(workspace, proposal_type="ruff")
        assert exit_code in (0, 1)


class TestIterationLoopEdgeCases:
    """Edge case tests for iteration loop."""

    def test_step_with_directive(self, workspace: Path) -> None:
        """Step uses directive from node."""
        state = SubstrateState(workspace)

        # Set directive first
        orient_command(workspace, "Run tests to verify functionality")

        # Now step
        proposal = ProposalStub.custom(
            action="Echo directive test",
            command=["echo", "directive"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        # Check orient phase captured directive
        orient_result = next(
            (pr for pr in result.phase_results if pr.phase_name == "orient"),
            None,
        )
        assert orient_result is not None
        assert orient_result.data.get("directive") == "Run tests to verify functionality"

    def test_step_preserves_oracle_summary(self, workspace: Path) -> None:
        """Step records oracle summary in new node."""
        state = SubstrateState(workspace)

        proposal = ProposalStub.custom(
            action="Test oracle summary",
            command=["echo", "PASSED"],
            timeout=10,
        )

        loop = IterationLoop(
            state=state,
            permission_level=PermissionLevel.ACT_EXTERNAL,
            proposal_stub=proposal,
        )

        result = loop.step()

        assert result.new_node_id is not None
        new_node = state.load_node(result.new_node_id)
        assert new_node is not None

        # Oracle summary should be present
        assert new_node.oracle_summary is not None

    def test_multiple_steps_create_chain(self, workspace: Path) -> None:
        """Multiple steps create a chain of nodes."""
        state = SubstrateState(workspace)
        node_ids: list[str] = []

        # Get initial node
        active = state.load_active()
        assert active is not None
        node_ids.append(active.active_node_id)

        # Run three steps
        for i in range(3):
            proposal = ProposalStub.custom(
                action=f"Step {i}",
                command=["echo", f"step{i}"],
                timeout=10,
            )

            loop = IterationLoop(
                state=state,
                permission_level=PermissionLevel.ACT_EXTERNAL,
                proposal_stub=proposal,
            )

            result = loop.step()
            assert result.new_node_id is not None
            node_ids.append(result.new_node_id)

        # Verify chain
        for i in range(1, len(node_ids)):
            node = state.load_node(node_ids[i])
            assert node is not None
            assert node.parent_node_id == node_ids[i - 1]
