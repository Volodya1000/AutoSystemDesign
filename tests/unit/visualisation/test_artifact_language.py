"""Separate localized labels from technical architecture references."""

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from config.generation import GenerationSettings
from domain.models.enums import NodeType
from domain.models.topology import ArchitectureGraph
from infrastructure.visualisation.plantuml.c4_container_builder import (
    C4ContainerDiagramBuilder,
)
from infrastructure.visualisation.plantuml.element_specs import localized_element_specs
from shared.artifact_language import ArtifactLanguage
from tests.factories import create_test_compute_node, create_test_edge, create_test_node

if TYPE_CHECKING:
    from domain.models.edges import Edge
    from domain.models.nodes import ComputeNode

pytestmark = pytest.mark.unit


def test_localized_c4_labels_do_not_rename_nodes_or_edges() -> None:
    service: ComputeNode = create_test_compute_node("orders_api")
    service.display_name = "Сервис заказов"
    edge: Edge = create_test_edge("web_client", "orders_api")
    graph: ArchitectureGraph = ArchitectureGraph(
        nodes=[create_test_node("web_client", NodeType.CLIENT), service], edges=[edge]
    )
    source: str = C4ContainerDiagramBuilder(
        element_specs=localized_element_specs(ArtifactLanguage.RUSSIAN)
    ).build(graph)
    assert service.identifier == "orders_api"
    assert edge.target_identifier == service.identifier
    assert service.display_name in source


def test_localized_element_types_keep_the_same_c4_functions() -> None:
    english = localized_element_specs(ArtifactLanguage.ENGLISH)
    russian = localized_element_specs(ArtifactLanguage.RUSSIAN)
    assert set(english) == set(russian)
    for kind, spec in english.items():
        assert russian[kind].function == spec.function
    assert russian[NodeType.COMPUTE].technology != english[NodeType.COMPUTE].technology


def test_unsupported_artifact_language_is_rejected() -> None:
    with pytest.raises(ValidationError):
        GenerationSettings.model_validate({"artifact_language": "de"})
