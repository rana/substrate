"""CLI integration tests for Substrate commands."""

from pathlib import Path

from substrate.cli.main import main


def test_init_creates_substrate_directory(tmp_path: Path, capsys: object) -> None:
    """sub init should create .substrate directory."""
    exit_code = main(["init", "--path", str(tmp_path)])
    assert exit_code == 0
    assert (tmp_path / ".substrate").exists()
    assert (tmp_path / ".substrate" / "config.json").exists()


def test_init_idempotent(tmp_path: Path) -> None:
    """sub init should be safe to run twice."""
    exit_code1 = main(["init", "--path", str(tmp_path)])
    exit_code2 = main(["init", "--path", str(tmp_path)])
    assert exit_code1 == 0
    assert exit_code2 == 0


def test_status_requires_init(tmp_path: Path) -> None:
    """sub status should fail if not initialized."""
    exit_code = main(["status", "--path", str(tmp_path)])
    assert exit_code == 1


def test_status_after_init(tmp_path: Path) -> None:
    """sub status should work after init."""
    main(["init", "--path", str(tmp_path)])
    exit_code = main(["status", "--path", str(tmp_path)])
    assert exit_code == 0


def test_branch_creates_new_node(tmp_path: Path) -> None:
    """sub branch should create a child node."""
    main(["init", "--path", str(tmp_path)])

    # Get initial node count
    nodes_dir = tmp_path / ".substrate" / "state" / "nodes"
    initial_count = len(list(nodes_dir.glob("*.json")))

    exit_code = main(["branch", "--path", str(tmp_path)])
    assert exit_code == 0

    # Should have one more node
    assert len(list(nodes_dir.glob("*.json"))) == initial_count + 1


def test_branch_requires_init(tmp_path: Path) -> None:
    """sub branch should fail if not initialized."""
    exit_code = main(["branch", "--path", str(tmp_path)])
    assert exit_code == 1


def test_rollback_to_valid_node(tmp_path: Path) -> None:
    """sub rollback should switch to specified node."""
    main(["init", "--path", str(tmp_path)])

    # Get original node ID
    import json

    active_path = tmp_path / ".substrate" / "state" / "active.json"
    with active_path.open() as f:
        original_id = json.load(f)["active_node_id"]

    # Branch (switches to new node)
    main(["branch", "--path", str(tmp_path)])

    # Rollback to original
    exit_code = main(["rollback", original_id, "--path", str(tmp_path)])
    assert exit_code == 0

    # Verify we're back on original
    with active_path.open() as f:
        current_id = json.load(f)["active_node_id"]
    assert current_id == original_id


def test_rollback_to_invalid_node(tmp_path: Path) -> None:
    """sub rollback should fail for nonexistent node."""
    main(["init", "--path", str(tmp_path)])
    exit_code = main(["rollback", "nonexistent", "--path", str(tmp_path)])
    assert exit_code == 1


def test_promote_marks_node(tmp_path: Path) -> None:
    """sub promote should mark node as promoted."""
    main(["init", "--path", str(tmp_path)])
    main(["branch", "--path", str(tmp_path)])

    # Get current node ID
    import json

    active_path = tmp_path / ".substrate" / "state" / "active.json"
    with active_path.open() as f:
        node_id = json.load(f)["active_node_id"]

    exit_code = main(["promote", node_id, "--path", str(tmp_path)])
    assert exit_code == 0

    # Verify promotion status
    node_path = tmp_path / ".substrate" / "state" / "nodes" / f"{node_id}.json"
    with node_path.open() as f:
        node_data = json.load(f)
    assert node_data["promotion_status"] == "promoted"


def test_compare_two_nodes(tmp_path: Path) -> None:
    """sub compare should compare two nodes."""
    main(["init", "--path", str(tmp_path)])

    # Get original node ID
    import json

    active_path = tmp_path / ".substrate" / "state" / "active.json"
    with active_path.open() as f:
        node_a = json.load(f)["active_node_id"]

    # Branch
    main(["branch", "--path", str(tmp_path)])
    with active_path.open() as f:
        node_b = json.load(f)["active_node_id"]

    exit_code = main(["compare", node_a, node_b, "--path", str(tmp_path)])
    assert exit_code == 0


def test_compare_invalid_node(tmp_path: Path) -> None:
    """sub compare should fail if node doesn't exist."""
    main(["init", "--path", str(tmp_path)])

    import json

    active_path = tmp_path / ".substrate" / "state" / "active.json"
    with active_path.open() as f:
        node_a = json.load(f)["active_node_id"]

    exit_code = main(["compare", node_a, "nonexistent", "--path", str(tmp_path)])
    assert exit_code == 1


def test_no_command_shows_help(capsys: object) -> None:
    """Running sub with no command should show help."""
    exit_code = main([])
    assert exit_code == 1
