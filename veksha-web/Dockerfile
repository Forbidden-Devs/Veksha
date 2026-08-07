FROM node:22-alpine AS build

WORKDIR /app

# Install only the web package. Shared extension sources are copied below and
# their React imports are resolved to veksha-web/node_modules by Vite aliases.
COPY veksha-web/package.json veksha-web/package-lock.json ./veksha-web/
RUN npm ci --prefix veksha-web

COPY veksha-web ./veksha-web
COPY veksha-extension/src ./veksha-extension/src
COPY veksha-extension/scripts/sync-i18n.mjs ./veksha-extension/scripts/sync-i18n.mjs
COPY veksha-extension/source/back.png ./veksha-extension/source/back.png
COPY veksha-backend/data/i18n_*.json ./veksha-backend/data/
COPY veksha-backend/data/ui_locales.json ./veksha-backend/data/ui_locales.json

ARG VITE_BACKEND_URL=https://api.veksha.app
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN npm --prefix veksha-web run build

FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production

COPY --from=build /app/veksha-web/dist ./veksha-web/dist
COPY --from=build /app/veksha-web/scripts/serve.mjs ./veksha-web/scripts/serve.mjs

EXPOSE 3000
CMD ["node", "veksha-web/scripts/serve.mjs"]
