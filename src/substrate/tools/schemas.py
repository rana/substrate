"""Tool schemas and type definitions.

Defines the structure for tool definitions including input/output schemas,
side-effect classifications, and required permission levels.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SideEffectClass(Enum):
    """Classification of tool side effects.

    Determines how a tool interacts with the external world.
    Used by Permission Gate to enforce authorization.
    """

    NONE = "none"  # Pure read, no state change
    LOCAL_STATE = "local_state"  # Modifies local files/state
    EXTERNAL = "external"  # Network, subprocess, external systems
    IRREVERSIBLE = "irreversible"  # Cannot be undone


class PermissionLevel(Enum):
    """Permission levels per 05-trust-and-permissions.md.

    Level 0: Observe only - read operations
    Level 1: Suggest - can propose changes
    Level 2: Act locally - can modify local state with approval
    Level 3: Act externally - can interact with external systems
    Level 4: Autonomous - full authority within bounds
    """

    OBSERVE = 0
    SUGGEST = 1
    ACT_LOCAL = 2
    ACT_EXTERNAL = 3
    AUTONOMOUS = 4


@dataclass(frozen=True)
class ToolSchema:
    """Schema defining a tool's interface and requirements.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable explanation of what the tool does
        input_schema: JSON Schema dict describing expected input
        output_schema: JSON Schema dict describing output format
        side_effect: Classification of the tool's side effects
        required_level: Minimum permission level to execute
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effect: SideEffectClass
    required_level: PermissionLevel
    # Tags for categorization and filtering
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for logging and transmission."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "side_effect": self.side_effect.value,
            "required_level": self.required_level.value,
            "tags": list(self.tags),
        }
