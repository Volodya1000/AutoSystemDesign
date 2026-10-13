from pydantic import BaseModel, ConfigDict, Field


class FunctionalRequirement(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    identifier: str = Field(alias="id")
    name: str
    text: str
