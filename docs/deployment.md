# Деплой Veksha

Целевая платформа следующей тестовой версии — Hetzner Cloud VPS в Singapore.
Деплой остаётся ручным: push в `master` ничего не разворачивает, CI/CD пока нет.

Production-контур описан в `compose.prod.yaml` и включает Caddy, backend, PWA,
внутреннюю admin-панель, PostgreSQL и необязательный профиль Telegram-бота.
PostgreSQL не публикует host port, admin доступен только на loopback VPS, а
application images помечаются полным commit SHA.

Локальная разработка по-прежнему использует отдельный `compose.yaml`:

```bash
cp .env.example .env
docker compose up --build
```

Подготовка VPS, первый запуск, backups, smoke-test и rollback подробно описаны в
[`hetzner-runbook.md`](hetzner-runbook.md). До прохождения всех критериев из
runbook это staging-подготовка, а не завершённый production deployment.

Следующая версия запускается на пустой базе. Старая инфраструктура и данные не
удаляются автоматически ни одним из добавленных скриптов.
