# Процесс выпуска расширения

Эта автоматизация относится к следующему этапу CI/CD. Текущий CI уже создаёт и
сохраняет проверочные Chrome, Firefox и Firefox source ZIP, но не публикует их.

Целевой процесс:

1. Workflow «Prepare extension release» получает `patch`, `minor` или `major`.
2. Автоматически обновляет одну исходную версию и создаёт release PR.
3. После merge создаётся тег `extension-vX.Y.Z`.
4. CI собирает три уже поддерживаемых артефакта:
   - Chrome ZIP;
   - Firefox ZIP;
   - Firefox source ZIP.

5. Артефакты сохраняются в GitHub Release.
6. Публикация в магазины требует ручного подтверждения через GitHub Environment
   `browser-stores`.
