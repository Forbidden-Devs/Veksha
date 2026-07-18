# Секреты и переменные

Значения секретов никогда не добавляются в Git, документацию, CI artifacts или
логи. Здесь перечислены только места хранения и назначение.

## Railway: backend production

- `OPENAI_API_KEY` — доступ backend к OpenAI.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` — OAuth.
- `TELEGRAM_BOT_USERNAME`, `TELEGRAM_BOT_WEBHOOK_SECRET` — интеграция с ботом.
- `ADMIN_API_SECRET` — временная защита служебных backend endpoint.
- `VEKSHA_DATA_DIR` — каталог persistent volume.
- `CORS_ALLOW_ORIGINS` — разрешённые web origins.
- `REDIS_URL` — необязательный кеш.

Runtime-секреты остаются в Railway. Они не дублируются в GitHub Actions.

## GitHub Environments

Будущие credentials Chrome Web Store и Firefox AMO будут храниться только в
environment `browser-stores` с ручным подтверждением публикации.

## Ротация

Секрет нужно немедленно заменить, если он попал в терминальный вывод, CI log,
issue, pull request, скриншот или историю Git. После ротации старое значение
считается недействительным.
