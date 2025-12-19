"""Substrate CLI entry point.

The CLI is the control surface for Substrate - stateless, explicit, scriptable.
"""

import argparse
import sys
from pathlib import Path

from substrate.cli.commands import init_command, status_command


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="sub",
        description="Substrate: A runtime environment for collaborative intelligence",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # sub init
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

    # sub status
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
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
