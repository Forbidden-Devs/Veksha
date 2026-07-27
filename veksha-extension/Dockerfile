FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_BACKEND_URL=http://localhost:8000
ENV VITE_BACKEND_URL=$VITE_BACKEND_URL
RUN npm run build

FROM alpine:3.22

COPY --from=build /app/dist /artifacts
VOLUME ["/output"]
CMD ["sh", "-c", "find /output -mindepth 1 -maxdepth 1 -exec rm -rf {} + && cp -R /artifacts/. /output/ && echo 'Extension builds copied to veksha-extension/dist'"]
