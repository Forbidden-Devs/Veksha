# Разработка Veksha

Основная ветка — `master`. Работа ведётся через короткие feature-ветки без
дополнительной ветки `develop`. Один pull request должен решать одну связанную
задачу.

## Перед открытием pull request

- Не добавляйте секреты, пользовательские данные, базы и собранные архивы.
- Запустите проверки затронутого компонента.
- Опишите пользовательский результат и способ проверки.
- Отдельно укажите изменения runtime-контракта или переменных окружения.

## Проверки

Автоматический CI временно отключён. Автор изменения запускает локально:

- backend: `python -m compileall -q .`,
  `python -m ruff check --select E9,F63,F7,F82 .` и
  `python -m pytest -q` в `veksha-backend/`; перед тестами запустите из корня
  `docker compose --profile test up -d --wait postgres-test`;
- Telegram-бот: те же compile/Ruff/pytest проверки в `veksha-tgbot/`;
- extension: `npm run typecheck`, `npm run test:version`,
  `npm run version:check` и `npm run release` в `veksha-extension/`;
- web: `npm run typecheck` и `npm run build` в `veksha-web/`;
- admin: `pnpm run typecheck`, `pnpm run test` и `pnpm run build` в
  `veksha-admin/`.

Web также проверяется при изменении extension, поскольку пока напрямую
использует его popup/shared исходники. В pull request перечислите фактически
запущенные команды и результаты; зелёного удалённого check сейчас нет.

## Деплой

Push в `master` ничего не разворачивает. Следующая версия готовится к ручному
деплою локально собранного release конкретного commit SHA на netcup VPS; до
прохождения staging-runbook это не считается production-контуром. Решение описано в
[`docs/next-version.md`](docs/next-version.md), а процедура — в
[`docs/deployment.md`](docs/deployment.md).
