# Документация ASTROV

**Актуализация структуры и архитектуры:** апрель 2026.

Этот каталог описывает продукт, API, фронтенд и эксплуатацию. Тематические справочники (Таро, ключи судьбы) дополняют общие документы и не дублируют полный список эндпоинтов.

---

## С чего начать

| Документ | Содержание |
|----------|------------|
| [TECHNICAL.md](./TECHNICAL.md) | Стек, структура репозитория, конфиг, деплой, ссылки |
| [APP_FULL_SPEC.md](./APP_FULL_SPEC.md) | Краткая спецификация продукта и модулей |
| [BACKEND.md](./BACKEND.md) | Сервисы, БД, бот, админка, платежи |
| [FRONTEND.md](./FRONTEND.md) | Маршруты, контексты, ключевые компоненты |
| [FUNCTIONALITY.md](./FUNCTIONALITY.md) | Каталог возможностей для пользователя |
| [USER_CAPABILITIES.md](./USER_CAPABILITIES.md) | Ценность и сценарии |
| [RAILWAY_DEPLOY.md](./RAILWAY_DEPLOY.md) | Переменные окружения и деплой на Railway |
| [railway-uploads-volume.md](./railway-uploads-volume.md) | Постоянное хранилище для `ASTROV_UPLOADS_DIR` |

---

## Модули и вкладки (технически)

| Документ | Тема |
|----------|------|
| [TABS_TECHNICAL_INDEX.md](./TABS_TECHNICAL_INDEX.md) | Индекс техдоков по вкладкам |
| [TAB_GOROSCOPE_TECHNICAL.md](./TAB_GOROSCOPE_TECHNICAL.md) | Гороскоп (`/home`, `HoroscopeSkyWidget`) |
| [TAB_SONNIK_TECHNICAL.md](./TAB_SONNIK_TECHNICAL.md) | Сонник (`/dreams`) |
| [TAB_TARO_TECHNICAL.md](./TAB_TARO_TECHNICAL.md) | Таро (`/tarot`) |
| [TAB_SCANNER_TECHNICAL.md](./TAB_SCANNER_TECHNICAL.md) | Сканер (`/scanner`) |
| [TAB_PROFILE_TECHNICAL.md](./TAB_PROFILE_TECHNICAL.md) | Профиль (`/profile/*`) |
| [MAGIC_8_BALL_TECHNICAL.md](./MAGIC_8_BALL_TECHNICAL.md) | Магический шар (`/magic-ball`) |
| [HOROSCOPE.md](./HOROSCOPE.md) | Бэкенд и фронт модуля гороскопа (детально) |

---

## Таро и нумерология (справочники)

| Документ | Назначение |
|----------|------------|
| [TAROT_TAB.md](./TAROT_TAB.md) | Обзор вкладки Таро |
| [TAROT_TECHNICAL_IMPLEMENTATION_FULL.md](./TAROT_TECHNICAL_IMPLEMENTATION_FULL.md) | Реализация |
| [TAROT_CARD_DESCRIPTIONS.md](./TAROT_CARD_DESCRIPTIONS.md) | Описания карт |
| [TAROT_KNOWLEDGE.md](./TAROT_KNOWLEDGE.md) | База знаний |
| [TAROT_VISUAL_ANALYSIS.md](./TAROT_VISUAL_ANALYSIS.md) | Визуальный анализ |
| [tarot_tz_smoke_checklist.md](./tarot_tz_smoke_checklist.md) | Чеклист smoke |
| [KEYS_OF_DESTINY.md](./KEYS_OF_DESTINY.md) | Ключи судьбы (контент) |

---

## Прочее

| Документ | Назначение |
|----------|------------|
| [TECH_DOCUMENTATION.md](./TECH_DOCUMENTATION.md) | Короткий указатель на этот README |
| [ROADMAP.md](./ROADMAP.md) | Планы и технический долг |
| [STEP_BY_STEP_FULL_ACCESS.md](./STEP_BY_STEP_FULL_ACCESS.md) | БД и полный доступ (пошагово) |
| [BACKEND_CHECK.md](./BACKEND_CHECK.md) | Локальная проверка API |

---

## Важные маршруты фронтенда (React Router)

- `/home` — гороскоп
- `/magic-ball` — магический шар (отдельная вкладка нижней навигации)
- `/tarot` — Таро
- `/scanner` — анализ фото (Vision)
- `/profile/*` — профиль, натальная карта, нумерология
- `/dreams` — сонник (маршрут есть; в нижней панели не выделен отдельной кнопкой)
- `/numerology` — редирект на `/profile`

Нижняя навигация (`BottomNav`): Гороскоп, Шар, Таро, Анализ, Профиль (5 пунктов).

---

## Ключевые API (обзор)

Полный перечень: OpenAPI `/docs` у запущенного backend. Ниже типичные группы:

- **Авторизация и профиль:** `/api/user/auth`, `/api/user/profile/sync`, профили пользователя
- **Гороскоп (главная):** `POST /api/horoscope/new` (основной виджет на `/home`); также `POST /api/horoscope/personalized` (legacy), действия в `horoscope_routes`
- **Платежи и рефералы:** `/api/payments/*`, в т.ч. `POST /api/payments/referral/claim`, `POST /api/payments/referral/info`
- **Таро, сны, vision, нумерология:** см. [BACKEND.md](./BACKEND.md)

Переменная **`TELEGRAM_BOT_USERNAME`** нужна для генерации реферальных ссылок. Каталог загрузок: **`ASTROV_UPLOADS_DIR`** (аватары и вложения).
