"""Tool Registry and Permission Gate.

Provides tool schema definitions and permission-based authorization.
"""

from substrate.tools.permissions import AuthorizationResult, PermissionGate
from substrate.tools.registry import (
    ToolNotFoundError,
    ToolRegistry,
    create_default_registry,
)
from substrate.tools.schemas import PermissionLevel, SideEffectClass, ToolSchema

__all__ = [
    "AuthorizationResult",
    "PermissionGate",
    "PermissionLevel",
    "SideEffectClass",
    "ToolNotFoundError",
    "ToolRegistry",
    "ToolSchema",
    "create_default_registry",
]
