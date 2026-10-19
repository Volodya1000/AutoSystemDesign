from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.exceptions.model_validation_errors import (
    ModelValidationCode,
    ModelValidationError,
)
from domain.models.ast_steps import (
    AltStep,
    LoopStep,
    MessageStep,
    OptStep,
    ScenarioStep,
)


class UserLifeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["user"] = Field(
        description="Participant type: real user / actor ('user')"
    )
    lifeline_id: str = Field(
        description="Unique lifeline ID within the scenario (e.g., 'buyer_1')"
    )
    business_role_id: str = Field(
        description="Reference to global role_id from the business roles catalog (e.g., 'buyer')"
    )
    scenario_role: str = Field(
        description="Role in the current process (e.g., 'initiator', 'recipient')"
    )
    description: str = Field(
        description="Description of the specific participant in this scenario"
    )


class ComponentLifeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["component"] = Field(
        description="Participant type: technical architectural component ('component')"
    )
    lifeline_id: str = Field(description="Unique lifeline ID (e.g., 'api_gateway')")
    architecture_node_id: str = Field(
        description="ID of the corresponding node from the static ArchitectureGraph"
    )
    display_name: str = Field(
        description="Display name for the diagram (e.g., 'Mobile Application')"
    )
    description: str = Field(
        description="Description of the component's role in this scenario"
    )


ScenarioLifeline = Annotated[
    UserLifeline | ComponentLifeline, Field(discriminator="kind")
]


def _validated_lifeline_ids(lifelines: list[ScenarioLifeline]) -> set[str]:
    """Validate lifeline identifiers and return their unique IDs."""
    lifeline_ids: set[str] = set()
    for lifeline in lifelines:
        lifeline_id: str = lifeline.lifeline_id
        if not lifeline_id.strip():
            raise ModelValidationError(ModelValidationCode.EMPTY_LIFELINE_ID)
        if lifeline_id in lifeline_ids:
            raise ModelValidationError(
                ModelValidationCode.DUPLICATE_LIFELINE_ID, lifeline_id=lifeline_id
            )
        lifeline_ids.add(lifeline_id)
    return lifeline_ids


def _validate_message_endpoints(step: MessageStep, lifeline_ids: set[str]) -> None:
    """Raise when a message references a lifeline that is not declared."""
    if step.from_lifeline not in lifeline_ids:
        raise ModelValidationError(
            ModelValidationCode.UNKNOWN_MESSAGE_SENDER, lifeline_id=step.from_lifeline
        )
    if step.to_lifeline not in lifeline_ids:
        raise ModelValidationError(
            ModelValidationCode.UNKNOWN_MESSAGE_RECIPIENT, lifeline_id=step.to_lifeline
        )


def _collect_used_lifeline_ids(
    steps: list[ScenarioStep], lifeline_ids: set[str]
) -> set[str]:
    """Collect referenced lifelines while validating nested message endpoints."""
    used_lifeline_ids: set[str] = set()
    for step in steps:
        if isinstance(step, MessageStep):
            _validate_message_endpoints(step, lifeline_ids)
            used_lifeline_ids.add(step.from_lifeline)
            used_lifeline_ids.add(step.to_lifeline)
        elif isinstance(step, AltStep):
            for branch in step.branches:
                used_lifeline_ids.update(
                    _collect_used_lifeline_ids(branch.steps, lifeline_ids)
                )
        elif isinstance(step, (OptStep, LoopStep)):
            used_lifeline_ids.update(
                _collect_used_lifeline_ids(step.steps, lifeline_ids)
            )
    return used_lifeline_ids


class InteractionScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(description="Unique scenario ID")
    requirement_identifier: str = Field(
        description="Identifier of the functional requirement being fulfilled"
    )
    description: str = Field(description="Description of what this scenario validates")
    lifelines: list[ScenarioLifeline] = Field(
        min_length=1, description="All participants in the scenario. Cannot be empty."
    )
    steps: list[ScenarioStep] = Field(
        min_length=1, description="Ordered AST of scenario steps. Cannot be empty."
    )

    @model_validator(mode="after")
    def validate_scenario_integrity(self) -> InteractionScenario:
        lifeline_ids: set[str] = _validated_lifeline_ids(self.lifelines)
        used_lifeline_ids: set[str] = _collect_used_lifeline_ids(
            self.steps, lifeline_ids
        )
        unused = sorted(lifeline_ids - used_lifeline_ids)
        if unused:
            raise ModelValidationError(
                ModelValidationCode.UNUSED_LIFELINES, unused=unused
            )
        return self
