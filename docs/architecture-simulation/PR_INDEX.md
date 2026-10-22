# Индекс PR: дискретно-событийная проверка архитектуры

Индекс — это **история проверяемых решений**, а не дубликат ROADMAP. Номер этапа из [ROADMAP.md](ROADMAP.md) и номер GitHub PR не совпадают автоматически.

| Этап | PR | Изменение |
| --- | --- | --- |
| 0 | [#114](https://github.com/Volodya1000/AutoSystemDesign/pull/114) | ТЗ, пользовательский макет, модель SimPy, статистическая дисциплина, дорожная карта, финальный чек-лист |
| 1 | [#126](https://github.com/Volodya1000/AutoSystemDesign/pull/126) | Pydantic-контракт результата и конфигурация через существующий AppSettings, числовой инвариант учёта запросов и unit-тесты |
| 2 | [#132](https://github.com/Volodya1000/AutoSystemDesign/pull/132) | Детерминированное расписание, реальный SimPy Resource, один узел, независимые каналы, FIFO; [объяснение с числовыми примерами](02-single-node-kernel.md) |
| 3 | [#140](https://github.com/Volodya1000/AutoSystemDesign/pull/140) | Поток Пуассона, Gamma/константа, независимые повторы, warm-up, horizon, event budget; [учебная глава](03-stochastic-replications.md) |
| 4A | [#141](https://github.com/Volodya1000/AutoSystemDesign/pull/141) | Отображение C4 с явными каналами, проверкой DAG и сохранением исходных лимитов; [объяснение](04-graph-mapping.md) |
| 4B | [#142](https://github.com/Volodya1000/AutoSystemDesign/pull/142) | SimPy выполнение линейного синхронного пути, отдельные реплики, сетевые задержки и цензурирование; [пример](04b-linear-graph-executor.md) |
| 5 | [#143](https://github.com/Volodya1000/AutoSystemDesign/pull/143) | Per-replica admission, отдельные причины отказов, инвариант completed/rejected/unfinished; [разбор](05-bounded-admission.md) |
| 6–11 | Не созданы | Маршрутизация → статистика → NFR → pipeline → PDF → E2E |
| 12 | Не создан, необязательный | Эксперименты с альтернативами архитектуры |

## Из предыдущей фичи

- [#90: root аналитической модели СМО](https://github.com/Volodya1000/AutoSystemDesign/pull/90).
- [Индекс её PR](../performance-analysis/PR_INDEX.md), [полный roadmap](../performance-analysis/ROADMAP.md), [чек-лист](../performance-analysis/ROOT_PR_ACCEPTANCE.md).
- Важный урок [#113](https://github.com/Volodya1000/AutoSystemDesign/pull/113): несколько `Merged` дочерних PR **не означают**, что все изменения достигли root head. Проверяйте достижимость коммитов, diff и CI на конечном SHA.

## При добавлении каждого дочернего PR

Обновить таблицу настоящими: **ссылка, base/head, этап, контракт, эталонное числовое поведение, ограничения, статус тестов**. Блокировать merge дочернего PR без понятного обучающего MD и regression tests. Root PR не вливать в `master` до завершения [финальной приёмки](ROOT_PR_ACCEPTANCE.md).
