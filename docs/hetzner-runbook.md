# Hetzner VPS: подготовка и первый деплой

Этот runbook описывает ручной первый запуск Veksha на чистом Hetzner Cloud VPS.
Он не создаёт сервер, DNS или внешнее backup-хранилище автоматически.

## Целевая схема

- один VPS в Singapore;
- Ubuntu 24.04 LTS или Debian 13;
- Docker Engine и Docker Compose v2;
- Caddy принимает только публичные `80/tcp`, `443/tcp` и `443/udp`;
- PWA и backend доступны через отдельные домены;
- PostgreSQL находится только во внутренней Docker-сети;
- admin слушает `127.0.0.1:4173` VPS и открывается через SSH tunnel;
- Telegram-бот запускается в единственном экземпляре через профиль `telegram`;
- ежедневный PostgreSQL dump копируется во внешнее S3-compatible хранилище.

Для сборки всех образов на самом сервере рекомендуется 4 vCPU и 8 GB RAM.
Меньшая машина может быть достаточна для runtime, но сборка web и расширенного
монорепозитория создаёт кратковременные пики CPU, RAM и диска.

## 1. Создание сервера

В Hetzner Cloud Console создайте сервер в Singapore и добавьте SSH key до
первого запуска. Не разрешайте password login. Создайте Cloud Firewall:

- `22/tcp` только с доверенных IP;
- `80/tcp` из любого адреса;
- `443/tcp` и `443/udp` из любого адреса;
- весь остальной входящий трафик запрещён.

После входа обновите систему, создайте пользователя `deploy`, установите Docker
Engine с Compose v2 по официальной инструкции Docker и добавьте `deploy` в
группу `docker`. После повторного входа должны работать:

```bash
docker version
docker compose version
```

Доступ к Docker socket фактически равен root-доступу. Не давайте пользователя
`deploy` приложениям или будущему CI runner.

## 2. Checkout и секреты

Разместите репозиторий в `/srv/veksha`, владельцем сделайте `deploy`. На сервере
используется detached checkout конкретного commit:

```bash
git fetch --all --tags --prune
git switch --detach <commit-sha>
cp .env.production.example .env.production
chmod 600 .env.production
```

Заполните `.env.production`. Для `POSTGRES_PASSWORD` используйте URL-safe
hex-значение, например результат `openssl rand -hex 32`. Значения
`ADMIN_API_SECRET`, `ADMIN_DATABASE_SECRET` и
`VEKSHA_BOT_WEBHOOK_SECRET` должны быть разными. Секреты прежней платформы не
переиспользуются — создаются новые.

Оставьте `VEKSHA_ENVIRONMENT=staging` до завершения всех проверок. При
переключении основного домена явно замените значение на `production`.

До первого запуска настройте DNS `A`/`AAAA` для `VEKSHA_APP_DOMAIN` и
`VEKSHA_API_DOMAIN` на адрес VPS. Google OAuth redirect URI должен точно
совпадать с `https://<api-domain>/api/auth/google/callback`.

`VEKSHA_CORS_ALLOW_ORIGINS` должен содержать PWA origin, локальный admin origin
`http://localhost:4173` и production ID браузерных расширений, если они уже
известны.

## 3. Первый запуск

Скрипт отказывается работать с незакоммиченным или новым неотслеживаемым кодом,
проверяет права файла секретов, валидирует Compose, собирает образы с полным
commit SHA и ждёт healthcheck всех запущенных сервисов:

```bash
./ops/hetzner/deploy.sh
./ops/hetzner/smoke-test.sh \
  https://app.example.com \
  https://api.example.com \
  "$(git rev-parse HEAD)"
```

Первый запуск создаёт пустую PostgreSQL. Данные Railway или старой тестовой
установки не импортируются.

Telegram включается только после заполнения трёх Telegram-переменных. Добавьте
в `.env.production`:

```dotenv
COMPOSE_PROFILES=telegram
```

После этого снова запустите `deploy.sh`. Нельзя запускать более одного
экземпляра бота: он использует long polling.

## 4. Admin

Admin намеренно не имеет публичного домена. Откройте туннель с рабочей машины:

```bash
ssh -N -L 4173:127.0.0.1:4173 deploy@<server-ip>
```

После этого панель доступна на `http://localhost:4173`. Не меняйте bind на
`0.0.0.0` и не публикуйте admin через Caddy до появления SSO с индивидуальными
учётными записями.

## 5. Backup

`backup-postgres.sh` создаёт custom-format `pg_dump`, checksum и хранит локальные
копии семь дней. Локальная копия на том же VPS не считается backup. Установите
`rclone`, настройте отдельное S3-compatible хранилище и создайте root-owned файл
`/etc/veksha/backup.env`:

```bash
sudo install -d -m 0750 /etc/veksha
sudo install -o root -g root -m 0600 /dev/null /etc/veksha/backup.env
```

Его содержимое:

```dotenv
VEKSHA_BACKUP_REMOTE=remote-name:veksha-production/postgres
```

Проверьте ручной запуск и наличие двух файлов в remote storage:

```bash
VEKSHA_BACKUP_REMOTE=remote-name:veksha-production/postgres \
  ./ops/hetzner/backup-postgres.sh
```

После проверки установите systemd units:

```bash
sudo install -m 0644 ops/hetzner/systemd/veksha-backup.service /etc/systemd/system/
sudo install -m 0644 ops/hetzner/systemd/veksha-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now veksha-backup.timer
systemctl list-timers veksha-backup.timer
```

До переключения production-домена выполните пробное восстановление в отдельный
Compose project. Скрипт принимает только пустую базу и отказывается перезаписывать
существующие таблицы:

```bash
VEKSHA_COMPOSE_PROJECT=veksha-restore-test \
  ./ops/hetzner/restore-postgres.sh \
  /path/to/veksha-postgres-<timestamp>.dump
```

После проверки временный project удаляется точной командой:

```bash
docker compose \
  --project-name veksha-restore-test \
  --env-file .env.production \
  -f compose.prod.yaml \
  down --volumes --remove-orphans
```

Никогда не заменяйте здесь project name на `veksha`: это имя основной базы.

## 6. Rollback

`deploy.sh` сохраняет текущую и предыдущую ревизии в `.deployments/`, а старые
образы остаются на сервере. Откат по умолчанию использует предыдущую ревизию:

```bash
./ops/hetzner/rollback.sh
```

Можно передать конкретный commit SHA. Скрипт проверит наличие всех четырёх
application images, переключит checkout на соответствующий commit и дождётся
healthchecks.

Rollback кода не откатывает базу. Любое несовместимое изменение схемы требует
backup перед deploy и отдельной проверенной процедуры возврата данных.

## 7. Критерии готовности к переключению DNS

1. Все контейнеры здоровы после reboot VPS.
2. Публичный smoke-test показывает ожидаемый commit SHA.
3. Работают регистрация, Google OAuth, перевод, Vocabulary Inbox, training и
   lesson WebSocket.
4. Проверены admin и единственный экземпляр Telegram-бота.
5. Backup автоматически появился во внешнем хранилище.
6. Backup успешно восстановлен в отдельную пустую базу.
7. Настроены внешняя проверка `/healthz` и уведомление о недоступности.
8. Зафиксирована команда rollback и сохранён предыдущий application image.
