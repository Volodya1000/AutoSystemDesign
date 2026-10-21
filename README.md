# AutoSystemDesign

AutoSystemDesign генерирует и проверяет артефакты архитектуры программных систем на основе YAML-сценария и LLM. Текущий конвейер создаёт архитектурную диаграмму C4, диаграммы последовательностей для функциональных требований и описание REST API с артефактами OpenAPI и Swagger UI.

## Требования

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- LLM endpoint, совместимый с OpenAI API. Конфигурация по умолчанию рассчитана на LM Studio.

## Установка и настройка

Установите зафиксированные зависимости разработки:

```bash
uv sync --locked --all-groups
```

Создайте локальный файл переменных окружения:

```bash
cp .env.example .env
```

Для LM Studio запустите локальный сервер и укажите в `.env` значения `ASD_BASE_URL` и `ASD_API_KEY`. Параметры модели и генерации задаются в `config.yaml`. Секреты следует хранить в переменных окружения или `.env`, а не в YAML-конфигурации.

## Быстрый запуск

Из корня репозитория:

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml
```

Примеры переопределения параметров:

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --out-dir output
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server kroki
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --no-diagram
```

Полное руководство по аргументам запуска, настройке визуализации, результатам и кодам завершения находится в [`docs/usage.md`](docs/usage.md).

## Извлечение требований из Markdown

Для ручной проверки извлечения функциональных и нефункциональных требований есть пример
`examples/requirements/online_store.md`. Запустите LM Studio или другой OpenAI-compatible
endpoint и настройте `ASD_BASE_URL`, `ASD_API_KEY` и модель в обычной конфигурации проекта.

```bash
uv run python scripts/extract_document_requirements.py
```

По умолчанию результат сохраняется в `output/document_requirements.json`. Можно указать
другой документ и путь результата:

```bash
uv run python scripts/extract_document_requirements.py --document examples/requirements/online_store.md --output output/requirements.json
```

JSON содержит извлечённые требования с цитатами из исходного текста и диагностические
замечания. Этот запуск предназначен для ручной проверки реальным LLM; модульные тесты
не требуют работающего endpoint.

Для преобразования требований в YAML-сценарий, совместимый с существующим конвейером,
используйте двухэтапное извлечение:

```bash
uv run python scripts/extract_document_scenario.py \\
  --document examples/requirements/online_store.md \\
  --output output/online_store.yaml
uv run python scripts/generate_pipeline.py \\
  --scenario output/online_store.yaml --no-diagram
```

Рядом создаётся `output/online_store.evidence.json` с цитатами по полям и диагностикой.
Перед генерацией архитектуры просмотрите этот файл: неподтверждённые требования и
числа отбрасываются, а при невозможности проверить обязательное описание YAML не
создаётся. Если в источнике нет подтверждённого отношения чтений к записям, блок
`workload` целиком исключается: это не позволяет случайно применить доменное значение
по умолчанию `read_ratio: 0.8`.

После проверки манифеста можно передать сценарий существующему конвейеру в рамках
того же вызова, добавив `--run-pipeline`. Для пропуска рендеринга добавьте также
`--no-diagram`; каталог артефактов можно задать через `--pipeline-out-dir output/design`.

## Изучение анализа производительности

Если вы впервые читаете расчёты нагрузки и очередей, начните не с PR, а с
[учебной карты фичи](docs/performance-analysis/README.md).
Там есть [объяснение M/M/1, M/M/c, M/M/c/K и аппроксимаций с нуля](docs/performance-analysis/QUEUEING_THEORY_FOR_BEGINNERS.md)
и [указатель всех pull request с причинами изменений](docs/performance-analysis/PR_INDEX.md).
Сам подробный план реализации находится в
[ROADMAP.md](docs/performance-analysis/ROADMAP.md).

После стадии C4 анализ производительности сохраняет `<scenario>_performance_analysis.json`
и, когда доступен системный Unicode TrueType-шрифт, создаёт рядом PDF.
PDF использует те же значения, что JSON, и не делает новых вычислений.
Подробнее: [PDF-отчёт](docs/performance-analysis/12-pdf-report.md).

Для приёмки всей функции используется
[чек-лист корневого PR](docs/performance-analysis/ROOT_PR_ACCEPTANCE.md)
и [реальные YAML-сценарии](scenarios/performance/README.md).
Выводы из логов оцениваются по наличию обязательных JSON/PDF и корректной
математике, а не только по нулевому коду завершения.

## Этапы конвейера

1. **C4**: генерация и проверка графа архитектуры.
2. **Sequence**: формирование каталога ролей и сценария взаимодействия для каждого функционального требования.
3. **API**: проектирование REST API и генерация артефактов OpenAPI/Swagger.

Артефакты сохраняются в настроенный выходной каталог. В зависимости от параметров это JSON-модели, исходники PlantUML, отрендеренные диаграммы, документ OpenAPI в формате JSON и HTML-страница Swagger UI.

Если функциональные требования отсутствуют, конвейер может сформировать только C4: генерация Sequence и API пропускается.

## Конфигурация

- `config.yaml`: модель LLM, лимиты генерации, параллелизм Sequence и параметры визуализации.
- `.env`: локальные секреты и адрес endpoint. Не добавляйте файл в Git.
- `config.test.yaml`: тестовая конфигурация. Для интеграционных тестов можно использовать `APP_CONFIG_FILE=config.test.yaml`.

Визуализация поддерживает режимы `auto`, `plantuml`, `kroki` или URL собственного сервера PlantUML. Настройка локального сервера описана в [`deploy/plantuml/README.md`](deploy/plantuml/README.md).

## Тесты и качество кода

Запуск модульных тестов:

```bash
uv run pytest -m unit
```

Основные статические проверки:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pylint src tests
```

Интеграционные тесты в `tests/integration` требуют доступного LLM endpoint и могут выполняться долго. GitHub Actions запускает установку зафиксированных зависимостей, статические проверки и модульные тесты для pull request в `master`.

## Структура проекта

- `src/domain`: доменные модели, инварианты и валидаторы.
- `src/application`: сервисы генерации, этапы конвейера, контракты результатов и порты.
- `src/infrastructure`: адаптеры LLM, парсинг, сохранение результатов, отчёты и рендереры.
- `src/config`: настройки приложения и интеграционных тестов.
- `scenarios`: примеры YAML-сценариев.
- `tests/unit` и `tests/integration`: автоматические тесты.

**Ограничение проверки:** дословная цитата подтверждает происхождение формулировки, но сама по себе не доказывает правильность семантической классификации (например, что фраза действительно описывает задержку). Для таких решений сохраняется цитата поля, чтобы результат можно было проверить до запуска конвейера.
