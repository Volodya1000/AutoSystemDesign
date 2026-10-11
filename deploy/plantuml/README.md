# Локальный сервер PlantUML

Самостоятельно размещённый экземпляр [plantuml-server](https://github.com/plantuml/plantuml-server) для полностью автономного рендеринга диаграмм. Стандартная библиотека C4 включена в образ, поэтому исходящий доступ к сети не требуется.

## Запуск / остановка

    docker compose -f deploy/plantuml/docker-compose.yaml up -d
    docker compose -f deploy/plantuml/docker-compose.yaml down

## Использование в качестве бэкенда для диаграмм

Для отдельного запуска:

    uv run python scripts/generate_design.py --diagram-server http://localhost:8080

Или как значение по умолчанию для проекта в `config.yaml`:

    visualisation:
      server: http://localhost:8080

## Усиление безопасности

Порт публикуется только на loopback-интерфейсе; контейнер сбрасывает все capabilities, запрещает повышение привилегий, работает с корневой файловой системой только для чтения и с ограничением по памяти.
