# Секреты и переменные

Значения секретов никогда не добавляются в Git, документацию, артефакты или
логи. Локальный запуск использует `.env`, созданный из `.env.example`, а первый
Hetzner staging — `.env.production`, созданный из `.env.production.example`.
Оба файла исключены из Git.

## Backend

- `OPENAI_API_KEY` — доступ backend к OpenAI.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` — OAuth.
- `TELEGRAM_BOT_USERNAME`, `TELEGRAM_BOT_WEBHOOK_SECRET` — интеграция с ботом.
- `ADMIN_API_SECRET` — временная защита служебных endpoint.
- `ADMIN_DATABASE_SECRET` — отдельный секрет SQL-консоли админки; он должен
  отличаться от `ADMIN_API_SECRET`.
- `DATABASE_URL` — явное подключение к PostgreSQL.
- `CORS_ALLOW_ORIGINS` — разрешённые web origins.
- `REDIS_URL` — необязательный кеш без пользовательских данных.
- `VEKSHA_ENVIRONMENT` — `local` для разработки и другое явное значение в
  будущем hosted runtime.
- `VEKSHA_REVISION` — идентификатор исходной ревизии, возвращаемый healthcheck.

## Telegram bot и admin

Боту нужны `TELEGRAM_BOT_TOKEN`, `VEKSHA_BACKEND_URL` и
`VEKSHA_BOT_WEBHOOK_SECRET`. Последний совпадает с
`TELEGRAM_BOT_WEBHOOK_SECRET` backend.

Admin получает `VITE_BACKEND_URL` во время сборки. `ADMIN_API_SECRET` и
`ADMIN_DATABASE_SECRET` не встраиваются в bundle: сотрудник вводит их вручную,
и они живут только в текущей вкладке браузера.

## Будущий hosting

На первом Hetzner VPS production-секреты хранятся в доступном только владельцу
`deploy` файле `/srv/veksha/.env.production` с mode `600`; шаблон находится в
`.env.production.example`. Это переходное решение до появления отдельного
secret manager. Секреты из Railway не переносятся как есть — для Hetzner они
перевыпускаются.

Credentials внешнего backup-хранилища находятся в конфигурации `rclone`, а
несекретный адрес remote — в `/etc/veksha/backup.env`. Эти файлы не добавляются
в Git и не попадают в application images.

Секрет немедленно ротируется, если он попал в терминальный вывод, build log,
issue, pull request, скриншот или историю Git.
