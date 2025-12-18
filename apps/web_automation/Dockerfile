ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:latest
FROM ${PLAYWRIGHT_IMAGE}

WORKDIR /app

COPY apps/web_automation/server.mjs /app/server.mjs

ENV PORT=8085
EXPOSE 8085

CMD ["node", "/app/server.mjs"]

