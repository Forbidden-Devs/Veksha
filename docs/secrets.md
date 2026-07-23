# Секреты и переменные

Значения секретов никогда не добавляются в Git, документацию, CI artifacts или
логи. Здесь перечислены только места хранения и назначение.

## Railway: backend production

- `OPENAI_API_KEY` — доступ backend к OpenAI.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` — OAuth.
- `TELEGRAM_BOT_USERNAME`, `TELEGRAM_BOT_WEBHOOK_SECRET` — интеграция с ботом.
- `ADMIN_API_SECRET` — временная защита служебных backend endpoint.
- `DATABASE_URL` — подключение к PostgreSQL (при reference-подключении Railway
  передаёт его из PostgreSQL service).
- `VEKSHA_DATA_DIR` — каталог для runtime-файлов; persistent volume для БД
  больше не нужен.
- `CORS_ALLOW_ORIGINS` — разрешённые web origins.
- `REDIS_URL` — необязательный кеш коротких переводов; не содержит
  пользовательские данные и не нужен для корректной работы.

Runtime-секреты остаются в Railway. Они не дублируются в GitHub Actions.

## Railway: Telegram bot

- `TELEGRAM_BOT_TOKEN` — токен от BotFather.
- `VEKSHA_BACKEND_URL` — публичный HTTPS URL backend.
- `VEKSHA_BOT_WEBHOOK_SECRET` — то же значение, что
  `TELEGRAM_BOT_WEBHOOK_SECRET` backend.

## Railway: admin

- `VITE_BACKEND_URL` — HTTPS URL backend, встраивается на этапе сборки.

Административный секрет не встраивается в admin bundle: сотрудник вводит
значение `ADMIN_API_SECRET` при входе, после чего оно живёт только в текущей
вкладке браузера.

## GitHub Environments

Будущие credentials Chrome Web Store и Firefox AMO будут храниться только в
environment `browser-stores` с ручным подтверждением публикации.

## Ротация

Секрет нужно немедленно заменить, если он попал в терминальный вывод, CI log,
issue, pull request, скриншот или историю Git. После ротации старое значение
считается недействительным.
