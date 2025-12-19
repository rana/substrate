"""Tests for workspace tree operations (M2)."""

import tempfile
from pathlib import Path

from substrate.runtime.state import SubstrateState, generate_node_id


def test_generate_node_id_length() -> None:
    """Node IDs should be 16 hex characters."""
    node_id = generate_node_id()
    assert len(node_id) == 16
    assert all(c in "0123456789abcdef" for c in node_id)


def test_generate_node_id_uniqueness() -> None:
    """Node IDs should be unique."""
    ids = {generate_node_id() for _ in range(100)}
    assert len(ids) == 100


def test_branch_creates_child_node() -> None:
    """Branch should create a new node derived from parent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Create a test file in the workspace
        test_file = workspace / "test.txt"
        test_file.write_text("hello")

        # Branch
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None
        assert new_node_id != original_node_id

        # Verify new node record
        new_node = state.load_node(new_node_id)
        assert new_node is not None
        assert new_node.parent_node_id == original_node_id

        # Verify active state updated
        new_active = state.load_active()
        assert new_active is not None
        assert new_active.active_node_id == new_node_id

        # Verify workspace copied
        new_workspace = state.get_workspace_path(new_node_id)
        assert (new_workspace / "test.txt").exists()
        assert (new_workspace / "test.txt").read_text() == "hello"


def test_branch_excludes_substrate_dir() -> None:
    """Branch should not copy .substrate directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None

        success, _, new_node_id = state.create_branch(active.active_node_id)
        assert success
        assert new_node_id is not None

        new_workspace = state.get_workspace_path(new_node_id)
        assert not (new_workspace / ".substrate").exists()


def test_rollback_switches_active_node() -> None:
    """Rollback should switch active node without deleting history."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch to create a new node
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        # Verify we're on new node
        active = state.load_active()
        assert active is not None
        assert active.active_node_id == new_node_id

        # Rollback to original
        success, _ = state.rollback(original_node_id)
        assert success

        # Verify we're back on original
        active = state.load_active()
        assert active is not None
        assert active.active_node_id == original_node_id

        # Verify new node still exists (history preserved)
        assert state.node_exists(new_node_id)


def test_rollback_nonexistent_node_fails() -> None:
    """Rollback to nonexistent node should fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        success, message = state.rollback("nonexistent")
        assert not success
        assert "not found" in message


def test_promote_marks_node_promoted() -> None:
    """Promote should mark node as promoted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch to create a new node
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        # Promote new node
        success, _ = state.promote(new_node_id)
        assert success

        # Verify promotion status
        node = state.load_node(new_node_id)
        assert node is not None
        assert node.promotion_status == "promoted"

        # Verify active node is promoted node
        active = state.load_active()
        assert active is not None
        assert active.active_node_id == new_node_id


def test_promote_idempotent() -> None:
    """Promoting an already promoted node should succeed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch and promote
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        state.promote(new_node_id)
        success, message = state.promote(new_node_id)
        assert success
        assert "already promoted" in message


def test_compare_identical_workspaces() -> None:
    """Compare should show identical workspaces as having no differences."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        # Create a test file
        test_file = workspace / "test.txt"
        test_file.write_text("hello")

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch (creates identical copy)
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        # Compare
        success, _, comparison = state.compare_nodes(original_node_id, new_node_id)
        assert success
        assert comparison is not None
        assert len(comparison["only_in_a"]) == 0
        assert len(comparison["only_in_b"]) == 0
        assert len(comparison["modified"]) == 0
        assert len(comparison["identical"]) > 0


def test_compare_modified_workspace() -> None:
    """Compare should detect modified files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        # Create a test file
        test_file = workspace / "test.txt"
        test_file.write_text("hello")

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        # Modify file in new workspace
        new_workspace = state.get_workspace_path(new_node_id)
        (new_workspace / "test.txt").write_text("world")

        # Compare
        success, _, comparison = state.compare_nodes(original_node_id, new_node_id)
        assert success
        assert comparison is not None
        assert "test.txt" in comparison["modified"]


def test_compare_added_file() -> None:
    """Compare should detect files only in one workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None
        original_node_id = active.active_node_id

        # Branch
        success, _, new_node_id = state.create_branch(original_node_id)
        assert success
        assert new_node_id is not None

        # Add file in new workspace only
        new_workspace = state.get_workspace_path(new_node_id)
        (new_workspace / "new_file.txt").write_text("new")

        # Compare
        success, _, comparison = state.compare_nodes(original_node_id, new_node_id)
        assert success
        assert comparison is not None
        assert "new_file.txt" in comparison["only_in_b"]


def test_compare_nonexistent_node_fails() -> None:
    """Compare with nonexistent node should fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        state = SubstrateState(workspace)
        state.initialize()

        active = state.load_active()
        assert active is not None

        success, message, comparison = state.compare_nodes(
            active.active_node_id, "nonexistent"
        )
        assert not success
        assert "not found" in message
        assert comparison is None
