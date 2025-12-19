"""Deterministic proposal stub for M6.

The proposal stub returns hardcoded actions for testing the iteration loop
without AI reasoning. Real model-driven proposals come in M7.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StubProposal:
    """Configuration for the proposal stub.

    Attributes:
        action: Description of the proposed action
        tool: Tool name to invoke
        args: Arguments for the tool
    """

    action: str
    tool: str
    args: dict[str, Any]

    def get_proposal(self, context: dict[str, Any]) -> dict[str, Any]:
        """Return the stubbed proposal.

        Args:
            context: Iteration context (unused in stub, but matches interface)

        Returns:
            Proposal dictionary with action, tool, and args
        """
        _ = context  # Unused in stub
        return {
            "action": self.action,
            "tool": self.tool,
            "args": self.args,
        }


class ProposalStub:
    """Factory for common stub proposals."""

    @staticmethod
    def run_pytest() -> StubProposal:
        """Create a stub that proposes running pytest."""
        return StubProposal(
            action="Run Python tests",
            tool="run_command",
            args={
                "command": ["uv", "run", "pytest", "-v", "--tb=short"],
                "timeout": 120,
            },
        )

    @staticmethod
    def run_ruff_check() -> StubProposal:
        """Create a stub that proposes running ruff check."""
        return StubProposal(
            action="Run linter",
            tool="run_command",
            args={
                "command": ["uv", "run", "ruff", "check", "."],
                "timeout": 60,
            },
        )

    @staticmethod
    def run_pyright() -> StubProposal:
        """Create a stub that proposes running pyright."""
        return StubProposal(
            action="Run type checker",
            tool="run_command",
            args={
                "command": ["uv", "run", "pyright"],
                "timeout": 120,
            },
        )

    @staticmethod
    def custom(action: str, command: list[str], timeout: int = 60) -> StubProposal:
        """Create a custom stub proposal.

        Args:
            action: Description of the action
            command: Command to execute
            timeout: Execution timeout in seconds
        """
        return StubProposal(
            action=action,
            tool="run_command",
            args={
                "command": command,
                "timeout": timeout,
            },
        )
