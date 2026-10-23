"""Execute real SimPy events for a supplied C4 graph and write JSON/PDF."""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from application.architecture_simulation.offline import OfflineSimulationRunner
from domain.architecture_simulation.offline import (
    OfflineSimulationInput,
    OfflineSimulationResult,
)
from infrastructure.architecture_simulation.linear_graph_engine import (
    SimPyLinearGraphEngine,
)
from infrastructure.architecture_simulation.pdf_report import (
    SimulationReportPdfRenderer,
)

_LOGGER: logging.Logger = logging.getLogger("simulation.demo")
_DEFAULT_INPUT: Path = (
    Path(__file__).resolve().parents[1] / "examples" / "simulation" / "cache_demo.json"
)


def main(arguments: Sequence[str] | None = None) -> int:
    """Run an offline example; fail instead of fabricating missing outputs."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=Path("output/simpy_demo"))
    options: argparse.Namespace = parser.parse_args(arguments)
    source: Path = options.input
    directory: Path = options.output_dir
    inputs: OfflineSimulationInput = OfflineSimulationInput.model_validate_json(
        source.read_text(encoding="utf-8")
    )
    result: OfflineSimulationResult = OfflineSimulationRunner(
        SimPyLinearGraphEngine()
    ).run(inputs)
    directory.mkdir(parents=True, exist_ok=True)
    prefix: str = f"{inputs.scenario.identifier}_simulation"
    (directory / f"{prefix}.json").write_text(
        result.report.model_dump_json(indent=2), encoding="utf-8"
    )
    (directory / f"{prefix}_trace.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    (directory / f"{prefix}.pdf").write_bytes(
        SimulationReportPdfRenderer().render(result)
    )
    for run in result.report.experiments:
        _LOGGER.info(
            "%s: generated=%d completed=%d rejected=%d unfinished=%d",
            run.workload_id,
            run.generated_requests,
            run.completed_requests,
            run.rejected_requests,
            run.unfinished_requests,
        )
    _LOGGER.info("Simulation JSON, trace and PDF saved to %s", directory)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
