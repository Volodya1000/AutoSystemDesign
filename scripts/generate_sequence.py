import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from application.tasks import DesignTask, DesignTaskMode
from config.root import AppSettings, load_app_settings
from domain.models.scenarios import DesignScenario
from infrastructure.agents.sequence_designer import SequenceDesignerAgent
from infrastructure.llm.client import LiteLlmClient
from infrastructure.visualisation.plantuml.sequence_builder import (
    SequenceDiagramBuilder,
)

_logger: logging.Logger = logging.getLogger("generate_sequence")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Sequence Diagram from a scenario."
    )
    parser.add_argument(
        "--scenario", type=str, required=True, help="Path to a scenario yaml file"
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default="output/sequence.json",
        help="Path to save the AST JSON",
    )
    parser.add_argument(
        "--out-puml",
        type=str,
        default="output/sequence.puml",
        help="Path to save the PlantUML file",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        settings: AppSettings = load_app_settings()
    except (ValidationError, ValueError) as error:
        _logger.error("Settings are not configured: %s", error)
        return 2

    scenario_path = Path(args.scenario)
    if not scenario_path.exists():
        _logger.error("Scenario file not found: %s", scenario_path)
        return 2

    with scenario_path.open("r", encoding="utf-8") as stream:
        payload: Any = yaml.safe_load(stream)

    scenario: DesignScenario = DesignScenario.model_validate(payload)

    _logger.info("Running Sequence Diagram generation...")

    client = LiteLlmClient(settings=settings)
    agent = SequenceDesignerAgent(client=client, settings=settings)
    task = DesignTask(scenario=scenario, mode=DesignTaskMode.INITIAL)

    start_time: float = time.perf_counter()
    try:
        proposal = agent.propose(task)
    except Exception as error:
        _logger.error("Generation failed: %s", error)
        return 1

    wall_seconds: float = time.perf_counter() - start_time
    _logger.info("Generated sequence diagram in %.1f s", wall_seconds)
    _logger.info("Tokens used: %d", proposal.usage.total_tokens)

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        proposal.system_design.model_dump_json(indent=2), encoding="utf-8"
    )
    _logger.info("Saved AST JSON to %s", out_json)

    builder = SequenceDiagramBuilder()
    out_puml = Path(args.out_puml)
    out_puml.parent.mkdir(parents=True, exist_ok=True)

    puml_content = []
    for interaction in proposal.system_design.interaction_scenarios:
        puml_content.append(builder.build(interaction))

    out_puml.write_text("\n".join(puml_content), encoding="utf-8")
    _logger.info("Saved PlantUML sequence to %s", out_puml)

    return 0


if __name__ == "__main__":
    sys.exit(main())
