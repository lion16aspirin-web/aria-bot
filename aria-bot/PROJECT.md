# PROJECT.md — ARIA Bot

## Статус
Фаза 1 — реалізація (in progress)

## Стек
- Python 3.11+
- discord.py 2.x (prefix + slash commands)
- anthropic SDK (Claude claude-sonnet-4-20250514)
- SQLite через aiosqlite
- python-dotenv для конфігурації

## Acceptance criteria — Фаза 1
- [ ] `!статус <тип> <локація>` зберігає статус в БД і оновлює повідомлення в #org-статус
- [ ] Статус скидається на офлайн при disconnect з Discord
- [ ] `!місія створити <назва>` розгортає embed-картку з кнопками ролей
- [ ] Гравці реєструються на ролі через кнопки; картка оновлюється live
- [ ] Нагадування за 1 годину до старту місії (автоматично)
- [ ] `@ARIA додай до мого складу / корп складу` парсить позиції і зберігає в БД
- [ ] `@ARIA покажи мій склад` — ARIA відповідає актуальним списком

## Acceptance criteria — Фаза 2
- [ ] @ARIA відповідає на вільний текст через Claude API з контекстом організації
- [ ] ARIA знає поточні статуси, склади, активні місії
- [ ] `@ARIA підготуй склад для місії X` — логістичний план

## Acceptance criteria — Фаза 3
- [ ] `@ARIA ціна <товар> <локація>` — UEX Corp API
- [ ] `@ARIA маршрут бюджет X` — оптимальний торговий маршрут

## Структура файлів
```
aria-bot/
├── CONCEPT.md          # ключова ідея (незмінна)
├── PROJECT.md          # цей файл
├── main.py
├── config.py
├── database.py
├── modules/
│   ├── status.py
│   ├── missions.py
│   ├── inventory.py
│   ├── intel.py        # Фаза 3
│   └── aria.py
├── utils/
│   └── formatters.py
├── .env.example
└── requirements.txt
```

## Поточні рішення
- Prefix команди (`!`) для статусів і місій; mention (@ARIA) для AI-чату та складу
- SQLite + aiosqlite — достатньо для малої організації, легко деплоїти
- Один файл БД `aria.db` поруч з main.py
- ARIA system prompt зберігається в aria.py, отримує контекст з БД динамічно
