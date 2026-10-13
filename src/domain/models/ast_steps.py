from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MessageStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["message"] = Field(
        description="Type of element: message or call ('message')"
    )
    from_lifeline: str = Field(description="Sender lifeline_id")
    to_lifeline: str = Field(description="Recipient lifeline_id")
    action_name: str = Field(
        description="Method name, event, or action (e.g., 'POST /orders')"
    )
    message_kind: Literal[
        "request", "response", "event", "notification", "user_action"
    ] = Field(description="Semantic category of the message")
    delivery_mode: Literal["sync", "async"] | None = Field(
        default=None, description="Delivery mode (sync/async) if applicable"
    )
    description: str | None = Field(default=None, description="Additional details")


class AlternativeBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str | None = Field(
        default=None,
        description=(
            "Branch condition. If null (None), it acts as the default (else) branch."
        ),
    )
    steps: list[ScenarioStep] = Field(
        min_length=1,
        description="List of steps in this branch (minimum one step)",
    )


class AltStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["alt"] = Field(
        description="Alternative branching (if / else / elif) ('alt')"
    )
    branches: list[AlternativeBranch] = Field(
        min_length=2,
        description=(
            "List of branches. If an else branch exists (condition=None), "
            "it must be unique and last."
        ),
    )

    @model_validator(mode="after")
    def validate_alt_branches(self) -> AltStep:
        else_count = 0
        for i, branch in enumerate(self.branches):
            if branch.condition is None:
                else_count += 1
                if i != len(self.branches) - 1:
                    raise ValueError(
                        "The default branch (else / condition=None) "
                        "must be the last one in an alt block."
                    )
            else:
                if not branch.condition.strip():
                    raise ValueError(
                        "A conditional branch cannot have an empty "
                        "condition or consist only of spaces."
                    )

        if else_count > 1:
            raise ValueError(
                "An 'alt' block can contain only one default (else) branch."
            )

        return self


class OptStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["opt"] = Field(description="Optional block / if without else ('opt')")
    condition: str = Field(description="Condition to execute the block")
    steps: list[ScenarioStep] = Field(
        min_length=1, description="Steps inside the optional block"
    )


class LoopStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["loop"] = Field(description="Loop block ('loop')")
    condition: str = Field(description="Repetition rule (e.g., 'For each item')")
    steps: list[ScenarioStep] = Field(min_length=1, description="Steps inside the loop")


ScenarioStep = Annotated[
    MessageStep | AltStep | OptStep | LoopStep, Field(discriminator="kind")
]

AlternativeBranch.model_rebuild()
AltStep.model_rebuild()
OptStep.model_rebuild()
LoopStep.model_rebuild()
