#!/usr/bin/env bash
# Локальная разработка TARO: фронт (3000) + бэкенд (8000)
set -e
cd "$(dirname "$0")/.."
echo "=== TARO Local Dev ==="
echo ""
echo "Важно: бэкенд нужно запускать с DEBUG=true и ALLOW_DEV_AUTH=true"
echo ""
echo "Терминал 1 (backend):"
echo "  cd $(pwd) && source venv/bin/activate && DEBUG=true ALLOW_DEV_AUTH=true python -m app.main"
echo ""
echo "Терминал 2 (frontend):"
echo "  cd $(pwd)/frontend && npm run dev"
echo ""
echo "Откройте: http://localhost:3000/tarot"
echo "API проксируется через Vite: /api -> http://localhost:8000"
echo ""
