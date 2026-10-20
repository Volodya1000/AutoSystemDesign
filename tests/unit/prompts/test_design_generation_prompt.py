import pytest

from application.tasks import DesignTask, DesignTaskMode
from domain.models import DesignScenario
from infrastructure.llm.models import MessageRole
from infrastructure.prompts.design_generation import build_initial_messages

EXPECTED_ASSERT_MESSAGES_COUNT = 2

pytestmark = pytest.mark.unit


class TestBuildInitialMessages:
    def test_structure_and_content(self, scenario: DesignScenario) -> None:
        task: DesignTask = DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)
        messages = build_initial_messages(task)
        assert len(messages) == EXPECTED_ASSERT_MESSAGES_COUNT
        assert [message.role for message in messages] == [
            MessageRole.SYSTEM,
            MessageRole.USER,
        ]
        user_content: str = messages[1].content
        assert "ecommerce_checkout" in user_content
        assert "120.0" in user_content
        assert "400.0" in user_content
        assert "latency" in user_content
        assert "budget" in user_content
        assert '"node_type"' in user_content  # schema fragment
        assert "web_client" in user_content  # few-shot example
        assert "client -> load_balancer" in user_content  # allowed connections
        assert "Hard rules" in user_content

