from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class InteractionScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(description="Unique scenario ID")
    requirement_name: str = Field(description="Name of the functional requirement")
    description: str = Field(description="Description of what this scenario validates")
    lifelines: list[ScenarioLifeline] = Field(
        min_length=1, description="All participants in the scenario. Cannot be empty."
    )
    steps: list[ScenarioStep] = Field(
        min_length=1, description="Ordered AST of scenario steps. Cannot be empty."
    )

    @model_validator(mode="after")
    def validate_scenario_integrity(self) -> InteractionScenario:
        lifeline_ids = set()
        for lifeline in self.lifelines:
            if not lifeline.lifeline_id.strip():
                raise ValueError("Lifeline identifier (lifeline_id) cannot be empty.")
            if lifeline.lifeline_id in lifeline_ids:
                raise ValueError(
                    f"Duplicate lifeline identifier: '{lifeline.lifeline_id}'"
                )
            lifeline_ids.add(lifeline.lifeline_id)

        def check_steps(steps_list: list[ScenarioStep]):
            for step in steps_list:
                if isinstance(step, MessageStep):
                    if step.from_lifeline not in lifeline_ids:
                        raise ValueError(
                            f"Unknown message sender: '{step.from_lifeline}'"
                        )
                    if step.to_lifeline not in lifeline_ids:
                        raise ValueError(
                            f"Unknown message recipient: '{step.to_lifeline}'"
                        )
                elif isinstance(step, AltStep):
                    for branch in step.branches:
                        check_steps(branch.steps)
                elif isinstance(step, OptStep) or isinstance(step, LoopStep):
                    check_steps(step.steps)

        check_steps(self.steps)
        return self
