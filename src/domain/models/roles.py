# Copyright (c) 2026 Volodya1000
"""Domain models for business roles and catalog."""

from pydantic import BaseModel, ConfigDict, Field


class BusinessRole(BaseModel):
    """A user or actor role within the business domain."""

    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(description="Stable unique identifier (e.g., 'buyer')")
    name: str = Field(description="Human-readable name")
    description: str = Field(description="Domain description of the role")


class ProjectRolesCatalog(BaseModel):
    """Global registry of all business roles in the project."""

    model_config = ConfigDict(extra="forbid")

    roles: list[BusinessRole] = Field(min_length=1)
