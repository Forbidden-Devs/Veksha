# Процесс выпуска расширения

GitHub Actions полностью автоматизирует подготовку версии и создание GitHub
Release. Публикация архивов в магазины браузеров остаётся отдельным этапом.

Текущий процесс:

1. Workflow «Prepare extension release» получает `patch`, `minor` или `major`.
2. Скрипт синхронно обновляет версию в `package.json`, `package-lock.json` и
   `manifest.json`, проверяет сборку и создаёт release PR.
3. После merge workflow проверяет, что номер версии увеличился, и создаёт тег
   `extension-vX.Y.Z`.
4. Workflow собирает три артефакта:
   - Chrome ZIP;
   - Firefox ZIP;
   - Firefox source ZIP.

5. Архивы и `SHA256SUMS.txt` сохраняются в артефактах workflow и GitHub Release.
6. Повторный запуск безопасен: существующий корректный тег переиспользуется, а
   файлы существующего Release обновляются.

Чтобы подготовить выпуск, откройте Actions → **Prepare extension release** →
**Run workflow**, выберите `patch`, `minor` или `major`, затем дождитесь CI и
слейте созданный PR. Обычные изменения `package.json` без смены версии релиз не
создают.

Автоматическая публикация в Chrome Web Store и Firefox Add-ons относится к
следующему этапу и должна требовать ручного подтверждения через GitHub
Environment `browser-stores`.
