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
