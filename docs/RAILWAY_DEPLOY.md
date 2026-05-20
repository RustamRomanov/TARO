# Деплой Astrov на Railway

## Стек проекта

| Слой       | Технология                         |
|------------|------------------------------------|
| Backend    | Python 3.12, FastAPI, uvicorn      |
| Frontend   | React 18, Vite 6, Tailwind         |
| Бот        | aiogram 3.x (Telegram)             |
| БД         | PostgreSQL (asyncpg)               |
| AI         | OpenAI / совместимый API           |

---

## Шаг 1: Репозиторий GitHub

Репозиторий: https://github.com/RustamRomanov/Astrov

Убедитесь, что закоммичены все изменения:

```bash
git add .
git commit -m "Add Railway config"
git push origin main
```

---

## Шаг 2: Создание проекта в Railway

1. Перейдите на [railway.app](https://railway.app) и войдите через GitHub.
2. **New Project** → **Deploy from GitHub repo**.
3. Выберите репозиторий `RustamRomanov/Astrov`.
4. Railway использует **Dockerfile** (указано в `railway.json`): собирается актуальная версия фронтенда при каждом деплое.

---

## Шаг 3: Добавить PostgreSQL

1. В проекте Railway: **+ New** → **Database** → **PostgreSQL**.
2. После создания нажмите на БД → вкладка **Variables**.
3. Скопируйте `DATABASE_URL` (формат: `postgresql://...`).
4. Для FastAPI нужен asyncpg: замените `postgresql://` на `postgresql+asyncpg://` в URL.

---

## Шаг 4: Переменные окружения (Environment Variables)

В сервисе веб-приложения (не БД) откройте **Variables** и добавьте:

| Переменная          | Описание                         | Пример                    |
|---------------------|----------------------------------|---------------------------|
| `TELEGRAM_BOT_TOKEN`| Токен от @BotFather              | `123456:ABC-...`          |
| `TELEGRAM_BOT_USERNAME` | Имя бота **без** `@` (реферальные ссылки `t.me/...?start=ref_*`) | `MyAstrovBot` |
| `DATABASE_URL`      | URL PostgreSQL (с asyncpg)       | `postgresql+asyncpg://...`|
| `REDIS_URL`         | Redis (кэш, реферальный pending) | `redis://...` |
| `APP_URL`           | URL приложения на Railway        | `https://astrov.up.railway.app` |
| `ASTROV_UPLOADS_DIR` | Каталог для аватаров и вложений (см. [railway-uploads-volume.md](./railway-uploads-volume.md)) | `/data/astrov-uploads` |
| `AI_API_KEY`        | Основной AI (текст + vision)      | ключ OpenAI / VseGPT      |
| `AI_BASE_URL`       | Base URL основного AI            | `https://api.openai.com/v1` |
| `AI_TEXT_MODEL`     | Модель для текста                | `gpt-4o-mini` / и т.д.    |
| `AI_VISION_MODEL`   | Модель для Сканера (психологический портрет, хиромантия) | `gpt-4o` / и т.д.         |
| `DEEPSEEK_API_KEY`  | Запасной AI **только для текста** (в DeepSeek API нет vision) | ключ с [platform.deepseek.com](https://platform.deepseek.com/api_keys) |
| `ADMIN_USERNAME`    | Логин для входа в админку `/admin/login` | `admin` |
| `ADMIN_PASSWORD`    | Пароль админки (обязательно задать в проде) | ваш пароль |
| `BILLING_CRON_SECRET` | Секрет для cron endpoint-ов (`billing`, `reconcile`, `horoscope reminders`) | `long-random-secret` |
| `ASTROMAP_RENDER_MODE` | Режим рендера: `auto`, `skymap`, `playwright` | `playwright` |
| `ASTROMAP_OPENAI_MODE` | Режим стилизации: `off`, `auto`, `required_if_key`, `required` | `required_if_key` |
| `OPENAI_API_KEY` | Ключ OpenAI для финальной стилизации | |
| `OPENAI_GPT_API_KEY` | Резервный ключ OpenAI (опционально) | |
| `SKYMAP_API_KEY` | Ключ SKY-MAP.org (если требуется) | |
| `SKYMAP_BASE_URL` | Base URL API (по умолчанию `http://server2.sky-map.org`) | |
| `SKYMAP_TIMEOUT_SECONDS` | Таймаут запроса (по умолчанию 30) | |
| `SKYMAP_MAX_RETRIES` | Число повторов при ошибке (по умолчанию 2) | |

Если основной AI недоступен или глючит по тексту (гороскопы, таро, сны и т.д.), используется DeepSeek. Сканер (психологический портрет, хиромантия) работает только через основной `AI_VISION_MODEL`.

Без `ADMIN_USERNAME` и `ADMIN_PASSWORD` вход в админку невозможен.

Для качества 1:1 как в референсах:

- `ASTROMAP_RENDER_MODE=playwright` (основной тех-рендер),
- `ASTROMAP_OPENAI_MODE=required_if_key`,
- задан `OPENAI_API_KEY`.

`auto` использует Playwright, при недоступности переключается на SKY-MAP.org. Если доступна только техническая карта SKY-MAP и нет OpenAI стилизации, генерация останавливается с ошибкой качества (плохой результат не отправляется).

---

## Шаг 5: Домен

1. Сервис приложения → **Settings** → **Networking**.
2. **Generate Domain** — в поле порта укажите **8000** (или 8080, если так подскажет Railway).
3. Скопируйте URL вида `astrov-production-xxxx.up.railway.app` и пропишите в `APP_URL`.

---

## Шаг 6: Telegram Mini App

1. Откройте [@BotFather](https://t.me/BotFather).
2. `/mybots` → выберите бота → **Bot Settings** → **Menu Button** (или Web App URL).
3. Укажите URL Mini App: `https://ваш-домен.up.railway.app` (без `/` в конце).

Поделиться раскладом: пользователь нажимает «Отправить в Telegram» — расклад уходит в личку с ботом, приложение остаётся открытым. Чтобы поделиться с другом, пользователь пересылает сообщение из чата с ботом.

---

## Как работает билд (Dockerfile)

1. **Stage 1 (Node):** в образе собирается фронтенд — `npm ci` и `npm run build` в `frontend/`. Папка `frontend/dist` создаётся только на этом шаге (в репозитории её нет — она в `.gitignore`).
2. **Stage 2 (Python):** ставятся зависимости Python, копируются `app/` и **готовая** `frontend/dist` из первого этапа.
3. Запуск: `sh start.sh` → `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
4. FastAPI отдаёт API по `/api/*` и SPA по `/`.

Так на Railway всегда деплоится **последняя версия из репозитория**, без зависимости от кеша билда. Если раньше виделась старая версия — часто причиной был старый Dockerfile без сборки фронта; сейчас фронт собирается внутри образа.

### Дополнительно для AstroMap (Playwright)

Chromium уже устанавливается в `Dockerfile`:

```bash
python -m playwright install chromium
```

Это обязательный шаг для качественной финальной карты в стиле референсов.

---

## ⚠️ Важно: новые ключи

Если `.env` когда-либо попадал в репозиторий — **обязательно смените** `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` и другие секреты. В Railway поставьте свежие значения в Variables.

---

## Деплой через CLI (после push)

Чтобы по команде запускать деплой без браузера (в т.ч. из Cursor/агента):

1. **Project Token**: в Railway открой проект **Astrov** → **Settings** → **Tokens**. Создай токен и скопируй его. (Это не токен с [account/tokens](https://railway.com/account/tokens) — для `railway up` нужен именно Project Token.)
2. **Service ID**: в том же проекте открой свой сервис (веб-приложение) → в **Settings** или в URL дашборда будет ID сервиса (например, длинный UUID). Скопируй его.
3. В `.env` добавь:
   ```bash
   RAILWAY_TOKEN=твой_project_token
   RAILWAY_SERVICE_ID=id_твоего_сервиса
   ```
4. В корне проекта выполни: `./scripts/deploy.sh`.

После этого «пушить и деплоить» = `git push origin main` + `./scripts/deploy.sh`.

---

## Миграции БД перед релизом

После деплоя нового контейнера обязательно примените миграции:

```bash
alembic upgrade head
```

Для текущего релиза будет создана таблица `reminders` для напоминаний гороскопа.

---

## Проверка

- `https://ваш-домен.up.railway.app/` — открывается приложение (SPA).
- `https://ваш-домен.up.railway.app/api/...` — доступны эндпоинты.
- Бот в Telegram отвечает и открывает Mini App.

---

## YooKassa: Webhook и пополнение баланса

1. **Webhook URL** в [Интеграция → HTTP-уведомления](https://yookassa.ru/my/http-notifications-settings):
   - Укажите: `https://ваш-домен.up.railway.app/api/payments/webhook`
   - События: `payment.succeeded`, `payment.canceled`, `payment.waiting_for_capture`

2. **Reconcile cron** (см. ниже) — досверка pending-платежей с YooKassa. Обязателен как резерв, если webhook не дошёл.

3. **YOOKASSA_WEBHOOK_SECRET** — опционален. Если не задан, проверка секрета отключена (безопасность через сверку с YooKassa API).

---

## Cron-план Railway (billing + reconcile + horoscope reminders)

Для стабильной обработки подписок и "зависших" pending-платежей используйте два cron job:

1. **Billing cycle** (основной):
   - Endpoint: `POST /api/payments/billing/run`
   - Рекомендуемый интервал: `*/10 * * * *` (каждые 10 минут)

2. **Reconcile pending** (досверка статусов в YooKassa):
   - Endpoint: `POST /api/payments/billing/reconcile-pending`
   - Body: `{"limit":200}`
   - Рекомендуемый интервал: `*/15 * * * *` (каждые 15 минут), со сдвигом от billing на +2-3 минуты

Все cron endpoint защищены заголовком:

- `X-Billing-Secret: <BILLING_CRON_SECRET>`

3. **Horoscope reminders dispatch** (рассылка напоминаний):
   - Endpoint: `POST /api/horoscope/reminders/dispatch`
   - Рекомендуемый интервал: `*/5 * * * *` (каждые 5 минут)
   - Query (опционально): `?limit=200`

4. **Напоминания об окончании Тарифа VIP** (за 7, 3 и 1 календарный день до `subscription_end_date`, UTC):
   - Endpoint: `POST /api/payments/billing/subscription-expiry-notify`
   - Body: `{"limit":500}`
   - Рекомендуемый интервал: `0 9 * * *` (раз в сутки, по UTC) или `0 10 * * *`

Пример вызовов:

```bash
curl -X POST "https://ваш-домен.up.railway.app/api/payments/billing/run" \
  -H "X-Billing-Secret: ${BILLING_CRON_SECRET}"

curl -X POST "https://ваш-домен.up.railway.app/api/payments/billing/reconcile-pending" \
  -H "Content-Type: application/json" \
  -H "X-Billing-Secret: ${BILLING_CRON_SECRET}" \
  -d '{"limit":200}'

curl -X POST "https://ваш-домен.up.railway.app/api/payments/billing/subscription-expiry-notify" \
  -H "Content-Type: application/json" \
  -H "X-Billing-Secret: ${BILLING_CRON_SECRET}" \
  -d '{"limit":500}'

curl -X POST "https://ваш-домен.up.railway.app/api/horoscope/reminders/dispatch?limit=200" \
  -H "X-Billing-Secret: ${BILLING_CRON_SECRET}"
```

Дополнительно для операционного мониторинга:
- `GET /api/system/runtime-metrics?top=30` с тем же `X-Billing-Secret`.
