FROM node:22-alpine AS build

WORKDIR /app
RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
ARG VITE_BACKEND_URL=http://localhost:8000
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN pnpm run build

FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PORT=4173

COPY --from=build /app/dist ./dist
COPY --from=build /app/server.mjs ./server.mjs

USER node
EXPOSE 4173
CMD ["node", "server.mjs"]
