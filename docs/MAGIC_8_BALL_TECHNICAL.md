# Техническая реализация «Магический шар предсказаний»

**Актуализация:** апрель 2026.

Документ описывает, как реализован функционал Магического шара (Magic 8-Ball) в приложении ASTROV: структура кода, состояние, жесты, анимации и данные.

---

## 1. Расположение в проекте

| Элемент | Путь |
|--------|------|
| UI-компонент | `frontend/src/components/magic8ball/Magic8Ball.jsx` |
| Массив ответов | `frontend/src/data/magic8BallAnswers.js` |
| Точка входа | Отдельная вкладка нижней навигации: маршрут **`/magic-ball`**, страница `frontend/src/pages/MagicBallPage.jsx` (в профиле могут оставаться дополнительные ссылки на шар, если есть в `Profile.jsx`) |

Модальное окно рендерится через `createPortal(..., document.body)`, чтобы оверлей был поверх всего приложения (z-index 9999). Внутри модалки шар рендерится в **WebGL** через React Three Fiber (Canvas), остальной UI (подсказка, кнопки) остаётся в React/DOM.

---

## 2. Стек 3D-шара (WebGL / Three.js)

- **three**: низкоуровневый 3D-движок.
- **@react-three/fiber**: React-рендерер для Three.js (объявление сцены декларативно).
- **@react-three/drei**: хелперы (Environment, ContactShadows, Lightformer и др.).

Шар — это реальная 3D-сфера в сцене, а не CSS-круг: объём, блики и глубина задаются материалами и освещением.

---

## 3. Состояние компонента (useState)

| Переменная | Тип | Назначение |
|------------|-----|------------|
| `answer` | `string \| null` | Текущий текст ответа; `null` — показывается заглушка «Узнай». |
| `isAnimating` | `boolean` | Идёт ли анимация срабатывания (шар поворачивается к зрителю и масштабируется). |
| `hasResult` | `boolean` | Показан ли уже ответ (для отображения кнопки «Повторить»). |
| `sceneKey` | `number` | Ключ сцены Canvas; при сбросе увеличивается, чтобы пересоздать сцену при новом открытии. |

Углы поворота и масштаб шара хранятся **внутри сцены** в ref’ах (`BallModel`: `targetRef`, `currentRef`, `dragRef`), а не в состоянии корневого компонента.

При закрытии модалки (`open === false`) в `useEffect` вызывается `resetBall(true)`: сбрасываются `answer`, `hasResult`, `isAnimating` и при необходимости `sceneKey`.

---

## 4. Refs (в BallModel и корне)

| Ref | Где | Назначение |
|-----|-----|------------|
| `dragRef` | BallModel | Флаг `active`, стартовые координаты и углы при pointer down, время начала жеста. |
| `targetRef` / `currentRef` | BallModel | Целевые и текущие значения rotation.x, rotation.y, scale; сглаживание через damp в useFrame. |
| `groupRef` | BallModel | Ссылка на group сферы для применения rotation и scale в каждом кадре. |
| `pointerTargetRef` | BallModel | Элемент, захвативший pointer, для releasePointerCapture при pointer up. |
| `timeoutRef` | корень | Таймер задержки перед показом ответа (900 ms). |
| `lastIndexRef` | корень | Индекс последнего выбранного ответа, чтобы не повторять подряд при коротких сериях. |

---

## 5. Вращение шара (pointer events на 3D-объекте)

Обработчики висят на **group** шара внутри Canvas:

- `onPointerDown`: сохраняем координаты и текущие целевые углы, включаем `dragRef.active`, при необходимости `setPointerCapture`.
- `onPointerMove`: при активном перетаскивании считаем дельту от старта и обновляем `targetRef.current.x` / `targetRef.current.y` с ограничением по `MAX_ROT_X`, `MAX_ROT_Y` и коэффициентом `DRAG_SENSITIVITY`.
- `onPointerUp` / `onPointerCancel`: снимаем захват, выключаем перетаскивание; дополнительно проверяем **жест «свайп»** для запуска предсказания (см. ниже).

В `useFrame` текущие углы и масштаб плавно доводятся до целевых через `THREE.MathUtils.damp`; в режиме покоя добавляется лёгкое idle-вращение (синус/косинус от времени).

---

## 6. Срабатывание предсказания (жест «свайп»)

При pointer up в BallModel проверяется, был ли жест достаточно резким:

- `distance` — длина вектора смещения от pointer down до pointer up (пиксели);
- `duration` — время жеста (мс);
- `velocity = distance / duration` (пиксели/мс).

Константы: `FLICK_DISTANCE = 140`, `FLICK_DURATION = 260`, `FLICK_VELOCITY = 0.8`.

Предсказание запускается (`onTriggerPrediction()`), если выполняется **хотя бы одно**:

- `distance >= FLICK_DISTANCE` и `duration <= FLICK_DURATION`, или  
- `velocity >= FLICK_VELOCITY`.

Кнопка «Спросить» также вызывает `triggerPrediction()` без проверки жеста.

---

## 7. Функция triggerPrediction()

