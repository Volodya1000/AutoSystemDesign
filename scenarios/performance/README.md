# Реальные ручные прогоны анализа производительности

Тут хранятся **четыре валидных YAML** с функциональными и нефункциональными
требованиями. Это входные сценарии для LLM-генерации, не зафиксированные C4
графы. Поэтому ожидать на каждой модели **одинаковые узлы и цифры запрещено**.

## Подготовка

- Python 3.13 и `uv sync --locked --all-groups`.
- Доступный OpenAI-compatible LLM и настройки через `.env`/`config.yaml`.
- Запуск из корня репозитория.
- При необходимости отключить внешнее построение изображений опцией
  `--no-diagram`: это **не отключает** Performance Analysis или его PDF.
- Каждый YAML запускайте в **отдельной папке**: файлы разных прогонов
  не должны друг друга перезаписывать.

## Команды

```bash
uv run python scripts/generate_pipeline.py --scenario scenarios/performance/checkout_baseline.yaml --out-dir output/acceptance/checkout --no-diagram

uv run python scripts/generate_pipeline.py --scenario scenarios/performance/catalog_read_heavy.yaml --out-dir output/acceptance/catalog --no-diagram

uv run python scripts/generate_pipeline.py --scenario scenarios/performance/notifications_spiky.yaml --out-dir output/acceptance/notifications --no-diagram

uv run python scripts/generate_pipeline.py --scenario scenarios/performance/helpdesk_no_workload.yaml --out-dir output/acceptance/helpdesk --no-diagram
```

Проверьте в соответствующем каталоге:
`checkout_baseline_performance_analysis.json` и
`checkout_baseline_performance_analysis.pdf` (аналогично для других).
**JSON обязателен**, PDF должен появляться при доступном системном шрифте.
Ошибки необязательного PDF должны оставлять JSON и объяснение warning.

## Машинная проверка сохранённых артефактов

После выполнения реального прогона можно проверить JSON/PDF без повторного вызова LLM:

```bash
uv run python scripts/check_performance_acceptance.py --out-dir output/acceptance/checkout --scenario checkout_baseline --require-pdf
uv run python scripts/check_performance_acceptance.py --out-dir output/acceptance/catalog --scenario catalog_read_heavy --require-pdf
uv run python scripts/check_performance_acceptance.py --out-dir output/acceptance/notifications --scenario notifications_spiky --require-pdf
uv run python scripts/check_performance_acceptance.py --out-dir output/acceptance/helpdesk --scenario helpdesk_no_workload --expect-status unavailable --require-pdf
```

Код выхода **0** означает, что локальные артефакты прошли структурные проверки;
**1** означает отказ. Даже успешная проверка файлов **не доказывает** правильность
LLM-архитектуры, end-to-end стадий и соблюдение p95/p99. Сверяйте вывод с полным
логом и [корневым чек-листом](../../docs/performance-analysis/ROOT_PR_ACCEPTANCE.md).

## Матрица ожиданий

| YAML | Фокус | Обязательное поведение |
| --- | --- | --- |
| checkout_baseline | Заказ и платёж, пиковый 60 RPS | Валидный C4/JSON, p99 не подтверждается средним |
| catalog_read_heavy | Чтение 95%, пик 600 RPS | Валидный JSON; если есть cache, его распределение требует проверки |
| notifications_spiky | Асинхронная доставка, пик 400 RPS | Async не удлиняет синхронный критический путь |
| helpdesk_no_workload | Нет workload | `status=unavailable`, код `workload_missing` |

Заданные ограничения latency и availability — **требования**, не измерения.
Результат вроде `mean=40ms` никогда не доказывает `p99<=450ms`.

## Как отправлять материалы для оценки

Присылайте ссылку на HEAD/CI, **точную команду**, полный лог с финальными
статусами стадий и кодом выхода, C4 JSON, JSON отчёта, PDF при наличии,
и список остальных результатов (Sequence/OpenAPI). Секреты из `.env`
не прикладывать.

Подробный протокол решений **PASS / PASS WITH WARNINGS / FAIL / INCONCLUSIVE**
и все блокирующие критерии главного PR:
[ROOT_PR_ACCEPTANCE.md](../../docs/performance-analysis/ROOT_PR_ACCEPTANCE.md).

### Пример минимального отчёта для переписки

```text
Git SHA:
CI URL:
Python / LLM model:
Scenario:
Command:
Exit code:
C4: succeeded | partial | failed
Performance analysis: succeeded | partial | failed
Sequence: succeeded | partial | failed | skipped
API: succeeded | partial | failed | skipped
JSON path / size:
PDF path / size:
Key warnings:
Attached: full log, C4 JSON, performance JSON, PDF
```

Если C4 не сформирован из-за сбоя LLM, это **не** математическая регрессия.
Но реальный end-to-end прогон всё равно не считается пройденным.
