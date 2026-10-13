from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BusinessRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str = Field(
        description="Stable unique identifier for the business role (e.g., 'buyer', 'seller')"
    )
    name: str = Field(description="Human-readable name of the role (e.g., 'Buyer')")
    description: str = Field(
        description="Description of the role within the business domain"
    )


class ProjectRolesCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles: list[BusinessRole] = Field(
        min_length=1,
        description="Global project registry of business roles (cannot be empty)",
    )
