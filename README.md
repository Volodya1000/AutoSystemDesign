# AutoSystemDesign

AutoSystemDesign generates and validates software architecture artifacts from YAML system scenarios using an LLM. The current pipeline produces a C4 architecture, sequence diagrams for functional requirements, and a REST API design with OpenAPI and Swagger UI artifacts.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- An OpenAI-compatible LLM endpoint. The default configuration is intended for LM Studio.

## Setup

Install the locked development dependencies:

```bash
uv sync --locked --all-groups
```

Create a local environment file from the example and adjust it for your LLM endpoint:

```bash
cp .env.example .env
```

For LM Studio, start the local server and set `ASD_BASE_URL` and `ASD_API_KEY` in `.env`. Model and generation options are configured in `config.yaml`. Secrets must come from environment variables or `.env`, not from the YAML configuration.

## Run the pipeline

From the repository root:

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml
```

Choose an output directory or rendering backend with command-line overrides:

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --out-dir output
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server kroki
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --no-diagram
```

The pipeline has three ordered stages:

1. **C4** generates and validates the architecture graph.
2. **Sequence** generates a roles catalog and one interaction scenario per functional requirement.
3. **API** generates a REST API design and its OpenAPI/Swagger artifacts.

Generated artifacts are written to the configured output directory. They include JSON models and, when enabled, PlantUML source and rendered diagrams, an OpenAPI JSON document, and a Swagger UI HTML page.

Scenarios without functional requirements can be used for C4-only output; sequence and API generation are skipped.

## Configuration

- `config.yaml`: LLM model, generation limits, sequence parallelism, and visualization settings.
- `.env`: local secrets and endpoint settings. Do not commit this file.
- `config.test.yaml`: test configuration. Integration tests may use `APP_CONFIG_FILE=config.test.yaml`.

The visualisation settings support `auto`, `plantuml`, `kroki`, or a self-hosted PlantUML server URL. The local PlantUML server setup is documented in [deploy/plantuml/README.md](deploy/plantuml/README.md).

## Tests and code quality

Run unit tests:

```bash
uv run pytest -m unit
```

Run the main static checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pylint src tests
```

Integration tests in `tests/integration` require a reachable LLM endpoint and can incur local model inference time. The GitHub Actions CI runs locked dependency installation, static checks, and unit tests for pull requests targeting `master`.

## Project layout

- `src/domain`: domain models, invariants, and validators.
- `src/application`: generation services, pipeline stages, result contracts, and ports.
- `src/infrastructure`: LLM adapters, parsing, persistence, reporting, and renderers.
- `src/config`: application and integration-test settings.
- `scenarios`: sample input YAML files.
- `tests/unit` and `tests/integration`: automated tests.
