# Copyright (c) 2026 Volodya1000
import pytest

from application.tasks import (
    DesignTask,
    DesignTaskMode,
    ProposalFailureDetail,
    ValidationErrorFeedback,
)
from domain.models import DesignScenario
from infrastructure.llm.models import MessageRole
from infrastructure.prompts.design_repair import build_repair_messages

pytestmark = pytest.mark.unit


class TestBuildRepairMessages:
    def test_includes_feedback_previous_payload_and_repeated_schema(
        self, scenario: DesignScenario
    ) -> None:
        task: DesignTask = DesignTask(
            scenario=scenario,
            mode=DesignTaskMode.REPAIR,
            previous_graph_payload='{"nodes": [], "edges": []}',
            validation_feedback=[
                ValidationErrorFeedback(
                    error_code="ISOLATED_NODE",
                    message="Node 'db_orphan' is isolated.",
                )
            ],
            parsing_failures=[
                ProposalFailureDetail(
                    location="$.nodes[0]",
                    message="Field required",
                    error_type="missing",
                )
            ],
        )
        messages = build_repair_messages(task)
        assert [message.role for message in messages] == [
            MessageRole.SYSTEM,
            MessageRole.USER,
        ]
        user_content: str = messages[1].content
        assert '{"nodes": [], "edges": []}' in user_content
        assert "[ISOLATED_NODE]" in user_content
        assert "db_orphan" in user_content
        assert "[missing]" in user_content
        assert "$.nodes[0]" in user_content
        assert "1." in user_content  # numbered problem list
        assert '"node_type"' in user_content  # schema repeated
        assert "client -> load_balancer" in user_content  # whitelist repeated
