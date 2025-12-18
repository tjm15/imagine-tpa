ARG NODE_IMAGE=node:alpine
ARG NGINX_IMAGE=nginx:alpine
FROM ${NODE_IMAGE} AS build

WORKDIR /app

COPY apps/ui/package*.json /app/

# Install deps (prefer lockfile when present; otherwise fall back to npm install).
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY apps/ui/ /app/

RUN npm run build

FROM ${NGINX_IMAGE}

COPY apps/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/

EXPOSE 80
