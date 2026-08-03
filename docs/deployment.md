# Деплой Veksha

Целевая платформа следующей тестовой версии — netcup VPS 500 G12 в Nuremberg с
Debian 13. Деплой остаётся ручным: push в `master` ничего не разворачивает,
CI/CD пока нет.

Production-контур описан в `compose.prod.yaml` и включает Caddy, backend, PWA,
внутреннюю admin-панель, PostgreSQL и необязательный профиль Telegram-бота.
PostgreSQL не публикует host port, admin доступен только на loopback VPS, а
application images собираются локально для `linux/amd64`. Тег образа содержит
полный commit SHA и окружение, например `<sha>-staging`; VPS получает готовый
release archive и никогда не собирает исходный код.

Локальная разработка по-прежнему использует отдельный `compose.yaml`:

```bash
cp .env.example .env
docker compose up --build
```

Подготовка VPS, локальная сборка, первый запуск, backups, smoke-test и rollback
подробно описаны в [`vps-runbook.md`](vps-runbook.md). До прохождения критериев из
runbook это staging-подготовка, а не завершённый production deployment.

Следующая версия запускается на пустой базе. Скрипты не импортируют данные со
старых платформ и не удаляют данные автоматически.
