# Презентация AutoSystemDesign

Исходник презентации хранится в репозитории, чтобы его можно было версионировать вместе с проектом и обновлять по мере изменения реализации.

## Сборка

Нужен LuaLaTeX. Из каталога `presentation/` выполните:

```bash
lualatex main.tex
lualatex main.tex
```

Повторный запуск нужен, чтобы корректно обновить номера слайдов.

Пока изображения отсутствуют, вместо них выводятся подписанные рамки-заполнители. Добавьте файлы с точными именами:

- `images/diagrams/requirements_document.png` — пример входного документа требований;
- `images/diagrams/c4_architecture.png` — C4-диаграмма;
- `images/diagrams/sequence_req_msg_01.png` — Sequence для доставки сообщения;
- `images/diagrams/sequence_req_msg_02.png` — Sequence для подтверждения прочтения;
- `images/diagrams/swagger_endpoints.png` — Swagger UI: операции и маршруты;
- `images/diagrams/swagger_schemas.png` — Swagger UI: схемы запросов и ответов.

Для кириллицы используется доступный системный шрифт с запасным вариантом Latin Modern Sans.

Примечание: BRD обычно означает *Business Requirements Document* (документ бизнес-требований).
