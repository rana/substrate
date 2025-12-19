"""Tests for Tool Registry.

Covers schema validation and tool lookup per M3 requirements.
"""

import pytest

from substrate.tools import (
    PermissionLevel,
    SideEffectClass,
    ToolNotFoundError,
    ToolRegistry,
    ToolSchema,
    create_default_registry,
)


class TestToolSchema:
    """Test ToolSchema structure and serialization."""

    def test_schema_creation(self) -> None:
        """Tool schema can be created with required fields."""
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
        )

        assert schema.name == "test_tool"
        assert schema.description == "A test tool"
        assert schema.side_effect == SideEffectClass.NONE
        assert schema.required_level == PermissionLevel.OBSERVE
        assert schema.tags == ()

    def test_schema_with_tags(self) -> None:
        """Tool schema accepts optional tags."""
        schema = ToolSchema(
            name="tagged_tool",
            description="Tool with tags",
            input_schema={},
            output_schema={},
            side_effect=SideEffectClass.LOCAL_STATE,
            required_level=PermissionLevel.ACT_LOCAL,
            tags=("filesystem", "write"),
        )

        assert schema.tags == ("filesystem", "write")

    def test_schema_to_dict(self) -> None:
        """Schema serializes to dictionary correctly."""
        schema = ToolSchema(
            name="serialize_test",
            description="Test serialization",
            input_schema={"type": "object"},
            output_schema={"type": "string"},
            side_effect=SideEffectClass.EXTERNAL,
            required_level=PermissionLevel.ACT_EXTERNAL,
            tags=("test",),
        )

        result = schema.to_dict()

        assert result["name"] == "serialize_test"
        assert result["side_effect"] == "external"
        assert result["required_level"] == 3
        assert result["tags"] == ["test"]

    def test_schema_is_frozen(self) -> None:
        """Tool schema is immutable."""
        schema = ToolSchema(
            name="frozen_test",
            description="Test immutability",
            input_schema={},
            output_schema={},
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
        )

        with pytest.raises(AttributeError):
            schema.name = "modified"  # type: ignore[misc]


class TestToolRegistry:
    """Test ToolRegistry operations."""

    def test_register_and_lookup(self) -> None:
        """Tools can be registered and looked up by name."""
        registry = ToolRegistry()
        schema = ToolSchema(
            name="lookup_test",
            description="Test lookup",
            input_schema={},
            output_schema={},
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
        )

        registry.register(schema)
        result = registry.get("lookup_test")

        assert result.name == "lookup_test"
        assert result is schema

    def test_lookup_nonexistent_raises(self) -> None:
        """Looking up unknown tool raises ToolNotFoundError."""
        registry = ToolRegistry()

        with pytest.raises(ToolNotFoundError) as exc_info:
            registry.get("nonexistent")

        assert exc_info.value.tool_name == "nonexistent"
        assert "nonexistent" in str(exc_info.value)

    def test_contains_check(self) -> None:
        """Registry supports 'in' operator for existence check."""
        registry = ToolRegistry()
        schema = ToolSchema(
            name="contains_test",
            description="Test contains",
            input_schema={},
            output_schema={},
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
        )

        assert "contains_test" not in registry

        registry.register(schema)

        assert "contains_test" in registry

    def test_list_tools(self) -> None:
        """Registry lists all registered tool names."""
        registry = ToolRegistry()

        for name in ["tool_a", "tool_b", "tool_c"]:
            registry.register(
                ToolSchema(
                    name=name,
                    description=f"Tool {name}",
                    input_schema={},
                    output_schema={},
                    side_effect=SideEffectClass.NONE,
                    required_level=PermissionLevel.OBSERVE,
                )
            )

        names = registry.list_tools()

        assert set(names) == {"tool_a", "tool_b", "tool_c"}

    def test_list_by_level(self) -> None:
        """Registry filters tools by maximum permission level."""
        registry = ToolRegistry()

        # Register tools at different levels
        for level in PermissionLevel:
            registry.register(
                ToolSchema(
                    name=f"tool_level_{level.value}",
                    description=f"Level {level.value} tool",
                    input_schema={},
                    output_schema={},
                    side_effect=SideEffectClass.NONE,
                    required_level=level,
                )
            )

        # Level 0 should only see level 0 tools
        level_0_tools = registry.list_by_level(PermissionLevel.OBSERVE)
        assert len(level_0_tools) == 1
        assert level_0_tools[0].name == "tool_level_0"

        # Level 2 should see levels 0, 1, 2
        level_2_tools = registry.list_by_level(PermissionLevel.ACT_LOCAL)
        assert len(level_2_tools) == 3
        names = {t.name for t in level_2_tools}
        assert names == {"tool_level_0", "tool_level_1", "tool_level_2"}

    def test_len(self) -> None:
        """Registry reports correct tool count."""
        registry = ToolRegistry()

        assert len(registry) == 0

        registry.register(
            ToolSchema(
                name="count_test",
                description="Test count",
                input_schema={},
                output_schema={},
                side_effect=SideEffectClass.NONE,
                required_level=PermissionLevel.OBSERVE,
            )
        )

        assert len(registry) == 1


class TestDefaultRegistry:
    """Test the default registry with core tools."""

    def test_default_registry_has_five_tools(self) -> None:
        """Default registry contains exactly five core tools."""
        registry = create_default_registry()

        assert len(registry) == 5

    def test_default_registry_tool_names(self) -> None:
        """Default registry has the expected tool names."""
        registry = create_default_registry()

        expected = {"read_file", "write_file", "list_directory", "run_command", "run_oracle"}
        actual = set(registry.list_tools())

        assert actual == expected

    def test_read_file_schema(self) -> None:
        """read_file has correct permission level and side effect."""
        registry = create_default_registry()
        tool = registry.get("read_file")

        assert tool.required_level == PermissionLevel.OBSERVE
        assert tool.side_effect == SideEffectClass.NONE
        assert "path" in tool.input_schema["properties"]

    def test_write_file_schema(self) -> None:
        """write_file requires ACT_LOCAL and has LOCAL_STATE side effect."""
        registry = create_default_registry()
        tool = registry.get("write_file")

        assert tool.required_level == PermissionLevel.ACT_LOCAL
        assert tool.side_effect == SideEffectClass.LOCAL_STATE

    def test_run_command_schema(self) -> None:
        """run_command requires ACT_EXTERNAL and has EXTERNAL side effect."""
        registry = create_default_registry()
        tool = registry.get("run_command")

        assert tool.required_level == PermissionLevel.ACT_EXTERNAL
        assert tool.side_effect == SideEffectClass.EXTERNAL

    def test_run_oracle_schema(self) -> None:
        """run_oracle requires ACT_EXTERNAL."""
        registry = create_default_registry()
        tool = registry.get("run_oracle")

        assert tool.required_level == PermissionLevel.ACT_EXTERNAL
        assert tool.side_effect == SideEffectClass.EXTERNAL

    def test_observe_level_tools(self) -> None:
        """At observe level, only read operations are accessible."""
        registry = create_default_registry()

        accessible = registry.list_by_level(PermissionLevel.OBSERVE)
        names = {t.name for t in accessible}

        # Only read_file and list_directory should be accessible at level 0
        assert names == {"read_file", "list_directory"}