1. Защита: если `isAnimating` или `!open` — выход.
2. `setIsAnimating(true)`, `setHasResult(false)`, `setAnswer(null)`.
3. Тактильная отдача: `Telegram.WebApp.HapticFeedback.impactOccurred('medium')` или `navigator.vibrate(70)`.
4. В BallModel через `useEffect` при `isAnimating` целевые углы сбрасываются в 0, целевой масштаб — 1.12.
5. Через 900 ms: один случайный ответ из `MAGIC_8_BALL_ANSWERS` (без повтора подряд), `setAnswer(...)`, `setHasResult(true)`, `setIsAnimating(false)`.

---

## 8. Визуал 3D-шара (сцена)

- **Сфера**: `SphereGeometry(1, 96, 96)`, `MeshPhysicalMaterial` с тёмным цветом (`#1a1e25`), clearcoat, metalness/roughness, **alphaMap** от `createWindowMaskTexture()` — маска рисуется на canvas (белый фон, круглое «окошко» с мягким краем в UV), чтобы на шаре была тёмная поверхность с одним прозрачным кругом.
- **Внутренний объём**: вторая сфера чуть меньше, `BackSide`, полупрозрачная тёмная, чтобы «окно» не выглядело пустым.
- **Колодец окна**: цилиндр перед сферой, тёмный стандартный материал.
- **Дно и подсветка**: круг (дно экрана), поверх него круг с синим полупрозрачным цветом.
- **Ответ**: плоскость с текстурой из `createAnswerTexture(text)` — canvas с синим треугольником и текстом (шрифт Bion), масштаб и opacity анимируются в `AnswerPlate` в useFrame.
- **Стекло и кольцо**: круг с полупрозрачным физическим материалом (transmission), тор для обводки окна.

Освещение: ambient, directional, point lights и **Environment** с Lightformer’ами (прямоугольники и кольцо) для бликов и отражений. ContactShadows под шаром. Фон сцены — тёмный с лёгким синим кругом позади.

---

## 9. Текстуры на Canvas

- **createWindowMaskTexture()**: canvas 2048×1024, в центре фронтальной области сферы (по UV) рисуется радиальный градиент, образующий круглое «окошко»; результат используется как alphaMap основной сферы.
- **createAnswerTexture(text)**: canvas 1024×1024; при непустом `text` рисуется синий треугольник (градиент, тень, точки), затем текст подгоняется по размеру и переносу строк (`fitAnswerText` / `splitIntoLines`, до 3 строк, шрифт Bion). Текстура передаётся в `AnswerPlate` и при смене ответа пересоздаётся (useMemo по `text`), старая dispose в useEffect.

---

## 10. Анимации (Framer Motion и useFrame)

- **Модалка**: `AnimatePresence`; корневой оверлей — opacity; внутренняя карточка — scale, opacity, y при входе/выходе.
- **Шар**: rotation и scale обновляются в `useFrame` через damp к целевым значениям; при `isAnimating` целевые x,y = 0, scale = 1.12.
- **Ответ (AnswerPlate)**: в useFrame opacity и scale плоскости плавно доводятся до целевых в зависимости от наличия текста.

---

## 11. Кнопки

- **Спросить**: всегда видна, при нажатии вызывает `triggerPrediction()`; во время анимации disabled, текст «Смотрим...».
- **Повторить**: показывается при `hasResult === true`; по нажатию `resetBall(true)` (сброс ответа и пересоздание сцены по `sceneKey`).
- **Закрыть**: вызывает `onClose()`. Кнопка «×» в углу карточки также вызывает `onClose()`.

---

## 12. Данные: массив ответов

Файл: `frontend/src/data/magic8BallAnswers.js`.

- Экспорт: `MAGIC_8_BALL_ANSWERS` — массив из 100 строк на русском.
- Выбор: один случайный элемент при каждом срабатывании; при длине > 1 индекс не совпадает с предыдущим (`lastIndexRef`).

---

## 13. Интеграция в Profile

В `Profile.jsx`: импорт `Magic8Ball`, состояние `showMagic8Ball`, кнопка «Шар предсказаний», рендер `<Magic8Ball open={showMagic8Ball} onClose={...} />`. Запросов к бэкенду и датчикам нет.

---

## 14. Зависимости

- **React** (hooks), **react-dom** (createPortal).
- **framer-motion**: motion, AnimatePresence.
- **three**, **@react-three/fiber**, **@react-three/drei**: сцена, сфера, освещение, тени, Environment, хелперы.
- Шрифт **Bion** используется в подсказках модалки и в canvas-текстуре ответа (`createAnswerTexture`).

---

## 15. Краткая схема потока

1. Открытие модалки → Canvas монтируется, шар в начальном положении, текст «Узнай».
2. Пользователь крутит шар пальцем/мышью → pointer events обновляют целевые углы, useFrame сглаживает rotation.
3. Резкий свайп по шару или нажатие «Спросить» → `triggerPrediction()`, шар анимированно поворачивается к зрителю и слегка увеличивается.
4. Через 900 ms показывается один случайный ответ на плоскости в «окошке».
5. «Повторить» сбрасывает ответ и при необходимости пересоздаёт сцену; «Закрыть» закрывает модалку.

Это описание текущей реализации Магического шара на WebGL/Three.js в ASTROV.
