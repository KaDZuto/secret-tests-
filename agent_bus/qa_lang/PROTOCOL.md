# PROTOCOL — сообщения шины qa_lang

Формат тот же, что у основной шины (`agent_bus/README.md`): JSONL, одно сообщение на строку.
Разделение только в файлах: `inbox.jsonl` читают, `outbox.jsonl` пишут.

```json
{"id": "qa-sao-001", "from": "main", "to": "qa_lang", "type": "request",
 "task": "text_review:sao", "payload": {"story": "data/story_sao.json", "tag": "sao",
 "note": "что особенно смотреть"}, "created_at": "2026-09-28T22:00:00Z"}
```

| поле | что это |
|---|---|
| `id` | уникальный идентификатор сообщения |
| `from` | кто пишет: `main` (человек, главный агент) или `qa_lang` (шина проверки) |
| `to` | `qa_lang` для заявки, `main` для ответа |
| `type` | `request` — заявка, `response` — ответ, `status` — состояние |
| `task` | `text_review:<tag>`, где `<tag>` — метка сюжета в `tasks.json` |
| `payload` | свободный объект; для заявки важны `story` и `tag` |
| `created_at` | ISO 8601, UTC |

## Типы задач

- `request` с `payload.story` — подготовить пакеты (`scan`). Человек делает это сам, агент может
  попросить.
- `request` с `payload.tag` — проверить уже подготовленные пакеты.
- `status` — сколько пакетов закрыто; пишет `bus.py status`.
- `response` — отчёт после `finish`: сколько машинных находок, сколько строк агент назвал плохими.

## Ответ агента

`finish` сам дописывает в `outbox.jsonl` строку вида:

```json
{"id": "qa-sao-report", "from": "qa_lang_bus", "to": "main", "type": "report",
 "task": "text_review:sao", "payload": {"message": "..."}, "created_at": "..."}
```

Полный отчёт лежит в `agent_bus/qa_lang/report.md` и `report.json`. Ответ в шине — короткая
строка, чтобы не тащить весь отчёт в чужой контекст.

## `tasks.json`

Создаётся командой `scan`, человек его не правит. Один объект на метку:

```json
{"tasks": {"sao": {"story": ".../data/story_sao.json", "name": "story_sao.json",
                   "packets": ["sao-01", "sao-02"], "done": [],
                   "size": 8, "findings": {"ERROR": 20, "WARN": 122, "INFO": 7},
                   "questions": ["meaning: ...", "..."]}}}
```

`done` — пакеты с принятым ответом. Пустой бланк в `verdicts/` означает «пакет не отвечен»:
команда `verdict` требует заполнить все поля явно, а `finish` считает незаполненный бланк
ошибкой, а не «всё хорошо».
