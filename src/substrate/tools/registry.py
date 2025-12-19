"""Tool Registry for managing tool definitions.

The registry holds tool schemas (capability definitions, not implementations).
Tools are looked up by name and validated against their schemas.
"""

from substrate.tools.schemas import (
    PermissionLevel,
    SideEffectClass,
    ToolSchema,
)


class ToolNotFoundError(Exception):
    """Raised when a requested tool does not exist in the registry."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool not found: {tool_name}")


class ToolRegistry:
    """Registry of available tool schemas.

    Holds tool definitions but not implementations.
    Tools are schemas only—capability definitions for the permission system.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSchema] = {}

    def register(self, tool: ToolSchema) -> None:
        """Register a tool schema."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSchema:
        """Look up a tool by name.

        Raises:
            ToolNotFoundError: If tool does not exist
        """
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def list_tools(self) -> list[str]:
        """Return list of registered tool names."""
        return list(self._tools.keys())

    def list_by_level(self, max_level: PermissionLevel) -> list[ToolSchema]:
        """Return tools accessible at or below the given permission level."""
        return [
            tool for tool in self._tools.values() if tool.required_level.value <= max_level.value
        ]

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)


def create_default_registry() -> ToolRegistry:
    """Create registry with the five core tools.

    Tools defined per M3 deliverables:
    - read_file: Read file contents (Level 0, no side effects)
    - write_file: Write to file (Level 2, local state)
    - list_directory: List directory contents (Level 0, no side effects)
    - run_command: Execute shell command (Level 3, external)
    - run_oracle: Query oracle model (Level 3, external)
    """
    registry = ToolRegistry()

    # read_file: Observe-level, no side effects
    registry.register(
        ToolSchema(
            name="read_file",
            description="Read the contents of a file at the specified path",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                },
                "required": ["path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "File contents"},
                    "size_bytes": {"type": "integer", "description": "File size"},
                },
                "required": ["content", "size_bytes"],
            },
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
            tags=("filesystem", "read"),
        )
    )

    # write_file: Act-local level, modifies local state
    registry.register(
        ToolSchema(
            name="write_file",
            description="Write content to a file, creating or overwriting",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "bytes_written": {"type": "integer"},
                },
                "required": ["success", "bytes_written"],
            },
            side_effect=SideEffectClass.LOCAL_STATE,
            required_level=PermissionLevel.ACT_LOCAL,
            tags=("filesystem", "write"),
        )
    )

    # list_directory: Observe-level, no side effects
    registry.register(
        ToolSchema(
            name="list_directory",
            description="List contents of a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory",
                    },
                },
                "required": ["path"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "entries": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["file", "directory", "symlink"],
                                },
                            },
                        },
                    },
                },
                "required": ["entries"],
            },
            side_effect=SideEffectClass.NONE,
            required_level=PermissionLevel.OBSERVE,
            tags=("filesystem", "read"),
        )
    )

    # run_command: Act-external level, subprocess execution
    registry.register(
        ToolSchema(
            name="run_command",
            description="Execute a shell command and return output",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum execution time",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "exit_code": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                },
                "required": ["exit_code", "stdout", "stderr"],
            },
            side_effect=SideEffectClass.EXTERNAL,
            required_level=PermissionLevel.ACT_EXTERNAL,
            tags=("execution", "shell"),
        )
    )

    # run_oracle: Act-external level, external API call
    registry.register(
        ToolSchema(
            name="run_oracle",
            description="Query the oracle model for guidance or validation",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Question or request for the oracle",
                    },
                    "context": {
                        "type": "object",
                        "description": "Additional context for the query",
                    },
                },
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "response": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["response"],
            },
            side_effect=SideEffectClass.EXTERNAL,
            required_level=PermissionLevel.ACT_EXTERNAL,
            tags=("oracle", "model"),
        )
    )

    return registry
