"""Explicit service parameters applied independently of LLM estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.models.enums import NodeType
from domain.models.nodes import CapacityNode
from domain.models.topology import AnyNode, ArchitectureGraph


class ServiceProfile(BaseModel):
    """Record only explicitly supplied processing parameters and their source."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    source: str = Field(min_length=1)
    provenance: Literal["assumption", "measurement"]
    replicas_count: int | None = Field(default=None, ge=1)
    maximum_concurrency: int | None = Field(default=None, gt=0)
    maximum_queue_size: int | None = Field(default=None, ge=0)
    service_channels_per_replica: int | None = Field(default=None, gt=0)
    mean_processing_time_milliseconds: float | None = Field(default=None, gt=0)
    standard_deviation_processing_time: float | None = Field(default=None, ge=0)
    monthly_cost_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_channels(self) -> Self:
        """Keep service channels distinct from the in-flight request limit."""
        if (
            self.service_channels_per_replica is not None
            and self.maximum_concurrency is not None
            and self.service_channels_per_replica > self.maximum_concurrency
        ):
            raise InvalidServiceProfileError.channels_exceed_concurrency()
        if not self.source.strip():
            raise InvalidServiceProfileError.missing_source()
        return self

    def apply[NodeT: CapacityNode](self, node: NodeT) -> NodeT:
        """Validate a new node while preserving type-specific topology fields."""
        parameters: dict[str, object] = self.model_dump(
            exclude={"source", "provenance"}, exclude_none=True
        )
        return type(node).model_validate(node.model_dump() | parameters)


class InvalidServiceProfileError(ValueError):
    """An explicit service profile is contradictory or lacks a source."""

    @classmethod
    def channels_exceed_concurrency(cls) -> InvalidServiceProfileError:
        return cls("Service channels cannot exceed maximum concurrency")

    @classmethod
    def missing_source(cls) -> InvalidServiceProfileError:
        return cls("A service profile must identify its source")

    @classmethod
    def client_profile(cls) -> InvalidServiceProfileError:
        return cls("Client nodes have no service capacity profile")


@dataclass(frozen=True)
class ProfileApplication:
    """Keep the bound graph and exact applied overrides together."""

    graph: ArchitectureGraph
    applied: dict[str, ServiceProfile]


class ServiceProfileCatalog(BaseModel):
    """Resolve node-specific profiles before type-wide explicit defaults."""

    model_config = ConfigDict(extra="forbid")

    by_node_type: dict[NodeType, ServiceProfile] = Field(default_factory=dict)
    by_node_id: dict[str, ServiceProfile] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_types(self) -> Self:
        """Reject capacity parameters for traffic sources."""
        if NodeType.CLIENT in self.by_node_type:
            raise InvalidServiceProfileError.client_profile()
        return self

    def apply(self, graph: ArchitectureGraph) -> ProfileApplication:
        """Apply supplied overrides without requiring a profile for every node."""
        nodes: list[AnyNode] = []
        applied: dict[str, ServiceProfile] = {}
        for node in graph.nodes:
            if not isinstance(node, CapacityNode):
                nodes.append(node)
                continue
            profile: ServiceProfile | None = self.by_node_id.get(
                node.identifier, self.by_node_type.get(node.node_type)
            )
            if profile is None:
                nodes.append(node)
            else:
                nodes.append(profile.apply(node))
                applied[node.identifier] = profile
        return ProfileApplication(
            graph=ArchitectureGraph(nodes=nodes, edges=graph.edges),
            applied=applied,
        )
