import pytest

from domain.models.ast_steps import MessageStep
from domain.models.nodes import ClientNode
from domain.models.roles import BusinessRole, ProjectRolesCatalog
from domain.models.sequence import ComponentLifeline, InteractionScenario
from domain.models.topology import ArchitectureGraph
from domain.specifications.sequence_validator import SequenceValidator

pytestmark = pytest.mark.unit


def test_sequence_validator_catches_unknown_architecture_nodes() -> None:
    catalog = ProjectRolesCatalog(
        roles=[BusinessRole(role_id="buyer", name="Buyer", description="d")]
    )
    graph = ArchitectureGraph(
        nodes=[ClientNode(identifier="web_client", replicas_count=1)], edges=[]
    )

    # Intentionally referencing a C4 node that doesn't exist in the graph
    lifeline = ComponentLifeline(
        kind="component",
        lifeline_id="l1",
        architecture_node_id="non_existent_db",
        display_name="DB",
        description="d",
    )
    msg = MessageStep(
        kind="message",
        from_lifeline="l1",
        to_lifeline="l1",
        action_name="ping",
        message_kind="event",
    )

    scenario = InteractionScenario(
        scenario_id="s1",
        requirement_identifier="req_1",
        description="desc",
        lifelines=[lifeline],
        steps=[msg],
    )

    validator = SequenceValidator()
    result = validator.validate_scenario(
        scenario, catalog, graph, expected_requirement_id="req_1"
    )

    assert result.is_successful is False
    assert (
        "references unknown architecture_node_id 'non_existent_db'"
        in result.errors[0].message
    )
