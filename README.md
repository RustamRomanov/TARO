# TARO

Telegram Mini App: расклады Таро и магический шар предсказаний.

## Локальная разработка

**Бэкенд** (порт 8000):

```bash
cd /path/to/TARO
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
DEBUG=true ALLOW_DEV_AUTH=true python -m app.main
```

**Фронт** (порт 3000, прокси `/api` → 8000):

```bash
cd frontend
npm install
npm run dev
```

Откройте http://localhost:3000/tarot

## Деплой

См. `docs/RAILWAY_DEPLOY.md`.
