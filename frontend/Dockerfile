# angular build served by nginx, which also proxies /api to the backend
FROM node:24-bookworm-slim AS build

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npx ng build --configuration production

FROM nginxinc/nginx-unprivileged:1.30-alpine

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist/frontend/browser /usr/share/nginx/html

# only JOB_* vars get substituted into the template
ENV NGINX_ENVSUBST_FILTER=^JOB_ \
    JOB_API_UPSTREAM=api:8000
