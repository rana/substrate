"""Substrate CLI entry point.

The CLI is the control surface for Substrate - stateless, explicit, scriptable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from substrate.cli.commands import (
    branch_command,
    compare_command,
    init_command,
    orient_command,
    promote_command,
    rollback_command,
    status_command,
    step_command,
)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="sub",
        description="Substrate: A runtime environment for collaborative intelligence",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a Substrate workspace",
    )
    init_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # status
    status_parser = subparsers.add_parser(
        "status",
        help="Display current workspace status",
    )
    status_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # branch
    branch_parser = subparsers.add_parser(
        "branch",
        help="Create a new branch from the current node",
    )
    branch_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # rollback
    rollback_parser = subparsers.add_parser(
        "rollback",
        help="Switch to a different node",
    )
    rollback_parser.add_argument(
        "node_id",
        type=str,
        help="ID of the node to switch to",
    )
    rollback_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # promote
    promote_parser = subparsers.add_parser(
        "promote",
        help="Promote a node to trunk status",
    )
    promote_parser.add_argument(
        "node_id",
        type=str,
        help="ID of the node to promote",
    )
    promote_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # compare
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two nodes",
    )
    compare_parser.add_argument(
        "node_a",
        type=str,
        help="ID of the first node",
    )
    compare_parser.add_argument(
        "node_b",
        type=str,
        help="ID of the second node",
    )
    compare_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # orient
    orient_parser = subparsers.add_parser(
        "orient",
        help="Set task directive for the active node",
    )
    orient_parser.add_argument(
        "directive",
        type=str,
        help="Task directive text",
    )
    orient_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )

    # step
    step_parser = subparsers.add_parser(
        "step",
        help="Execute a single iteration step",
    )
    step_parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Workspace root path (default: current directory)",
    )
    step_parser.add_argument(
        "--proposal",
        type=str,
        choices=["pytest", "ruff", "pyright"],
        default="pytest",
        help="Type of proposal to execute (default: pytest)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "init":
        return init_command(args.path)
    elif args.command == "status":
        return status_command(args.path)
    elif args.command == "branch":
        return branch_command(args.path)
    elif args.command == "rollback":
        return rollback_command(args.path, args.node_id)
    elif args.command == "promote":
        return promote_command(args.path, args.node_id)
    elif args.command == "compare":
        return compare_command(args.path, args.node_a, args.node_b)
    elif args.command == "orient":
        return orient_command(args.path, args.directive)
    elif args.command == "step":
        return step_command(args.path, args.proposal)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
