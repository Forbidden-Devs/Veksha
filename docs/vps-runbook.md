# netcup VPS: локальная сборка и ручной деплой

Этот runbook описывает первый запуск Veksha на netcup VPS 500 G12 в Nuremberg.
Сервер работает на Debian 13 (`amd64`), application images собираются локально
для `linux/amd64` и передаются на VPS как проверяемый release archive.

## Целевая схема

- netcup VPS 500 G12: 2 vCore, 4 GB RAM, 128 GB NVMe;
- Docker Engine и Docker Compose v2 на VPS;
- Caddy публикует только `80/tcp`, `443/tcp` и `443/udp`;
- PostgreSQL доступен только во внутренней Docker-сети;
- admin слушает `127.0.0.1:4173` и открывается через SSH tunnel;
- Telegram-бот является необязательным профилем и запускается в одном экземпляре;
- ежедневный PostgreSQL dump копируется во внешнее S3-compatible хранилище;
- VPS не содержит репозиторий, Git credentials или build toolchain.

## 1. Базовая подготовка VPS

Создайте пользователя `deploy`, настройте вход только по SSH key, отключите
password/root SSH login и оставьте SCP Screen аварийным каналом. В netcup
Firewall разрешите ingress:

- `22/tcp` с доверенного IP (или временно из любого адреса при динамическом IP);
- `80/tcp`, `443/tcp` и `443/udp` из любого адреса;
- ICMP для диагностики.

Не создавайте EGRESS rules без полного allow-list: первое такое правило меняет
остальной исходящий трафик на DROP.

Установите Docker Engine из официального Debian repository, добавьте `deploy` в
группу `docker` и проверьте после повторного входа:

```bash
docker version
docker compose version
docker run --rm hello-world
```

Создайте каталоги:

```text
/srv/veksha/bin
/srv/veksha/incoming
/srv/veksha/releases
/srv/veksha/shared
/srv/veksha/backups
/srv/veksha/state
```

## 2. Секреты и DNS

До первого release передайте шаблон с рабочей машины:

```bash
rsync .env.production.example \
  deploy@<server>:/srv/veksha/shared/.env.production
ssh deploy@<server> chmod 600 /srv/veksha/shared/.env.production
```

Заполните файл на VPS. Оставьте `VEKSHA_ENVIRONMENT=staging` до прохождения всех
проверок. `VEKSHA_REVISION` и `VEKSHA_IMAGE_TAG` являются validation-заглушками:
установщик экспортирует проверенные значения из release manifest.

Создайте новые значения для `POSTGRES_PASSWORD`, `ADMIN_API_SECRET`,
`ADMIN_DATABASE_SECRET` и `VEKSHA_BOT_WEBHOOK_SECRET`; они должны отличаться.
Для URL-safe значения подходит результат `openssl rand -hex 32`. Старые секреты
не переиспользуются.

Настройте DNS `A`/`AAAA` для `VEKSHA_APP_DOMAIN` и `VEKSHA_API_DOMAIN` на VPS.
Google OAuth redirect URI должен точно совпадать с
`https://<api-domain>/api/auth/google/callback`.

## 3. Локальные проверки и release

Перед сборкой запустите тесты затронутых компонентов и приведите Git в чистое
состояние. Builder отказывается работать при изменённых или неотслеживаемых
файлах.

На машине с Docker Buildx:

```bash
./ops/vps/build-release.sh staging api-staging.example.com
```

Builder:

1. берёт полный Git SHA;
2. создаёт тег `<sha>-staging`;
3. собирает backend, web, admin и bot для `linux/amd64`;
4. проверяет архитектуру каждого image;
5. создаёт `releases/veksha-<sha>-staging.tar.gz` и `.sha256`.

Web и admin зависят от API domain во время сборки, поэтому staging и production
release одного SHA имеют разные image tags.

## 4. Загрузка и установка

```bash
./ops/vps/upload-release.sh \
  releases/veksha-<sha>-staging.tar.gz \
  deploy@<server>
```

