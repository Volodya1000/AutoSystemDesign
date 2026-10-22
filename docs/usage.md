# Руководство по запуску

Все команды ниже выполняются из корня репозитория. Перед запуском установите зависимости и настройте доступ к LLM согласно основному [README](../README.md).

## 1. Справка CLI

Получить актуальный список аргументов непосредственно из скрипта:

```bash
uv run python scripts/generate_pipeline.py --help
```

Обязательный аргумент `--scenario` указывает путь к YAML-сценарию.

## 2. Примеры запуска

<details>
<summary>Обычный запуск на примере сценария социальной сети</summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml
```

Используются настройки из `config.yaml`. Это основной вариант запуска полного конвейера.

</details>

<details>
<summary>Запуск другого сценария</summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/ecommerce_checkout.yaml
```

Можно указать любой существующий YAML-файл, соответствующий модели `DesignScenario`.

</details>

<details>
<summary>Изменение каталога результатов: <code>--out-dir</code></summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --out-dir output
```

Переопределяет `visualisation.diagram_dir` из `config.yaml`. Каталог создаётся автоматически, если он отсутствует.

</details>

<details>
<summary>Выбор сервера визуализации: <code>--diagram-server</code></summary>

```bash
# Автоматический выбор согласно конфигурации
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server auto

# PlantUML
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server plantuml

# Kroki
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server kroki

# Собственный сервер PlantUML
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-server http://localhost:8080
```

Аргумент переопределяет `visualisation.server`. Для собственного сервера укажите его URL. Для локального развёртывания см. [инструкцию по PlantUML](../deploy/plantuml/README.md).

</details>

<details>
<summary>Выбор формата изображения: <code>--diagram-format</code></summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-format png
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --diagram-format svg
```

Поддерживаются `png` и `svg`. Если аргумент не задан, используется `visualisation.image_format` из `config.yaml`.

</details>

<details>
<summary>Генерация без рендеринга диаграмм: <code>--no-diagram</code></summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --no-diagram
```

Отключает рендеринг изображений. Этапы генерации и сохранения структурированных артефактов продолжают выполняться; исходники диаграмм могут сохраняться, если их формирование предусмотрено этапом.

</details>

<details>
<summary>Подробные логи: <code>--verbose</code></summary>

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/social_network_chat.yaml --verbose
```

Включает DEBUG-логирование, в том числе вывод необработанных ответов LLM. Учитывайте, что такие логи могут содержать фрагменты входных данных и сгенерированного содержимого.

</details>

<details>
<summary>Комбинация аргументов</summary>

```bash
uv run python scripts/generate_pipeline.py \
  --scenario scenarios/ecommerce_checkout.yaml \
  --out-dir output/checkout \
  --diagram-server kroki \
  --diagram-format svg \
  --verbose
```

Параметры CLI переопределяют соответствующие настройки визуализации из `config.yaml`. Неуказанные параметры берутся из конфигурации.

</details>

## 3. Настройка LLM

Скопируйте пример окружения:

```bash
cp .env.example .env
```

Для локального LM Studio обычно требуется запустить локальный сервер и указать в `.env`:

```dotenv
ASD_BASE_URL=http://localhost:1234/v1
ASD_API_KEY=lm-studio
```

Укажите подходящую модель и параметры генерации в `config.yaml`. Фактические значения должны соответствовать настройкам вашего LLM endpoint. Переменные окружения имеют приоритет над значениями из `.env`. Не коммитьте реальные ключи API.

## 4. Сценарии без функциональных требований

Если YAML-сценарий не содержит функциональных требований, конвейер может сформировать архитектуру C4 и пропускает этапы Sequence и API, для которых нужны функциональные требования. Это подходит для сценариев, где требуется только архитектурная схема.

## 5. Проверка YAML-сценария

Входные YAML-сценарии проверяются строго: неизвестные ключи запрещены как
на верхнем уровне, так и внутри блока `workload`, `requirements` и
`functional_requirements`. Опечатки не удаляются автоматически.

Имя проекта в YAML задаётся только ключом `identifier`. Другие названия
поля не поддерживаются и приводят к ошибке валидации. Отсутствующие
необязательные секции, например `functional_requirements`, по-прежнему
допустимы.

При ошибке команда завершится с кодом **2** до запуска генерации. Например,
если в файле `scenarios/broken.yaml` вместо `requirements` написано
`requrements`, в журнале появится сообщение:

```text
Invalid scenario scenarios/broken.yaml at 'requrements': Unknown field
```

Для вложенных ключей указывается путь, например `workload.read_rato`.
Исправьте имя поля в YAML. Настройки LLM (`config.yaml` и `.env`)
не являются частью YAML-сценария и проверяются отдельно.

## 6. Этапы и результаты

Конвейер выполняет этапы в следующем порядке:

1. **C4**: формирование и валидация архитектурного графа.
2. **Sequence**: формирование каталога ролей и диаграмм взаимодействия по функциональным требованиям.
3. **API**: проектирование REST API и генерация артефактов OpenAPI/Swagger.

Состав файлов зависит от этапов, успешности генерации и параметров рендеринга. Выходной каталог задаётся параметром `--out-dir` или настройкой `visualisation.diagram_dir` в `config.yaml`.

## 7. Коды завершения

- `0`: обязательные артефакты созданы. Ошибка рендеринга диаграммы может привести к частичному результату, но сама по себе не обязательно означает ненулевой код. Проверьте итоговую сводку в логах.
- `1`: не выполнен обязательный этап или отсутствуют обязательные JSON/AST-артефакты.
- `2`: ошибка конфигурации, сценария или подключения к LLM endpoint.

## 8. Проверки и тесты

<details>
<summary>Модульные тесты</summary>

```bash
uv run pytest -m unit
```

</details>

<details>
<summary>Статические проверки</summary>

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pylint src tests
```

</details>

<details>
<summary>Интеграционные тесты</summary>

```bash
uv run pytest tests/integration
```

Интеграционные тесты требуют доступного LLM endpoint и могут занимать заметное время из-за локальной генерации. При необходимости проверьте настройки в `config.test.yaml` и переменную `APP_CONFIG_FILE`.

</details>
