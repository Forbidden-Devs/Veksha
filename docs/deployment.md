## Как открыть PR:

Основная ветка master, работа ведётся через короткие feature-ветки без develop.
PR открываем на один "тикет".

## Для каждого pull request:
  * backend: тесты;
  * extension: typecheck, сборка Chrome и Firefox, проверка manifest;
  * web: typecheck и production build;
  * bot: тесты и проверка запуска;
  * admin: typecheck, тесты и build;
  * общая итоговая проверка CI, обязательная перед merge.
# Деплой Veksha

## Текущая схема

- GitHub — источник кода и проверок.
- Railway project содержит production backend.
- Backend подключён к ветке `master` и каталогу `/veksha-backend`.
- Railway `Wait for CI` не начинает deploy, пока GitHub workflow на push не
  завершится успешно.
- Watch path `/veksha-backend/**` не позволяет изменениям других приложений
  перезапускать backend.
- Telegram bot и внутренняя admin-панель разворачиваются отдельными Railway
  services из `/veksha-tgbot` и `/veksha-admin`.
- Пользовательская PWA разворачивается отдельным Railway service с контекстом
  всего репозитория (она импортирует shared-код расширения) и конфигурацией
  `/veksha-web/railway.toml`.

## Backend

Конфигурация сборки и запуска хранится в `veksha-backend/railway.toml`.
Railway проверяет `GET /healthz` до переключения трафика. Endpoint не вызывает
OpenAI, Google или Telegram и возвращает Git commit из
`RAILWAY_GIT_COMMIT_SHA`.

После deploy проверяем:

1. deployment имеет статус `SUCCESS`;
2. `/healthz` возвращает HTTP 200 и `status: ok`;
3. revision совпадает с ожидаемым commit SHA;
4. в runtime logs нет повторяющихся ошибок запуска.

## Telegram bot

Конфигурация находится в `veksha-tgbot/railway.toml`. Сервис использует long
polling, поэтому для него должна быть настроена ровно одна replica. Railway
проверяет `GET /healthz`; затем вручную проверяем `/start`, `/status` и тестовый
инвойс с выбранным набором функций.

Watch path: `/veksha-tgbot/**`. Обязательные переменные перечислены в
`docs/secrets.md`.

## Admin

Конфигурация находится в `veksha-admin/railway.toml`. `VITE_BACKEND_URL`
передаётся при сборке, а публичный домен admin необходимо добавить в
`CORS_ALLOW_ORIGINS` backend. Railway проверяет `GET /healthz`.

Watch path: `/veksha-admin/**`. После deploy проверяем вход, чтение цен,
изменение одной цены с возвратом исходного значения и создание ограниченного
тестового промокода.

## Web / PWA

Service должен собираться из корня репозитория: ограничивать root directory до
`/veksha-web` нельзя, иначе Vite не увидит shared-файлы расширения. В настройке
Railway указываем config path `/veksha-web/railway.toml`. Публичный HTTPS origin
добавляем в `CORS_ALLOW_ORIGINS` backend.

После deploy проверяем `/healthz`, вход через Google, быстрый перевод с
появлением слова в словаре, тренировку, установку PWA и повторный запуск без
сети (оболочка открывается, сетевые действия ожидаемо недоступны).

## Откат

1. В Railway выбрать последний стабильный deployment и выполнить rollback.
2. Если проблема находится в коде, сделать revert отдельным commit в `master`.
3. Дождаться успешного CI и нового Railway deployment.
4. Повторно проверить `/healthz` и пользовательский сценарий.

Production нельзя исправлять только через ручные настройки: устойчивое изменение
должно быть отражено в Git или задокументированной переменной Railway.
