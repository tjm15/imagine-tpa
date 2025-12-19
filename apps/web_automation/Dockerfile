ARG NODE_IMAGE=node:22-alpine
FROM ${NODE_IMAGE}

# Install Playwright dependencies (includes Chromium, Firefox, WebKit)
RUN apk add --no-cache \
    libc6-compat \
    ca-certificates

WORKDIR /app

COPY apps/web_automation/package.json* ./
RUN if [ -f package.json ]; then npm ci --production; else npm install -g playwright; fi

COPY apps/web_automation/server.mjs /app/server.mjs

ENV PORT=8085
EXPOSE 8085

CMD ["node", "/app/server.mjs"]

