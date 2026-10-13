from pydantic import BaseModel, ConfigDict

from domain.models.functional import FunctionalRequirement
from domain.models.roles import ProjectRolesCatalog
from domain.models.sequence import InteractionScenario


class SystemContextOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    functional_requirements: list[FunctionalRequirement]
    roles_catalog: ProjectRolesCatalog


class SystemDesignOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    functional_requirements: list[FunctionalRequirement]
    roles_catalog: ProjectRolesCatalog
    interaction_scenarios: list[InteractionScenario]
