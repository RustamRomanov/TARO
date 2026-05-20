#!/usr/bin/env bash
# Деплой на Railway: загружает .env и выполняет railway up.
# В .env нужны:
#   RAILWAY_TOKEN — Project Token (проект → Settings → Tokens), не Account token.
#   RAILWAY_SERVICE_ID — ID сервиса (в дашборде: сервис → Settings или в URL).
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
if [ -z "$RAILWAY_TOKEN" ]; then
  echo "В .env нужен RAILWAY_TOKEN (Project Token: проект Astrov → Settings → Tokens)."
  exit 1
fi
if [ -z "$RAILWAY_SERVICE_ID" ]; then
  echo "В .env нужен RAILWAY_SERVICE_ID (ID сервиса из дашборда Railway)."
  exit 1
fi
export RAILWAY_TOKEN
railway up --service="$RAILWAY_SERVICE_ID"
