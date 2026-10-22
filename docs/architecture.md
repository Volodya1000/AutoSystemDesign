# Именование интерфейсных контрактов

В проекте словом «протокол» обозначаются **два разных понятия**:

- `typing.Protocol` задаёт структурный контракт между компонентами Python без наследования от реализации.
- `domain.models.protocols.ConnectionProtocol` является **Pydantic-моделью протокола взаимодействия узлов** (HTTP, gRPC и т. д.), а не интерфейсом Python.

Это правило касается только **классов, наследующих `typing.Protocol`**.

## Правила

1. Имя каждого `typing.Protocol` оканчивается ровно на `Protocol`, например `ArchitectureDesignerProtocol` и `PipelineStageProtocol`. Не использовать `PortProtocol` или `ProtocolProtocol`.
2. Если модуль содержит преимущественно интерфейсные контракты, он называется `protocols.py`. Для нескольких групп контрактов в одном пакете допустимы точные имена `service_protocols.py`, `document_scenario_protocols.py` и т. п.
3. Небольшой контракт может оставаться рядом с тесно связанными типами или реализацией, когда выделение модуля только ухудшает навигацию. Текущие примеры: `application/document_reader.py` (ошибка ввода и читатель), `application/requirements_extraction.py` (контракт и сервис), `application/pipeline/stage.py` (`StageId` и исполняемая стадия), `application/pipeline/stages/sequence.py` (приватный контракт результата), `infrastructure/visualisation/plantuml/renderer.py` (изображения и их адаптеры).
4. Реализации получают самостоятельные предметные имена, например `ArchitectureDesignerAgent`, `KrokiImageRenderer`, `FileArtifactWriter`. Суффикс `Protocol` не добавляется реализациям.
5. Не переименовывать `BaseModel`, `ABC`, enum, DTO или транспортные протоколы только из-за общего слова «интерфейс».
6. Зависимости application от реализации в infrastructure не появляются при механической миграции. Смена имени контракта не должна менять его методы, сигнатуры или исполняемое поведение.

## Примеры размещения

| Сфера | Контракт | Модуль |
| --- | --- | --- |
| Генерация архитектуры | `ArchitectureDesignerProtocol` | `application/protocols.py` |
| Конвейер | `ArtifactWriterProtocol` | `application/pipeline/protocols.py` |
| Сервисы генерации | `DesignGeneratorProtocol` | `application/pipeline/service_protocols.py` |
| Извлечение сценария | `DocumentScenarioMapperProtocol` | `application/document_scenario_protocols.py` |
| PDF-отчёт | `PerformanceReportPdfRendererProtocol` | `application/performance_analysis/protocols.py` |
| Визуализация | `DiagramSourceBuilderProtocol` | `infrastructure/visualisation/plantuml/protocols.py` |

## При переименовании

- Проверять все импорты, аннотации, тесты и строковые пути, используемые в `patch` / `monkeypatch`.
- Не добавлять бессмысленные алиасы со старым именем в код приложения. Никакой стабильный публичный Python API для старых импортов не обещан.
- Запустить `pytest`, `ruff check`, `mypy` и проверку архитектурных зависимостей по правилам репозитория. Тест `tests/unit/test_protocol_naming.py` защищает само соглашение от регрессии.
