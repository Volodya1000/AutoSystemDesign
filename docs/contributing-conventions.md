# Правила оформления изменений

Используем **Conventional Commits** для сообщений коммитов и заголовков PR:

```text
feat(domain): добавить новый валидатор
fix(pipeline): устранить потерю результата стадии
test(ci): проверить доменные инварианты
refactor(api): разделить обязанности компонентов
docs: уточнить инструкции запуска
chore(deps): обновить инструменты
```

Проверка выполняется на GitHub для каждого PR в `master` через Commitizen и локально в `commit-msg` hook. Установить оба типа hook:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Проверка полного диапазона коммитов включает только текущую ветку PR, поэтому старые исторические сообщения переименовывать не нужно.

## Обязательная запись в changelog

Каждый обычный PR добавляет **один краткий фрагмент** в `changelog.d/`. Пример:

```text
changelog.d/+better-validator.feature.md
changelog.d/+repair-fix.bugfix.md
changelog.d/+ci-tests.misc.md
```

Запись должна описывать результат для пользователя или разработчика, а не перечислять изменённые файлы. Удобно использовать номер issue: `123.feature.md`. Не привязанные к issue фрагменты должны начинаться с `+`.

Проверка CI:

```bash
uv run --with towncrier==26.9.0 towncrier check --compare-with origin/master
```

Выпуск версии (на отдельной ветке выпуска, после проверки результата):

```bash
uv run --with towncrier==26.9.0 towncrier build --draft --version 0.1.0
uv run --with towncrier==26.9.0 towncrier build --yes --version 0.1.0
```

В результате формируется `CHANGELOG.md`, а использованные фрагменты удаляются. Пороговая проверка не пытается проверять смысл текста: это задача code review. Релизный PR, меняющий сам `CHANGELOG.md`, освобождён от требования нового фрагмента штатным поведением Towncrier.

**Внимание к старым PR:** после включения нового обязательного workflow ранее открытые PR тоже будут проверяться; перед merge им понадобится changelog-фрагмент либо отдельная политика исключений.
