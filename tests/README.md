# Организация тестов

## Размещение новых unit-тестов

Основное правило: `tests/unit/<layer>/<feature>/test_<module>.py` повторяет
ответственность проверяемого кода из `src/<layer>/<feature>/<module>.py`.
При отсутствии отдельного подкаталога feature можно разместить
`test_<module>.py` непосредственно в `tests/unit/<layer>/`.
Существующие тесты перемещаются постепенно: массовая перестановка каталогов
не является целью текущего изменения.

Примеры:
- `application.pipeline` → `tests/unit/application/` и
  `tests/unit/application/pipeline/` для тестов отдельных компонентов.
- `infrastructure.visualisation.openapi.dereference` →
  `tests/unit/infrastructure/visualisation/openapi/`.

Два набора тестов dereference оставлены намеренно:
`test_dereference.py` проверяет компактные граничные случаи;
`test_openapi_dereference.py` проверяет расширенные сценарии и интеграцию
развёрнутого OpenAPI со Swagger HTML. Не удаляйте сценарии только из-за
схожих имён тестовых файлов.

## Повторное использование

- Фабрики узлов, рёбер и графов: `tests/factories.py`.
- Общие pytest-фикстуры: `tests/conftest.py`; узкоспециализированные
  фикстуры размещайте в ближайшем локальном `conftest.py`.
- Тестовые модули `test_*.py` не должны импортировать фабрики или функции
  друг из друга: `from tests.unit.test_... import ...` запрещён.
- Вспомогательные классы-заглушки, например `tests/unit/in_memory_writer.py`,
  могут оставаться в самостоятельных модулях без префикса `test_`.
  Не создавайте общий helper ради одного локального теста.

## Обязательные проверки

```bash
uv run pytest --collect-only -q tests/unit
uv run pytest tests/unit
uv run ruff check tests
uv run ruff format --check tests
uv run mypy src tests scripts
```

При переносе тестов сравните число собранных сценариев до и после,
убедитесь, что изменилось лишь расположение, а не смысл проверок.
Полный прогон в CI выполняется по пути `tests/unit`, **не** по маркеру
`pytest.mark.unit`. Интеграционные тесты, требующие LLM, остаются отдельно.