Скрипт проверяет локальный checksum, обновляет server-side tools, загружает
архив через `rsync` и запускает installer. Installer повторно проверяет архив и
внутренний `images.tar`, валидирует manifest, выполняет `docker load`, запускает
Compose с `--no-build` и ждёт healthcheck. Текущая версия доступна через
`/srv/veksha/current`, предыдущая записана в `/srv/veksha/state/previous`.

Первый запуск создаёт пустую PostgreSQL. Данные старой тестовой установки не
импортируются.

После появления DNS выполните с рабочей машины:

```bash
./ops/vps/smoke-test.sh \
  https://app-staging.example.com \
  https://api-staging.example.com \
  "$(git rev-parse HEAD)"
```

## 5. Admin и Telegram

Admin открывается только через tunnel:

```bash
ssh -N -L 4173:127.0.0.1:4173 deploy@<server>
```

Панель будет доступна на `http://localhost:4173`. Не публикуйте `4173` через
firewall или Caddy.

Telegram включается после заполнения трёх Telegram variables:

```dotenv
COMPOSE_PROFILES=telegram
```

После изменения env повторно установите текущий или следующий release. Нельзя
запускать более одного экземпляра long-polling бота.

## 6. Backup и проверка восстановления

Установите `rclone`, настройте отдельное S3-compatible хранилище и создайте
root-owned файл `/etc/veksha/backup.env`:

```dotenv
VEKSHA_BACKUP_REMOTE=remote-name:veksha/staging/postgres
```

Проверьте backup вручную:

```bash
VEKSHA_BACKUP_REMOTE=remote-name:veksha/staging/postgres \
  /srv/veksha/bin/backup-postgres.sh
```

Должны появиться custom-format dump и `.sha256` локально и в remote storage.
После проверки установите units, которые upload script помещает на VPS:

```bash
sudo install -m 0644 /srv/veksha/shared/systemd/veksha-backup.service /etc/systemd/system/
sudo install -m 0644 /srv/veksha/shared/systemd/veksha-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now veksha-backup.timer
systemctl list-timers veksha-backup.timer
```

До production выполните восстановление в отдельный пустой Compose project:

```bash
VEKSHA_COMPOSE_PROJECT=veksha-restore-test \
  /srv/veksha/bin/restore-postgres.sh \
  /path/to/veksha-postgres-<timestamp>.dump
```

Удаляйте только тестовый project:

```bash
VEKSHA_REVISION=$(sed -n 's/^revision=//p' /srv/veksha/current/manifest.env) \
VEKSHA_IMAGE_TAG=$(sed -n 's/^image_tag=//p' /srv/veksha/current/manifest.env) \
docker compose \
  --project-name veksha-restore-test \
  --env-file /srv/veksha/shared/.env.production \
  -f /srv/veksha/current/compose.prod.yaml \
  down --volumes --remove-orphans
```

Никогда не заменяйте project name здесь на `veksha`: это основная база.

## 7. Rollback

После второго успешного release:

```bash
/srv/veksha/bin/rollback.sh
```

Можно передать конкретный release ID. Скрипт проверяет наличие release directory
и всех четырёх images, активирует старый Compose и сверяет backend revision.
Повторный rollback возвращает только что отключённую версию.

Rollback кода не откатывает базу. Несовместимое изменение схемы требует backup
перед release и отдельной проверенной процедуры возврата данных.

## 8. Критерии production

1. Контейнеры healthy после reboot VPS.
2. Публичный smoke-test показывает ожидаемый Git SHA.
3. Работают регистрация, OAuth, перевод, Inbox, training и lesson WebSocket.
4. Проверены admin и единственный экземпляр Telegram-бота.
5. Backup появился во внешнем хранилище.
6. Backup восстановлен в отдельную пустую базу.
7. Настроена внешняя проверка `/healthz` и уведомления.
8. Второй release и rollback прошли успешно.
