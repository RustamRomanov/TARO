import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, startTransition } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';

import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import { cn } from '../lib/cn';
import { TtsPlayButton } from '../lib/ttsPlayback';
import { Send, Square, Sparkles, Lightbulb, LayoutGrid, Users, ScrollText } from 'lucide-react';
import { TarotInterpretBody, TarotInterpretInline } from '../components/tarot/TarotRichText';
import TarotMagicBallOverlay from '../components/tarot/TarotMagicBallOverlay';
import { tarotDecks } from '../data/tarotDecks';
import { getCardNameRu } from '../data/tarotCardNamesRu';
import { SPREADS, getSpreadHint, getSpreadById, TAROLOGIST_SUGGESTED_QUESTIONS, SPREAD_PICKER_HINTS } from '../data/tarotSpreads';
import { useProfile } from '../context/ProfileContext';
import { useAuth } from '../context/AuthContext';
import { useTarotSession } from '../context/TarotSessionContext';
import { useChromeLayout } from '../context/ChromeLayoutContext';
import { getInitData, getInitDataWithRetry } from '../lib/initData';

/** Под строкой статуса и плашкой «Закрыть» в Telegram WebApp */
const TAROT_BACK_BELOW_TG_HEADER = 'calc(env(safe-area-inset-top, 0px) + 48px)';
/** Контент под одной строкой «← Назад», когда сверху фиксированная полоса */
const TAROT_BELOW_BACK_NAV_ROW = 'calc(env(safe-area-inset-top, 0px) + 48px + 2.75rem)';

/** Единая кнопка «Назад» на экранах Таро (только стрелка; подпись в aria-label для доступности) */
function TarotBackNavButton({ onClick, className }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Назад"
      className={cn(
        'pointer-events-auto inline-flex items-center justify-center py-2.5 px-2 -m-1 text-white text-2xl leading-none rounded-xl active:bg-white/10',
        className,
      )}
    >
      <span aria-hidden>←</span>
    </button>
  );
}

/** Как кнопки «Начать» / «Продолжить» на экране выбора колоды */
const TAROT_MAIN_CTA_CLASS =
  'w-full py-3.5 px-6 rounded-xl font-medium text-base uppercase tracking-wide border transition-colors hover:opacity-95 disabled:opacity-40 disabled:pointer-events-none';
/** Кнопка «Поделиться раскладом» */
const TAROT_SHARE_CTA_STYLE = {
  background: 'rgba(71, 85, 105, 0.5)',
  borderWidth: 1,
  borderColor: 'rgba(148, 163, 184, 0.45)',
  color: '#e2e8f0',
};
const TAROT_GHOST_CTA_CLASS =
  'w-full py-3.5 px-6 rounded-xl font-medium text-sm uppercase tracking-wide border border-white/20 bg-white/5 text-white hover:bg-white/10 transition-colors';
import AccessModal from '../components/billing/AccessModal';
import SimpleSwipePicker from '../components/tarot/SimpleSwipePicker';

const API_BASE = import.meta.env.VITE_API_URL || '';
const ABS_BASE = (typeof window !== 'undefined' ? window.location.origin : '').replace(/\/$/, '');
const TAROT_LAST_DECK_STORAGE_KEY = 'astrov_tarot_last_deck_id';
const TAROT_LAST_SPREAD_STORAGE_KEY = 'astrov_tarot_last_spread_id';
const TAROT_DAILY_LIMIT_MESSAGE = 'Вы исчерпали лимит раскладов на сегодня. Приходите завтра.';
const TAROT_POST_FREE_PROMO_KEY = 'astrov_tarot_post_free_promo_pending';
/** Локальная дата (YYYY-MM-DD): один бесплатный расклад «Карта дня» в сутки без VIP и без welcome. */
const TAROT_SINGLE_CARD_FREE_YMD_KEY = 'astrov_tarot_card_of_day_free_ymd';
const TAROT_ACCESS_MODAL_VIP_EMPHASIS_CLASS = 'text-emerald-300 text-[13px] font-semibold';
/** Совпадает с paddingTop у main для /tarot в MainLayout.jsx: нужен для «прокрутки под шапку». */
const TAROT_MAIN_TOP_INSET = 'calc(max(48px, env(safe-area-inset-top, 0px)) + 2px - 0.1rem)';
const TAROT_RESULT_TOP_SPACER = `calc(${TAROT_MAIN_TOP_INSET.replace(/^calc\((.*)\)$/, '$1')} + 10px)`;
const TAROT_SINGLE_RESULT_TOP_SPACER = `calc(${TAROT_MAIN_TOP_INSET.replace(/^calc\((.*)\)$/, '$1')} - 4px)`;
const TAROT_PICK_DECK_ROW_OFFSET_Y = 19;
/** Нижний отступ многостраничного результата: компактный, без пустого "хвоста" после кнопок. */
const TAROT_RESULT_SCROLL_BOTTOM_MULTI =
  'max(2.75rem, calc(env(safe-area-inset-bottom, 0px) + 2rem))';
/** Пока идёт запрос толкования: одна плашка, факт один на расклад. */
const TAROT_WAITING_FACT_INTRO = 'А пока идет толкование расклада, вот вам интересный факт:';
/** Для «1 карта» и «3 карты»: короткие факты. */
const TAROT_WAITING_FACTS_SHORT = [
  'В классической колоде Райдера-Уэйта 78 карт: 22 Старших и 56 Младших Арканов.',
  'Карта Шут в Таро символизирует старт нового пути и готовность к переменам.',
  'Старшие Арканы чаще показывают ключевые события, а Младшие: повседневные детали.',
  'Масть Кубков связана с эмоциями, чувствами и темой отношений.',
  'Перевёрнутая карта не всегда негативна: чаще это подсказка о внутреннем процессе.',
  'Масть Жезлов отвечает за инициативу, движение и то, что вы готовы запустить в действие.',
  'Масть Мечей проясняет мысли, границы и разговор, который лучше провести прямо и спокойно.',
  'Масть Пентаклей опирается на ресурсы, тело, деньги и практические шаги в реальности.',
  'Позиция в раскладе задаёт роль карты: та же карта в разных местах отвечает на разные части истории.',
  'Таро не «предсказывает железно»: это язык смыслов, который помогает увидеть варианты и акценты.',
  'Тузы в мастях часто отмечают новый заход: импульс, чувство, мысль или ресурс, который только входит в игру.',
  'Суд и Солнце в классике Райдера-Уэйта про разные виды «ясности»: одно про итог и урок, другое про тепло и открытость.',
  'Луна в Таро чаще про туман и воображение, а не про «обман ради зла»: это сигнал перепроверить факты и свои страхи.',
  'Башня резко меняет конструкцию, которую вы уже чувствовали трещинами: это про обнажение правды, а не про «наказание».',
  'Звезда хорошо сочетается с вопросами про восстановление: надежда появляется после честного признания усталости.',
  'Сила говорит о мягкой уверенности: удерживать импульс без подавления, вести себя спокойно и последовательно.',
  'Колесница про движение к цели и управление риском: скорость полезна, если вы держите руль и видите дорогу.',
  'Отшельник уместен, когда нужна пауза и пересборка: уйти на высоту, оглянуться и вернуться с одним выводом.',
  'Справедливость любит взвешенные формулировки: договор, границы, ответственность и честный подсчёт фактов.',
  'Дьявол в раскладе чаще про привычку и «липкость» ситуации, чем про злодея снаружи: спросите, что вас цепляет.',
];
/** Для остальных раскладов: длинные факты (примерно в 3 раза больше по объёму). */
const TAROT_WAITING_FACTS_LONG = [
  'Современное чтение Таро часто опирается на образ и контекст: вы смотрите не на «приговор судьбы», а на карту как на сцену, где видны роли, напряжение и ресурс. Именно поэтому один и тот же аркан в разных позициях может звучать по-разному: позиция задаёт вопрос, а карта предлагает ответ в рамках этой роли. Если держать в голове вопрос и честно отмечать эмоции во время расклада, трактовка становится точнее и полезнее в быту.',
  'Кельтский крест любят за то, что он собирает историю в слоях: от фона и прошлого к настоящему, затем к ближайшим помехам и скрытым мотивам, и дальше к совету и перспективе. Хороший разбор здесь похож на диагностику: сначала выясняется «что происходит», потом «почему так держится», и только потом «что можно сделать мягко и реалистично». Такой порядок помогает не перепутать симптом с причиной и не спешить с выводами на середине пути.',
  'Расклады на отношения удобны, когда вы разделяете «чувства», «ожидания», «контакт» и «вектор». Карты редко говорят «оставайся или уходи» одной фразой: чаще они показывают, где тепло, где трение, где неясность и где вы сами можете повлиять диалогом. Если читать связку карт как динамику, а не как ярлыки, получается разговор о зрелости, границах и выборе без лишней драмы.',
  'Финансовые темы в Таро лучше держать приземлённо: Пентакли и положение «препятствие» часто указывают на конкретику, ритм, риски и дисциплину. Полезно закреплять вывод цифрой или маленьким действием: проверить один счёт, сделать одну заявку, убрать один лишний расход. Тогда расклад превращается не в «магическое обещание», а в план на короткий горизонт, который можно проверить фактами.',
  'Этика чтения проста: вы отвечаете за свои решения, а карты помогают увидеть слепые зоны. Таро не заменяет врача, юриста или финансового советника, особенно если речь о здоровье, праве или крупных деньгах. В здравом подходе расклад подсказывает ракурсы и риски, а финальный шаг всегда остаётся за вами, с вашей ответственностью и реальными обстоятельствами.',
  'Прямая и перевёрнутая карта часто читаются как «снаружи / внутри» или «явно / требует донастройки», а не как «хорошо / плохо». Перевёрнутость может означать задержку, внутреннее сопротивление, незрелую форму темы или необходимость вернуться к базовым шагам. Если не цепляться к одному слове, а описать ситуацию целиком, смысл обычно становится мягче и практичнее.',
  'Младшие Арканы хорошо работают как «сюжет на неделю»: Жезлы про запуск, Кубки про чувства и близость, Мечи про ясность и разговор, Пентакли про тело, деньги и быт. Когда вы связываете масть с действием, карты перестают плавать в абстракции и начинают отвечать на вопрос «что сделать небольшим шагом сегодня», не ломая общую картину расклада.',
  'Дневник раскладов сильно улучшает качество: дата, вопрос, карты и одна строка «что сделал(а)». Через пару недель видно, где вы угадывали мотив, где ошибались в тревоге, где тема повторялась. Это не «проверка магии», а тренировка внимательности: вы учитесь отделять интуицию от автоматического страха и от желания услышать готовый ответ.',
  'Визуальные детали колоды тоже часть смысла: цвет, жест, взгляд персонажа, фон. Райдер-Уэйт держит много подсказок в картинке, и иногда одна деталь объясняет «почему именно так», когда текстовая формулировка кажется сухой. Если смотреть на карту как на кадр из фильма, интерпретация становится живее и ближе к вашей реальной сцене.',
  'Разные колоды меняют настроение и акценты, но скелет вопроса остаётся вашим. Одна колода может звучать мягче, другая резче, третья более архетипично. Полезно выбрать колоду, которой вы готовы доверять образам на дистанции: когда язык символов совпадает с вашим восприятием, расклад читается быстрее и без лишнего напряжения.',
  'Старшие Арканы похожи на главы романа: они задают архетип, урок и поворот сюжета. Когда в большом раскладе выпадает несколько Старших подряд, полезно назвать тему одним словом и проверить, не дублирует ли каждая карта одно и то же разными красками. Тогда итог получается связным: вы видите не «много важного», а один большой узел и несколько путей, как с ним обращаться.',
  'Младшие Арканы с цифрами любят отвечать на вопрос «насколько» и «в каком темпе»: двойки и тройки про выбор и первые шаги, семёрки и восьмёрки про ожидание и перегруз, девятки и десятки про завершение цикла. Если читать число как громкость процесса, легче понять, где нужно ускориться, где сбавить, а где просто переждать без самообвинения.',
  'Дворы (паж, рыцарь, королева, король) описывают стиль действия и уровень зрелости, а не «пол» персонажа в вашей жизни. Паж любопытен и учится, рыцарь гонится за целью, королева настраивает среду, король фиксирует рамки. В связке с мастью это даёт конкретику: не «кто-то придёт», а «какой способ поведения сейчас усиливает ситуацию».',
  'Ассы в мастях часто звучат как новая глава: новый импульс, новое чувство, новая ясность или новый ресурс. Они хорошо сочетаются с вопросом «с чего начать», но требуют второй карты, чтобы не остаться в воздухе. Вторая карта показывает, чем эта глава питается и какой первый шаг реально ложится на ваш день.',
  'Если в раскладе много Мечей, разум может быть острым, но усталым: это сигнал проверить сон, тон общения и где вы спорите сами с собой. Мечи любят честность без ярлыков: вместо «всё плохо» лучше «какая мысль съедает энергию». Тогда совет получается рабочим: меньше внутреннего шума, больше одного ясного действия или одного спокойного разговора.',
  'Кубки в большом количестве могут означать сильную эмоциональную вовлечённость, иногда до переполнения. Здесь полезно отличить «хочу» от «могу», «близость» от «зависимости», «заботу» от «контроля». Карты редко осуждают чувство: они чаще показывают, где оно красиво поддерживает, а где начинает подменять границы и здравый смысл.',
  'Жезлы в связке с Пентаклями часто описывают «идея + воплощение»: что хочется запустить и что реально по силам в материи. Если Жезлы доминируют, а Пентаклей мало, есть риск перегрева без результата. Если наоборот, можно застрять в рутине без огня. Смысл расклада тогда в балансе: маленький шаг в теле или в деньгах, который подпитывает мотивацию, а не гасит её.',
  'Повторяющиеся масти в раскладе похожи на повтор мотива в музыке: это не случайность, а акцент. Три Кубка подряд почти всегда про эмоциональную тему, три Пентакля про быт и устойчивость. Когда вы называете повтор вслух, итог становится проще: не распыляться на десять смыслов, а взять одну линию и довести её до практического вывода.',
  'Вопрос формулируйте так, чтобы в нём было место для действия: не «что будет», а «что мне важно понять про …» или «как лучше поступить в …». Таро лучше ложится на вопросы про выбор, мотивы, риски и ближайший горизонт. Чем яснее граница вопроса, тем меньше соблазн натянуть ответ на всю жизнь сразу.',
  'Если трактовка «слишком общая», чаще всего дело не в картах, а в том, что вопрос широкий или внутри есть стыд за желание. Попробуйте переформулировать вслух короче и добавить контекст: срок, роль, что уже пробовали. Часто после этого же расклад начинает «щёлкать», потому что мозгу наконец есть за что зацепиться.',
  'Связка «карта + позиция + сосед» работает как предложение: подлежащее, сказуемое и обстоятельство. Сначала читайте соседей как взаимное влияние, потом позицию как роль, и только потом выводите совет. Так меньше шансов вырвать одну «страшную» карту из контекста и построить на ней лишнюю драму.',
];

const TAROT_WAITING_FACT_STAR_COUNT = 20;
const TAROT_WAITING_FACT_STAR_CYCLE_SEC = 14;

function TarotWaitingFactStarStrip() {
  const n = TAROT_WAITING_FACT_STAR_COUNT;
  const cycleSec = TAROT_WAITING_FACT_STAR_CYCLE_SEC;
  const hatchKeyframesCss = useMemo(() => {
    const hatchSlot = 40 / n;
    const collapseStart = 56;
    const collapseSlot = 38 / n;
    const hatchBurst = Math.min(2.85, hatchSlot + 1.15);
    const collapseBurst = Math.min(2.85, collapseSlot + 1.15);
    const chunks = [];
    for (let i = 0; i < n; i += 1) {
      const a = Number((i * hatchSlot).toFixed(3));
      const b = Number(Math.min(a + hatchBurst, collapseStart - 1).toFixed(3));
      const c = Number((collapseStart + (n - 1 - i) * collapseSlot).toFixed(3));
      const d = Number(Math.min(c + collapseBurst, 99.4).toFixed(3));
      const midH = Number(((a + b) / 2).toFixed(3));
      const midC = Number(((c + d) / 2).toFixed(3));
      chunks.push(
        `@keyframes tarot-waiting-hatch-star-${i}{0%,${a}%{transform:scale(0.06) translateY(0.1em);opacity:0.12}${midH}%{transform:scale(1.12) translateY(0);opacity:1}${b}%{transform:scale(1) translateY(0);opacity:1}${b}%,${c}%{transform:scale(1) translateY(0);opacity:1}${midC}%{transform:scale(0.42) translateY(0.08em);opacity:0.28}${d}%,100%{transform:scale(0.06) translateY(0.1em);opacity:0.12}}.tarot-waiting-fact-loadstar--hatch-${i}{animation:tarot-waiting-hatch-star-${i} ${cycleSec}s cubic-bezier(0.45,0.05,0.55,0.95) infinite}`,
      );
    }
    return chunks.join('');
  }, [n, cycleSec]);

  return (
    <div className="tarot-waiting-fact-edge pointer-events-none select-none overflow-hidden rounded-t-[14px]">
      <style>{hatchKeyframesCss}</style>
      <div className="tarot-waiting-fact-loadrow" aria-hidden>
        {Array.from({ length: n }, (_, i) => (
          <span key={i} className={`tarot-waiting-fact-loadstar tarot-waiting-fact-loadstar--hatch-${i}`}>
            ★
          </span>
        ))}
      </div>
    </div>
  );
}

function getLocalYmd() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function readSingleCardFreeYmd() {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage?.getItem(TAROT_SINGLE_CARD_FREE_YMD_KEY) || '';
  } catch (_) {
    return '';
  }
}

function hasSingleCardFreeBeenUsedToday() {
  return readSingleCardFreeYmd() === getLocalYmd();
}

function markSingleCardFreeUsedToday() {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage?.setItem(TAROT_SINGLE_CARD_FREE_YMD_KEY, getLocalYmd());
  } catch (_) {}
}

function TarotSpreadCostModal({ open, priceRub, onConfirm, onCancel }) {
  if (!open || typeof document === 'undefined') return null;
  return createPortal(
    <div
      className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tarot-cost-title"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-amber-400/35 bg-slate-950/95 px-5 py-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <p id="tarot-cost-title" className="text-center text-amber-100 text-base font-medium mb-1">
          Стоимость расклада
        </p>
        <p className="text-center text-white text-2xl font-semibold tabular-nums mb-6">
          {priceRub} ₽
        </p>
        <button
          type="button"
          onClick={onConfirm}
          className="w-full py-3.5 px-6 rounded-xl font-medium text-sm uppercase tracking-wide border border-amber-400/80 bg-amber-500/20 text-amber-100 hover:bg-amber-500/30 transition-colors"
        >
          Выполнить расклад
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="mt-3 w-full py-2 text-sm text-white/60 hover:text-white/90"
        >
          Отмена
        </button>
      </div>
    </div>,
    document.body
  );
}

/** Текст модалки доступа: акцент «Тариф VIP…» в том же зелёном, что и вкладка VIP. */
const TAROT_ACCESS_MODAL_NO_FUNDS = (
  <>
    На балансе недостаточно средств для этого расклада. Пополните баланс или оформите{' '}
    <span className={TAROT_ACCESS_MODAL_VIP_EMPHASIS_CLASS}>
      Тариф VIP: безлимитный доступ ко всем функциям приложения.
    </span>
  </>
);

const TAROT_ACCESS_MODAL_VIP_HINT = (
  <span className={TAROT_ACCESS_MODAL_VIP_EMPHASIS_CLASS}>
    Оформи VIP: безлимитный доступ ко всем функциям приложения.
  </span>
);

function useTypewriter(text, options = {}) {
  const { charsPerSec = 38, enabled = true, instant = false } = options;
  const [displayedLength, setDisplayedLength] = useState(0);
  const fullText = String(text || '');
  const isComplete = instant || displayedLength >= fullText.length;

  useEffect(() => {
    if (instant) {
      setDisplayedLength(fullText.length);
      return;
    }
    if (!enabled || !fullText) {
      setDisplayedLength(0);
      return;
    }
    setDisplayedLength(0);
    let cancelled = false;
    let len = 0;
    let timeoutId = null;
    const baseMs = 1000 / charsPerSec;
    const tick = () => {
      if (cancelled || len >= fullText.length) return;
      const ch = fullText[len];
      let delay = baseMs * (0.7 + Math.random() * 0.6);
      if (/[.!?;,]\s/.test(fullText.slice(Math.max(0, len - 1), len + 2))) delay += 120 + Math.random() * 80;
      else if (ch === ' ') delay *= 0.6;
      timeoutId = setTimeout(() => {
        if (cancelled) return;
        len += 1;
        setDisplayedLength(len);
        tick();
      }, delay);
    };
    timeoutId = setTimeout(() => {
      if (cancelled) return;
      len = 1;
      setDisplayedLength(1);
      tick();
    }, baseMs);
    return () => {
      cancelled = true;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [fullText, enabled, charsPerSec, instant]);

  return {
    displayedText: instant ? fullText : fullText.slice(0, displayedLength),
    isComplete,
  };
}

/** Соотношение сторон карт таро (ширина/высота) по реальным размерам изображений 500×895 */
const TAROT_ASPECT = 500 / 895;

function sanitizeProfileId(value) {
  const n = Number(value);
  if (!Number.isInteger(n)) return null;
  if (n < -2147483648 || n > 2147483647) return null;
  return n;
}

function shiftHex(hex, delta) {
  const v = Number(hex) || 0;
  const r = Math.max(0, Math.min(255, ((v >> 16) & 255) + delta));
  const g = Math.max(0, Math.min(255, ((v >> 8) & 255) + delta));
  const b = Math.max(0, Math.min(255, (v & 255) + delta));
  return (r << 16) | (g << 8) | b;
}

function hashStringSeed(src) {
  const s = String(src || '');
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6D2B79F5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function getRotatedSuggestedQuestions(spreadId, variant = 0, maxItems = 5) {
  const source = TAROLOGIST_SUGGESTED_QUESTIONS[spreadId] || [];
  if (!source.length) return [];
  const list = [...source];
  const rnd = mulberry32(hashStringSeed(`${spreadId}:${variant}:${source.length}`));
  for (let i = list.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rnd() * (i + 1));
    [list[i], list[j]] = [list[j], list[i]];
  }
  return list.slice(0, Math.max(1, Math.min(maxItems, list.length)));
}

function useTarotDecks(rawDecks) {
  const [decksReady, setDecksReady] = useState(
    () => (rawDecks || []).map((d) => ({ ...d, backImage: '', deckImage: '' }))
  );
  const cardImageCache = useRef(new Map());

  useEffect(() => {
    if (!rawDecks?.length) {
      setDecksReady([]);
      return;
    }
    let cancelled = false;
    (async () => {
      const results = await Promise.allSettled(
        rawDecks.map(async (d) => {
          const backImage = d.backImageLoader ? await d.backImageLoader().catch(() => '') : '';
          const deckImage = d.deckImageLoader ? await d.deckImageLoader().catch(() => '') : '';
          return { ...d, backImage, deckImage };
        })
      );
      if (cancelled) return;
      const resolved = results
        .map((r, idx) => (r.status === 'fulfilled' ? r.value : { ...rawDecks[idx], backImage: '', deckImage: '' }))
        .filter(Boolean);
      setDecksReady(resolved);
    })();
    return () => { cancelled = true; };
  }, [rawDecks?.length]);

  const resolveCardImage = async (card, deckId) => {
    if (!card) return '';
    if (card.image) return card.image;
    const key = deckId ? `${deckId}:${card.id}` : card.id;
    const cached = cardImageCache.current.get(key);
    if (cached) return cached;
    if (!card.imageLoader) return '';
    try {
      const url = await card.imageLoader();
      cardImageCache.current.set(key, url);
      return url;
    } catch {
      return '';
    }
  };

  return { decks: decksReady, resolveCardImage };
}

const EMPTY_TAROT_DECK = {
  id: 'empty',
  name: 'Колоды загружаются',
  description: 'Подождите, загружаем изображения колод.',
  cards: [],
  backClass: 'tarot-back tarot-back--cosmic',
  backImage: '',
  color: '0b162e',
};

// ТЗ: константы анимации Таро
const TAROT_ANIM = {
  DECK_LEFT_INSET: 25,
  DECK_RIGHT_INSET: 25,
  BOTTOM_GAP_FROM_TABS: 54,
  FLY_RIGHT_DURATION_MS: 2000,
  FLY_LEFT_DURATION_MS: 2000,
  STAGGER_PER_CARD_MS: 120,
  // Базовый расклад: 3 карты по центру → поочерёдный переворот
  BASIC_FLIP_STAGGER_MS: 500,
  // Другие расклады (FanDeck): расфокус
  BASIC_DEFOCUS_MS: 1400,
  SMOOTH_EASE: [0.32, 0.72, 0.36, 1],
  // Остальные расклады (дуга и т.д.)
  ARC_SPREAD_DURATION_MS: 2000,
  FLY_EASE: [0.22, 1, 0.36, 1],
  ARC_EASE: [0.22, 1, 0.36, 1],
  CARD_FLIGHT_TO_FORMATION_MS: 1200,
  SCATTER_DURATION_MS: 1500,
  FIGURE_RISE_DURATION_MS: 1800,
  LEVITATION_AMPLITUDE_PX: 3,
  LEVITATION_DURATION_S: 2.5,
  BASIC_HANG_MS: 2000,
  CINEMATIC_CARD_DURATION_MS: 1000,
  CINEMATIC_STAGGER_MS: 180,
  ANALYSIS_MIN_MS: 1800,
};

const SPREAD_IMAGE_MAP = {
  single: '/tarot-spreads/basic.png',
  three_cards: '/tarot-spreads/quick.png',
  financial: '/tarot-spreads/financial.png',
  six_cards: '/tarot-spreads/relationship.png',
  ten_cards: '/tarot-spreads/celtic.png',
};

function pluralCards(n) {
  if (n === 1) return '1 карту';
  if (n >= 2 && n <= 4) return `${n} карты`;
  return `${n} карт`;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function shuffleArray(src) {
  const arr = Array.isArray(src) ? [...src] : [];
  for (let i = arr.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

/** Минимум реплик пользователя до автостарта (как TAROLOGIST_MIN_USER_TURNS_FOR_AUTO на бэкенде). */
function tarologistMinUserTurnsForAuto(spreadId) {
  switch (spreadId) {
    case 'three_cards':
      return 1;
    case 'financial':
    case 'six_cards':
      return 4;
    case 'ten_cards':
      return 3;
    default:
      return 1;
  }
}

function tarologistReplyStartsSpread(replyText) {
  const t = String(replyText || '').toLowerCase();
  if (!t) return false;
  const hasStartIntent = /(начинаю расклад|перехожу к раскладу|запускаю расклад|выполняю расклад|выполню расклад|сейчас выполняю расклад|сейчас сделаю расклад|делаю расклад|раскладываю|беру\s+[^.!?\n]{0,40}\s+карт)/i.test(t);
  const hasBlockerIntent = /(не могу|недостаточно|уточни|нужно уточнение|нужны уточнения|задай вопрос|нужно больше информации)/i.test(t);
  return hasStartIntent && !hasBlockerIntent;
}

function tarologistReplyReadyForExecute(replyText) {
  const t = String(replyText || '').toLowerCase();
  if (!t) return false;
  const hasReadyIntent = /(готов[а-я]*\s+выполнить\s+расклад|готов[а-я]*\s+сделать\s+расклад|если\s+готов[а-я]*|могу\s+начать\s+расклад|можем\s+начинать\s+расклад|могу\s+перейти\s+к|перейти\s+к\s+кельтскому\s+кресту|выполнить\s+расклад\?|подтверди[тй]?|напиши\s+«?(да|хочу)»?)/i.test(t);
  const hasStartNowIntent = /(начинаю расклад|запускаю расклад|перехожу к раскладу)/i.test(t);
  return hasReadyIntent && !hasStartNowIntent;
}

function tarologistReplyAskedExecuteQuestion(replyText) {
  const t = String(replyText || '').toLowerCase();
  if (!t || !t.includes('?')) return false;
  return /(выполнить\s+расклад|сделать\s+расклад|перейти\s+к\s+раскладу|начать\s+расклад)/i.test(t);
}

function tarologistUserAffirmative(text) {
  const t = String(text || '').trim().toLowerCase();
  if (!t) return false;
  return /^(да|давай|хочу|ок|окей|ага|готов|готова|поехали|начинай|запускай)([!.?,\s].*)?$/i.test(t);
}

function tarologistBuildQuestionFromMessages(messages = [], forcedQuestion = '') {
  const forced = String(forcedQuestion || '').trim();
  if (forced && !tarologistUserAffirmative(forced)) return forced;

  const userMessages = (Array.isArray(messages) ? messages : [])
    .filter((m) => m?.role === 'user')
    .map((m) => String(m?.content || '').trim())
    .filter(Boolean);

  const meaningful = userMessages.filter((text) => {
    if (tarologistUserAffirmative(text)) return false;
    if (/^(привет|здравствуйте|добрый\s+(день|вечер|утро)|спасибо|благодарю|ок|окей|ага)$/i.test(text)) return false;
    return text.includes('?') || text.length >= 10;
  });

  if (meaningful.length) return meaningful[meaningful.length - 1];

  const fallback = userMessages.filter((text) => !tarologistUserAffirmative(text));
  if (fallback.length) {
    return fallback.slice().sort((a, b) => b.length - a.length)[0];
  }
  return '';
}

function _cleanupTarologistOption(text) {
  return String(text || '')
    .replace(/^.*?:\s*/i, '')
    .replace(/^это\s+больше\s+про\s+/i, '')
    .replace(/^скорее\s+/i, '')
    .replace(/^про\s+/i, '')
    .replace(/[.?!]+$/g, '')
    .replace(/^["«'\s]+|["»'\s]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function _isGoodTarologistOption(option) {
  const o = String(option || '').trim();
  if (!o) return false;
  if (o.length < 2 || o.length > 42) return false;
  if (/[,:;]/.test(o)) return false;
  if (/выполнить\s+расклад/i.test(o)) return false;
  const words = o.split(/\s+/).filter(Boolean);
  return words.length >= 1 && words.length <= 7;
}

function tarologistExtractChoiceChips(replyText) {
  const src = String(replyText || '').replace(/\n+/g, ' ').trim();
  if (!src || !/\sили\s/i.test(src)) return [];
  const sentences = src
    .split(/(?<=[.?!])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const withOrQuestion = [...sentences].reverse().find((s) => /\?/.test(s) && /\sили\s/i.test(s));
  const withOrFallback = [...sentences].reverse().find((s) => /\sили\s/i.test(s));
  const targetSentence = withOrQuestion || withOrFallback || '';
  if (!targetSentence) return [];
  const core = targetSentence.includes(':')
    ? targetSentence.slice(targetSentence.lastIndexOf(':') + 1).trim()
    : targetSentence;
  const parts = core
    .replace(/[?]+$/g, '')
    .split(/\s+или\s+/i)
    .map(_cleanupTarologistOption)
    .filter(_isGoodTarologistOption);
  if (parts.length !== 2) return [];
  const uniq = Array.from(new Set(parts)).filter((p) => p.length >= 2 && p.length <= 48);
  return uniq.slice(0, 2);
}

function normalizeTarologistReplyText(text) {
  const raw = String(text || '').trim();
  if (!raw) return '';
  return raw
    .replace(/^\s*(григорий(?:\s+астров)?|таролог)\s*:\s*/i, '')
    .trim();
}

/** Резерв под нижнюю навигацию MainLayout (fixed z-30), иначе кнопки уезжают под «плашку». */
const TAROT_TAB_BAR_RESERVE = 'calc(5.75rem + max(0px, env(safe-area-inset-bottom, 0px)))';

/** Нижний отступ без таб-бара: только safe area (экран чата с тарологом). */
const TAROT_CHAT_BOTTOM_SAFE = 'max(12px, env(safe-area-inset-bottom, 0px))';

/** Чат с тарологом перед раскладом. Фон совпадает с экраном Таро: прозрачный слой поверх vanta/градиента родителя. */
function TarologistChatScreen({
  messages = [],
  onSendMessage,
  suggestedQuestions = [],
  onExecuteSpread,
  isLoading,
  input,
  onInputChange,
  onPromptStageChange,
  onBack,
  /** false: плашка вкладок скрыта, не резервируем высоту под BottomNav. */
  reserveBottomTabBar = false,
}) {
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const blurTimerRef = useRef(null);
  const totalCount = messages.filter((m) => m?.role).length;
  const maxReached = totalCount >= 10;
  const [keyboardVisible, setKeyboardVisible] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const vvHeightRef = useRef(0);
  const typingTimerRef = useRef(null);
  const animatedAssistantKeysRef = useRef(new Set());
  const [animatedAssistant, setAnimatedAssistant] = useState({ index: -1, text: '', done: true });
  const [vvHeight, setVvHeight] = useState(() => (
    typeof window !== 'undefined' ? (window.visualViewport?.height ?? window.innerHeight) : 640
  ));
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let raf = 0;
    let lastKb = false;
    const SHOW_THRESHOLD = 48;
    const HIDE_THRESHOLD = 28;
    const flush = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        raf = 0;
        const h = Math.round(vv.height);
        if (Math.abs(h - vvHeightRef.current) >= 3) {
          vvHeightRef.current = h;
          setVvHeight(h);
        }
        const delta = Math.max(0, Math.round((window.innerHeight || 0) - vv.height));
        const visible = delta > SHOW_THRESHOLD;
        const hidden = delta < HIDE_THRESHOLD;
        const next = lastKb ? !hidden : visible;
        if (next === lastKb) return;
        lastKb = next;
        setKeyboardVisible(next);
      });
    };
    vvHeightRef.current = Math.round(vv.height);
    flush();
    vv.addEventListener('resize', flush, { passive: true });
    vv.addEventListener('scroll', flush, { passive: true });
    return () => {
      vv.removeEventListener('resize', flush);
      vv.removeEventListener('scroll', flush);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);
  useEffect(() => {
    return () => {
      if (typingTimerRef.current) {
        clearTimeout(typingTimerRef.current);
        typingTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!messages.length) {
      animatedAssistantKeysRef.current.clear();
      setAnimatedAssistant({ index: -1, text: '', done: true });
      return;
    }
    const lastIndex = messages.length - 1;
    const lastMessage = messages[lastIndex];
    if (!lastMessage || lastMessage.role !== 'assistant') return;
    const fullText = String(lastMessage.content || '');
    const messageKey = `${lastIndex}:${fullText}`;
    if (animatedAssistantKeysRef.current.has(messageKey)) {
      setAnimatedAssistant({ index: lastIndex, text: fullText, done: true });
      return;
    }
    if (typingTimerRef.current) {
      clearTimeout(typingTimerRef.current);
      typingTimerRef.current = null;
    }
    setAnimatedAssistant({ index: lastIndex, text: '', done: false });
    let cursor = 0;
    const tick = () => {
      cursor += 1;
      const next = fullText.slice(0, cursor);
      const done = cursor >= fullText.length;
      setAnimatedAssistant({ index: lastIndex, text: next, done });
      if (done) {
        animatedAssistantKeysRef.current.add(messageKey);
        typingTimerRef.current = null;
        return;
      }
      let delay = 8 + Math.random() * 12;
      if (/[.!?]\s?$/.test(next)) delay += 32 + Math.random() * 42;
      else if (/[,;:]\s?$/.test(next)) delay += 16 + Math.random() * 26;
      typingTimerRef.current = setTimeout(tick, delay);
    };
    typingTimerRef.current = setTimeout(tick, 40);
  }, [messages]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (messages.length === 0) {
      el.scrollTop = 0;
      return;
    }
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    });
    return () => cancelAnimationFrame(id);
  }, [messages, vvHeight, animatedAssistant.text, animatedAssistant.done]);

  const isAssistantAnimating = !animatedAssistant.done && animatedAssistant.index >= 0;

  const wasLoadingRef = useRef(false);
  useEffect(() => {
    if (wasLoadingRef.current && !isLoading) {
      const t = window.setTimeout(() => {
        inputRef.current?.focus();
      }, 120);
      wasLoadingRef.current = isLoading;
      return () => window.clearTimeout(t);
    }
    wasLoadingRef.current = isLoading;
  }, [isLoading]);

  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const prevBodyOverflow = document.body.style.overflow;
    const prevHtmlOverscroll = document.documentElement.style.overscrollBehavior;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overscrollBehavior = 'none';
    return () => {
      document.body.style.overflow = prevBodyOverflow;
      document.documentElement.style.overscrollBehavior = prevHtmlOverscroll;
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
    };
  }, []);

  const handleSend = () => {
    const t = (input || '').trim();
    if (!t || isLoading) return;
    onInputChange('');
    onSendMessage(t);
  };

  const handleExecuteClick = () => {
    if (isLoading) return;
    onSendMessage('Да');
  };
  /** Пока ждём ответ таролога, держим «режим клавиатуры»: иначе появляется «Выполнить расклад», вёрстка прыгает и WebView закрывает клавиатуру. */
  const typingMode = keyboardVisible || inputFocused || isLoading;
  const chipClass =
    'text-xs px-3 py-1.5 rounded-lg border border-white/20 bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/75';
  const lastAssistantMessage = [...messages].reverse().find((m) => m?.role === 'assistant')?.content || '';
  const choiceChips = tarologistExtractChoiceChips(lastAssistantMessage);
  const showExecuteHintChip = tarologistReplyReadyForExecute(lastAssistantMessage) && !isLoading;
  const showChips = Boolean(suggestedQuestions.length && messages.length < 2 && !typingMode);
  const showChoiceChips = choiceChips.length > 0 && !isLoading;
  const paddingBottom =
    typingMode
      ? 'max(8px, env(safe-area-inset-bottom, 0px))'
      : reserveBottomTabBar
        ? TAROT_TAB_BAR_RESERVE
        : TAROT_CHAT_BOTTOM_SAFE;

  useEffect(() => {
    onPromptStageChange?.(showChips);
  }, [showChips, onPromptStageChange]);

  return (
      <div
        className="fixed left-0 right-0 top-0 z-20 flex flex-col px-3 overflow-hidden bg-transparent outline-none ring-0 focus:outline-none"
        style={{
          height: vvHeight,
          maxHeight: vvHeight,
          paddingTop: 0,
          paddingBottom,
          overscrollBehavior: 'none',
          WebkitTapHighlightColor: 'transparent',
        }}
      >
        {/* Поверх ленты: фон и сообщения доходят до верхнего края WebView, кнопка не съедает высоту колонки */}
        <div
          className="absolute left-0 right-0 z-30 flex justify-start px-3 pointer-events-none"
          style={{ top: TAROT_BACK_BELOW_TG_HEADER }}
        >
          <div className="pointer-events-auto">
            <TarotBackNavButton onClick={onBack} />
          </div>
        </div>
        <div
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden mb-2 overscroll-contain"
          style={{
            WebkitOverflowScrolling: 'touch',
            scrollBehavior: 'auto',
            overflowAnchor: 'none',
            scrollPaddingTop: TAROT_BELOW_BACK_NAV_ROW,
          }}
        >
          {/* Пустой экран: текст у стрелки сверху. С диалогом: пузыри прижаты к полю ввода. */}
          <div
            className={cn(
              'flex w-full flex-col gap-3',
              messages.length === 0 ? 'min-h-0 justify-start' : 'min-h-full justify-end',
            )}
            style={{ paddingTop: TAROT_BELOW_BACK_NAV_ROW }}
          >
            {messages.length === 0 ? (
              <>
                <p className="text-amber-300 text-sm">
                  Вы можете выбрать готовый вопрос или написать свой.
                </p>
                <p className="text-white/50 text-xs">Таролог ждёт вашего сообщения...</p>
              </>
            ) : (
              messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    'rounded-xl px-3 py-2 text-sm max-w-[90%]',
                    m.role === 'user'
                      ? 'ml-auto bg-amber-500/20 border border-amber-400/30 text-amber-100'
                      : m.role === 'system'
                        ? 'mx-auto bg-amber-500/10 border border-amber-400/25 text-amber-100/90 text-xs'
                        : 'mr-auto bg-white/10 border border-white/15 text-white/90'
                  )}
                >
                  {m.role === 'assistant' ? <span className="text-amber-200/80 text-xs">Таролог: </span> : null}
                  {m.role === 'assistant' && animatedAssistant.index === i
                    ? (
                        <>
                          {animatedAssistant.text}
                          {isAssistantAnimating ? <span className="opacity-65">▍</span> : null}
                        </>
                      )
                    : m.content}
                </div>
              ))
            )}
          </div>
        </div>
        {maxReached && !typingMode ? (
          <p className="text-amber-200/80 text-xs mb-2 shrink-0">
            Достаточно информации. Напишите «да», если готовы к раскладу.
          </p>
        ) : null}
        {showExecuteHintChip ? (
          <div className="w-full flex flex-wrap gap-2 mb-2 justify-start items-start self-start text-left shrink-0">
            <button
              type="button"
              disabled={isLoading}
              onMouseDown={(e) => e.preventDefault()}
              onTouchStart={(e) => e.preventDefault()}
              onClick={handleExecuteClick}
              className={cn(chipClass, 'text-amber-100 border-amber-400/40 bg-amber-500/10')}
            >
              Да
            </button>
          </div>
        ) : null}
        {showChoiceChips ? (
          <div className="w-full flex flex-wrap gap-2 mb-2 justify-start items-start self-start text-left shrink-0">
            {choiceChips.map((option) => (
              <button
                key={option}
                type="button"
                disabled={isLoading}
                onMouseDown={(e) => e.preventDefault()}
                onTouchStart={(e) => e.preventDefault()}
                onClick={() => {
                  inputRef.current?.blur();
                  onSendMessage(option);
                }}
                className={cn(chipClass, 'text-left disabled:opacity-50')}
              >
                {option}
              </button>
            ))}
          </div>
        ) : null}
        {showChips ? (
          <div className="w-full flex flex-wrap gap-2 mb-2 justify-start items-start self-start text-left shrink-0">
            {suggestedQuestions.slice(0, 5).map((q, i) => (
              <button
                key={i}
                type="button"
                disabled={isLoading}
                onMouseDown={(e) => e.preventDefault()}
                onTouchStart={(e) => e.preventDefault()}
                onClick={() => {
                  setInputFocused(true);
                  inputRef.current?.focus({ preventScroll: true });
                  onSendMessage(q);
                }}
                className={cn(chipClass, 'text-left disabled:opacity-50')}
              >
                {q}
              </button>
            ))}
          </div>
        ) : null}

        <div className="shrink-0 flex flex-col gap-2 pt-1">
          <div className="flex gap-2 min-w-0 w-full items-stretch">
            <input
              ref={inputRef}
              type="text"
              inputMode="text"
              enterKeyHint="send"
              autoComplete="off"
              autoCorrect="on"
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              onFocus={() => {
                if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
                blurTimerRef.current = null;
                setInputFocused(true);
              }}
              onBlur={() => {
                if (isLoading) {
                  requestAnimationFrame(() => {
                    inputRef.current?.focus({ preventScroll: true });
                  });
                  return;
                }
                blurTimerRef.current = setTimeout(() => {
                  blurTimerRef.current = null;
                  setInputFocused(false);
                }, 180);
              }}
              placeholder="Ваш вопрос..."
              disabled={false}
              readOnly={isLoading}
              className={cn(
                'flex-1 min-w-0 h-11 min-h-[44px] box-border rounded-xl border border-amber-500/30 bg-black/25 px-3 text-base leading-normal text-white placeholder:text-white/40',
                'focus:outline-none focus:ring-0 focus:border-amber-500/30 focus-visible:outline-none focus-visible:ring-0',
                '[-webkit-tap-highlight-color:transparent]',
                isLoading && 'opacity-90'
              )}
              style={{ fontSize: '16px' }}
            />
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onTouchStart={(e) => e.preventDefault()}
              onClick={handleSend}
              disabled={isLoading || !(input || '').trim()}
              aria-label="Отправить"
              className={cn(
                'shrink-0 h-11 min-h-[44px] w-11 min-w-[44px] box-border inline-flex items-center justify-center rounded-xl border border-amber-400/40 bg-amber-500/15 text-amber-200 disabled:opacity-50',
                'focus:outline-none focus:ring-0 focus-visible:outline-none focus-visible:ring-0',
                '[-webkit-tap-highlight-color:transparent]'
              )}
            >
              {isLoading ? (
                <span className="text-sm font-medium">...</span>
              ) : (
                <Send className="w-[1.15rem] h-[1.15rem]" strokeWidth={2.25} aria-hidden />
              )}
            </button>
          </div>
        </div>
      </div>
  );
}

/** Нормализация ключа карты для сопоставления с ответом API (как на бэкенде). */
function normalizeCardKey(val) {
  const raw = String(val ?? '')
    .trim()
    .toLowerCase()
    .replace(/\.(jpg|jpeg|png|webp)$/i, '');
  return raw.replace(/[^a-z0-9]/g, '');
}

function resolveCardTitle(cardId, fallback = '', deckId = '') {
  const normalizeSuitOnlyRu = (value) => {
    const raw = String(value || '').trim();
    if (!raw) return '';
    const suitOnly = new Set(['Жезлов', 'Кубков', 'Мечей', 'Пентаклей', 'Дисков', 'Монет']);
    if (suitOnly.has(raw)) return `Туз ${raw}`;
    return raw;
  };
  const deck = deckId || undefined;
  const ruFromId = getCardNameRu(cardId, deck);
  if (ruFromId && /[А-Яа-яЁё]/.test(ruFromId)) return normalizeSuitOnlyRu(ruFromId);
  const ruFromFallback = getCardNameRu(String(fallback || ''), deck);
  if (ruFromFallback && /[А-Яа-яЁё]/.test(ruFromFallback)) return normalizeSuitOnlyRu(ruFromFallback);
  const cleaned = String(fallback || '').replace(/^\d+[\s._-]*/, '').trim();
  const technicalLike =
    /^[a-f0-9]{24,}(?:[_-][a-f0-9-]{8,})*$/i.test(cleaned)
    || /^(wands|cups|swords|pentacles|disks|coins)\d+$/i.test(cleaned);
  if (cleaned && !technicalLike) return normalizeSuitOnlyRu(cleaned);
  return 'Карта';
}

/** Название карты для отображения: по id, по имени файла из image, затем card_name/name. */
function getCardDisplayName(card) {
  if (!card) return 'Карта';
  const deckForName = card?.astrovDeckId || '';
  const resolved = resolveCardTitle(card.id, card.card_name || card.name || '', deckForName);
  if (resolved && !/^карта$/i.test(resolved)) return resolved;
  const img = card.image;
  if (img && typeof img === 'string') {
    const basename = img.split('/').pop()?.split('?')[0] || '';
    const fromPath = resolveCardTitle(basename, '', deckForName);
    if (fromPath && !/^карта$/i.test(fromPath)) return fromPath;
  }
  return 'Карта';
}

function debugTarotMapping(label, payload) {
  if (!import.meta.env.DEV) return;
  try {
    // Dev-only tracing to catch any position/name/image drift.
    console.groupCollapsed(`[tarot-map] ${label}`);
    console.log(payload);
    console.groupEnd();
  } catch {
    // noop
  }
}

function debugTarologistAutostart(label, payload) {
  if (!import.meta.env.DEV) return;
  try {
    console.groupCollapsed(`[tarot-autostart] ${label}`);
    console.log(payload);
    console.groupEnd();
  } catch {
    // noop
  }
}

function playGoldSparkSound() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(1180, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.055, ctx.currentTime + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.2);
  } catch {
    // ignore audio init issues
  }
}

function CardZoomOverlay({ open, onClose, src, alt = '' }) {
  const frameRef = useRef(null);
  const pinchRef = useRef({ initialDistance: 0, baseScale: 1 });
  const [scale, setScale] = useState(1);

  useEffect(() => {
    if (!open) setScale(1);
  }, [open, src]);

  useEffect(() => {
    const el = frameRef.current;
    if (!open || !el) return;
    const onTouchStart = (e) => {
      if (e.touches.length === 2) {
        pinchRef.current.initialDistance = distance(e.touches[0], e.touches[1]);
        pinchRef.current.baseScale = scale;
      }
    };
    const onTouchMove = (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const d = distance(e.touches[0], e.touches[1]);
        const init = pinchRef.current.initialDistance || 1;
        const base = pinchRef.current.baseScale || 1;
        setScale(Math.min(3, Math.max(1, (base * d) / init)));
      }
    };
    const onTouchEnd = (e) => {
      if (e.touches.length < 2) {
        pinchRef.current = { initialDistance: 0, baseScale: 1 };
      }
    };
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    el.addEventListener('touchcancel', onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchEnd);
    };
  }, [open, scale]);

  if (!open || !src || typeof document === 'undefined') return null;
  const baseW = 306 * scale;
  const baseH = Math.round(306 / TAROT_ASPECT) * scale;
  const maxW = window.innerWidth - 24;
  const maxH = window.innerHeight - 24;
  let w = baseW;
  let h = baseH;
  if (baseW > maxW || baseH > maxH) {
    const fit = Math.min(maxW / baseW, maxH / baseH);
    w = baseW * fit;
    h = baseH * fit;
  }
  return createPortal(
    <motion.div
      className="fixed inset-0 z-[99999] bg-black/85 flex flex-col items-center justify-center p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="mb-3 rounded-full border border-amber-300/60 bg-black/45 px-5 py-2 text-sm text-amber-100"
      >
        Закрыть
      </button>
      <motion.div
        ref={frameRef}
        className="rounded-2xl overflow-hidden shadow-2xl border border-white/10 bg-transparent"
        style={{
          width: w,
          height: h,
          touchAction: 'none',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={src}
          alt={alt}
          className="w-full h-full object-cover rounded-2xl"
        />
      </motion.div>
    </motion.div>,
    document.body
  );
}

const CINEMATIC_SINGLE_DURATION_S = 2.0;
const CINEMATIC_DEFAULT_DURATION_S = 1.1;
const CINEMATIC_STAGGER_S = 0.2;

function getCinematicSpecs(spreadId) {
  if (spreadId === 'single') {
    return [{ x: 50, y: 43, scale: 0.5, rotateZ: 0, delay: 0, fromY: -2 }];
  }
  if (spreadId === 'three_cards') {
    return [
      { x: 23, y: 51, scale: 0.34, rotateZ: -7, delay: 0, fromY: -16 },
      { x: 50, y: 49, scale: 0.35, rotateZ: 3, delay: 0.26, fromY: -18 },
      { x: 77, y: 52, scale: 0.34, rotateZ: -4, delay: 0.52, fromY: -17 },
    ];
  }
  if (spreadId === 'financial') {
    /* Лесенка: диагональ снизу слева наверх вправо. Центры по X симметричны вокруг 50% (26…74%),
     * чтобы отступ от левого края до 1-й карты совпадал с отступом от 5-й до правого (раньше 14/78%
     * давали ~14% слева и ~22% справа). Шаг 12% даёт сильнее нахлест. scale и maxCardW в стейдже
     * увеличены отдельно под размер колоды.
     * y смещены вверх на ~10%, чтобы нижняя карта не перекрывала строку «Прокрути колоду» в FanDeckPick. */
    const s = 0.34;
    return [
      { x: 26, y: 52, scale: s, rotateZ: 0, delay: 0.0, fromY: 16 },
      { x: 38, y: 41, scale: s, rotateZ: 0, delay: 0.15, fromY: 16 },
      { x: 50, y: 31, scale: s, rotateZ: 0, delay: 0.3, fromY: 16 },
      { x: 62, y: 22, scale: s, rotateZ: 0, delay: 0.45, fromY: 16 },
      { x: 74, y: 14, scale: s, rotateZ: 0, delay: 0.6, fromY: 16 },
    ];
  }
  if (spreadId === 'six_cards') {
    /* Те же maxCardW/heightCap, что у «Финансы»; scale ×34/32 от прежних, верх схемы как у финансовой колоды. */
    return [
      { x: 38, y: 21, scale: 0.3, rotateZ: -8, delay: 0.0, fromY: -10 },
      { x: 62, y: 21, scale: 0.3, rotateZ: 8, delay: 0.0, fromY: -10 },
      { x: 50, y: 34, scale: 0.34, rotateZ: 0, delay: 0.2, fromY: -10 },
      { x: 40, y: 51, scale: 0.3, rotateZ: -5, delay: 0.4, fromY: -10 },
      { x: 60, y: 51, scale: 0.3, rotateZ: 5, delay: 0.4, fromY: -10 },
      { x: 50, y: 63, scale: 0.32, rotateZ: 0, delay: 0.6, fromY: -10 },
    ];
  }
  if (spreadId === 'ten_cards') {
    const s = 0.24;
    return [
      { x: 40, y: 34, scale: s, rotateZ: 0, delay: 0.0, fromY: -8 },
      { x: 40, y: 34, scale: s, rotateZ: 90, delay: 0.0, fromY: -8 },
      { x: 40, y: 18, scale: s, rotateZ: 0, delay: 1.0, fromY: -8 },
      { x: 40, y: 54, scale: s, rotateZ: 0, delay: 1.0, fromY: -8 },
      { x: 18, y: 34, scale: s, rotateZ: 0, delay: 1.0, fromY: -8 },
      { x: 62, y: 34, scale: s, rotateZ: 0, delay: 1.0, fromY: -8 },
      { x: 80, y: 8, scale: s, rotateZ: 0, delay: 1.9, fromY: -6 },
      { x: 80, y: 26, scale: s, rotateZ: 0, delay: 2.05, fromY: -6 },
      { x: 80, y: 44, scale: s, rotateZ: 0, delay: 2.2, fromY: -6 },
      { x: 80, y: 60, scale: s, rotateZ: 0, delay: 2.35, fromY: -6 },
    ];
  }
  return [];
}

function getCinematicTotalMs(spreadId, cardsCount) {
  const specs = getCinematicSpecs(spreadId).slice(0, cardsCount);
  const maxDelay = specs.reduce((m, s) => Math.max(m, s.delay || 0), 0);
  const base = spreadId === 'single' ? CINEMATIC_SINGLE_DURATION_S : CINEMATIC_DEFAULT_DURATION_S;
  return Math.round((maxDelay + base + 0.2) * 1000);
}

/** Верхняя зона контейнера выбора: сюда улетают карты по схеме cinematic (финансы, отношения, крест). */
const FAN_FORMATION_HEIGHT_RATIO = 0.45;

/**
 * Расклад «Финансы»: лесенка по spec.y (14…52). Прямой расчёт + clamp сжимал карты 3–5 к одному верху.
 * Линейно отображаем spec.y на доступный диапазон центров по высоте доски.
 */
function mapFinancialStairYTop(specY, boardH, effectiveH, safeInset) {
  const finSpecs = getCinematicSpecs('financial');
  const ys = finSpecs.map((s) => Number(s.y));
  const minSpecY = Math.min(...ys);
  const maxSpecY = Math.max(...ys);
  const minCenterY = safeInset + effectiveH / 2;
  const maxCenterY = Math.max(minCenterY, boardH - safeInset - effectiveH / 2);
  const t =
    maxSpecY === minSpecY ? 0.5 : (Number(specY) - minSpecY) / (maxSpecY - minSpecY);
  const centerY = minCenterY + t * (maxCenterY - minCenterY);
  return centerY - effectiveH / 2;
}

function getTenCardsRightColumnNudgePx(index) {
  if (index >= 6 && index <= 9) return 0;
  return 0;
}

/** Слоты портала в координатах «доски» (как CinematicSpreadStage), boardW/boardH — размер верхней зоны. */
function getFanFormationSlotPixel(spreadId, order, boardW, boardH) {
  const specs = getCinematicSpecs(spreadId);
  const spec = specs[order] || specs[0];
  const maxCardW =
    spreadId === 'financial' || spreadId === 'six_cards'
      ? Math.min(280, boardW * 0.46)
      : Math.min(220, boardW * 0.34);
  const normalizedAspect = TAROT_ASPECT;
  const heightCap = 0.58;
  const baseCardH = Math.min(maxCardW / normalizedAspect, boardH * heightCap);
  const baseCardW = baseCardH * normalizedAspect;
  const scaleBase = 0.32;
  const finalScale = spec.scale / scaleBase;
  const effectiveW = baseCardW * finalScale;
  const effectiveH = baseCardH * finalScale;
  const safeInsetX = spreadId === 'ten_cards' ? 8 : 6;
  const safeInsetY = spreadId === 'ten_cards' ? -28 : 6;
  const xRaw = (boardW * spec.x) / 100 - effectiveW / 2;
  const x = clamp(xRaw, safeInsetX, Math.max(safeInsetX, boardW - effectiveW - safeInsetX));
  const y =
    spreadId === 'financial'
      ? mapFinancialStairYTop(spec.y, boardH, effectiveH, safeInsetY)
      : clamp(
          (boardH * spec.y) / 100 - effectiveH / 2,
          safeInsetY,
          Math.max(safeInsetY, boardH - effectiveH - safeInsetY)
        );
  const tenCardsNudge = spreadId === 'ten_cards' ? getTenCardsRightColumnNudgePx(order) : 0;
  const yWithNudge = clamp(
    y - tenCardsNudge,
    safeInsetY,
    Math.max(safeInsetY, boardH - effectiveH - safeInsetY)
  );
  return {
    left: x,
    top: yWithNudge,
    width: effectiveW,
    height: effectiveH,
    rotateZ: spec.rotateZ ?? 0,
  };
}

/** Быстрый расклад: дуга колоды с 50% нахлестом, 8 карт на экране, хаотичная левитация. */
const LIFT_DURATION = 1.0;
const FLIP_DURING_LIFT = true;
const DISSOLVE_DURATION = 0.6;

function DeckScrollArrowTrail({ direction = 'right', hidden = false }) {
  const points = direction === 'left' ? '15 18 9 12 15 6' : '9 18 15 12 9 6';
  return (
    <span
      className="flex items-center justify-center gap-[1px]"
      style={{ opacity: hidden ? 0 : 1, transition: 'opacity 220ms ease' }}
      aria-hidden
    >
      <style>
        {`
          @keyframes tarot-scroll-arrow-trail-left {
            0%, 100% { opacity: 0.12; transform: translateX(0) scale(0.9); }
            34% { opacity: 1; transform: translateX(-4px) scale(1.08); }
            68% { opacity: 0.42; transform: translateX(-7px) scale(1); }
          }
          @keyframes tarot-scroll-arrow-trail-right {
            0%, 100% { opacity: 0.12; transform: translateX(0) scale(0.9); }
            34% { opacity: 1; transform: translateX(4px) scale(1.08); }
            68% { opacity: 0.42; transform: translateX(7px) scale(1); }
          }
        `}
      </style>
      {[0, 1, 2].map((idx) => (
        <svg
          key={`${direction}-${idx}`}
          width="11"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#d4a84a"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            animationName: direction === 'left' ? 'tarot-scroll-arrow-trail-left' : 'tarot-scroll-arrow-trail-right',
            animationDuration: '1.35s',
            animationIterationCount: 'infinite',
            animationTimingFunction: 'ease-in-out',
            animationDelay: `${idx * 0.16}s`,
            filter: 'drop-shadow(0 0 6px rgba(212, 168, 74, 0.45))',
          }}
        >
          <path d={`M${points}`} />
        </svg>
      ))}
    </span>
  );
}

const SingleCardArcPicker = React.memo(function SingleCardArcPicker({
  deck = [],
  activeDeck,
  allowReversed,
  onCardSelect,
  triggerHaptics,
  resolveCardImage,
}) {
  const scrollRef = useRef(null);
  const containerRef = useRef(null);
  const slotRef = useRef(null);
  const [liftStartRect, setLiftStartRect] = useState(null);
  const [slotRect, setSlotRect] = useState(null);
  const scrollLockRef = useRef(null);
  const [scrollState, setScrollState] = useState({ scrollLeft: 0, width: 390 });
  const lastHapticRef = useRef(0);
  const [selectedIndex, setSelectedIndex] = useState(null);
  const [liftingCard, setLiftingCard] = useState(null);
  const [pickPhase, setPickPhase] = useState(null); // 'lifting' | 'flipping' | 'dissolving'

  const updateScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const sl = el.scrollLeft;
    const w = el.clientWidth;
    setScrollState((prev) => {
      if (prev.scrollLeft === sl && prev.width === w) return prev;
      return { scrollLeft: sl, width: w };
    });
  }, []);

  const onScrollTouch = useCallback(() => {
    const now = Date.now();
    if (now - lastHapticRef.current < 80) return;
    lastHapticRef.current = now;
    triggerHaptics?.('light');
  }, [triggerHaptics]);

  const rafRef = useRef(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateScroll();
    const onScroll = () => {
      onScrollTouch();
      if (!rafRef.current) rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        updateScroll();
      });
    };
    const ro = new ResizeObserver(updateScroll);
    ro.observe(el);
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      ro.disconnect();
      el.removeEventListener('scroll', onScroll);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [updateScroll, onScrollTouch]);

  const handleCardTap = useCallback(
    async (card, index, event) => {
      if (selectedIndex != null || liftingCard) return;
      triggerHaptics('medium');
      const cardEl = event?.currentTarget;
      if (cardEl && typeof cardEl.getBoundingClientRect === 'function') {
        setLiftStartRect(cardEl.getBoundingClientRect());
      }
      const el = scrollRef.current;
      if (el) scrollLockRef.current = el.scrollLeft;
      setSelectedIndex(index);
      const withReversed = {
        ...card,
        is_reversed: allowReversed ? Math.random() < 0.5 : false,
      };
      const image = await resolveCardImage(withReversed, activeDeck?.id);
      const cardWithImage = { ...withReversed, image: image || card?.image };
      setLiftingCard(cardWithImage);
      setPickPhase('lifting');
    },
    [selectedIndex, liftingCard, allowReversed, activeDeck?.id, resolveCardImage, triggerHaptics]
  );

  const onLiftComplete = useCallback(() => {
    if (FLIP_DURING_LIFT) {
      setPickPhase('landed');
    } else {
      setPickPhase('flipping');
    }
  }, []);

  const onFlipComplete = useCallback(() => {
    setPickPhase('dissolving');
  }, []);

  const onDissolveComplete = useCallback(() => {
    if (liftingCard) {
      onCardSelect(liftingCard);
      setLiftingCard(null);
      setSelectedIndex(null);
      setPickPhase(null);
    }
  }, [liftingCard, onCardSelect]);

  const n = deck.length;
  const [measuredW, setMeasuredW] = useState(390);
  const measuredStableRef = useRef(0);
  useEffect(() => {
    const el = containerRef.current || scrollRef.current;
    if (!el) return;
    const apply = () => {
      const cw = Math.round(el.clientWidth || 390);
      if (Math.abs(measuredStableRef.current - cw) < 2) return;
      measuredStableRef.current = cw;
      setMeasuredW(cw);
    };
    apply();
    const ro = new ResizeObserver(() => requestAnimationFrame(apply));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const containerW = scrollState.width > 0 ? scrollState.width : measuredW;
  const viewportH = typeof window !== 'undefined' ? window.innerHeight : 844;
  const viewportW = typeof window !== 'undefined' ? window.innerWidth : 390;
  const VISIBLE_CARDS = 8;
  const OVERLAP_RATIO = 0.5;
  const rawCardWidth = containerW / (VISIBLE_CARDS * (1 - OVERLAP_RATIO) + OVERLAP_RATIO);
  const cardWidth = Math.round(Math.max(rawCardWidth, containerW / 3.8));
  const cardStep = Math.round(cardWidth * (1 - OVERLAP_RATIO));
  const cardHeight = Math.round(cardWidth / TAROT_ASPECT);
  const sidePadding = 0;
  const totalWidth = Math.max(containerW, sidePadding * 2 + cardWidth + Math.max(0, n - 1) * cardStep);
  // Позиция и размер как в SingleCardResultView (экран результата)
  const resultCardH = 300;
  const targetTop = Math.round(viewportH * 0.20); // 20% от верха экрана, как на экране результата
  const cardH = cardHeight * 1.22;
  const liftEndScale = resultCardH / cardH;
  const selectedCardCenterX = selectedIndex != null
    ? sidePadding + selectedIndex * cardStep + cardWidth / 2 - scrollState.scrollLeft
    : containerW / 2;
  const liftInitialX = selectedCardCenterX - containerW / 2;
  const liftInitialY = Math.max(180, viewportH - targetTop - 260);

  const seededNoise = useCallback((seed) => {
    const raw = Math.sin(seed * 12.9898) * 43758.5453123;
    return raw - Math.floor(raw);
  }, []);

  const singleDeckScrollKeyRef = useRef(null);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el || n === 0) return;
    if (selectedIndex != null) return;
    const target = Math.max(0, (totalWidth - containerW) / 2);
    const key = `${n}-${Math.round(totalWidth)}`;
    if (singleDeckScrollKeyRef.current !== key) {
      singleDeckScrollKeyRef.current = key;
      el.scrollLeft = target;
    }
  }, [n, totalWidth, containerW, selectedIndex]);

  useEffect(() => {
    if (selectedIndex == null) return;
    const el = scrollRef.current;
    const locked = scrollLockRef.current;
    if (el != null && typeof locked === 'number') {
      el.scrollLeft = locked;
    }
  }, [selectedIndex]);

  useLayoutEffect(() => {
    if (selectedIndex == null) {
      setLiftStartRect(null);
      setSlotRect(null);
      return;
    }
    if (slotRef.current) {
      setSlotRect(slotRef.current.getBoundingClientRect());
    }
  }, [selectedIndex]);

  const isLifting = pickPhase === 'lifting' && liftingCard && selectedIndex != null;
  const isFlipping = pickPhase === 'flipping' && liftingCard && selectedIndex != null;
  const isLanded = pickPhase === 'landed' && liftingCard && selectedIndex != null;
  const isDissolving = pickPhase === 'dissolving';
  const selectedCardLifted = (isLifting || isFlipping || isLanded || isDissolving) && selectedIndex != null;

  useEffect(() => {
    if (pickPhase === 'landed') {
      const t = setTimeout(onDissolveComplete, 400);
      return () => clearTimeout(t);
    }
    if (pickPhase !== 'dissolving') return;
    const t = setTimeout(onDissolveComplete, DISSOLVE_DURATION * 1000);
    return () => clearTimeout(t);
  }, [pickPhase, onDissolveComplete]);

  useEffect(() => {
    if (pickPhase !== 'flipping') return;
    const t = setTimeout(onFlipComplete, FLIP_DURATION * 1000);
    return () => clearTimeout(t);
  }, [pickPhase, onFlipComplete]);

  const isFaceShown = pickPhase === 'flipping' || pickPhase === 'landed' || pickPhase === 'dissolving';
  const smoothEase = [0.33, 0, 0.2, 1];
  const startX = liftStartRect
    ? liftStartRect.left + liftStartRect.width / 2 - viewportW / 2
    : liftInitialX;
  const startY = liftStartRect
    ? liftStartRect.top + liftStartRect.height / 2 - (targetTop + cardH / 2)
    : liftInitialY;
  const scaledH = cardH * liftEndScale;
  const endX = 0;
  const endY = 0;

  const liftOverlay = selectedCardLifted && liftingCard && typeof document !== 'undefined' && createPortal(
    <motion.div
      className="fixed inset-0 z-[200] pointer-events-none flex items-start justify-center"
      style={{
        paddingTop: `${targetTop}px`,
        perspective: 1200,
        WebkitPerspective: 1200,
      }}
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
    >
      <motion.div
        className="relative rounded-[12px] overflow-visible shadow-2xl"
        style={{
          width: cardWidth * 1.22,
          height: cardHeight * 1.22,
          transformStyle: 'preserve-3d',
          WebkitTransformStyle: 'preserve-3d',
          willChange: 'transform',
        }}
        initial={{ x: startX, y: startY, scale: 0.94, rotateZ: -6 }}
        animate={{
          x: endX,
          y: endY,
          scale: liftEndScale,
          rotateZ: 0,
          opacity: 1,
          transition: pickPhase === 'lifting'
            ? { duration: LIFT_DURATION, ease: smoothEase }
            : { duration: 0 },
        }}
        onAnimationComplete={() => pickPhase === 'lifting' && onLiftComplete()}
      >
        <div className="absolute inset-0 rounded-[12px] overflow-hidden">
          <motion.div
            className="absolute inset-0 flex items-center justify-center rounded-[12px] overflow-hidden bg-amber-950/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: (isFaceShown || (FLIP_DURING_LIFT && pickPhase === 'lifting')) ? 1 : 0 }}
            transition={
              FLIP_DURING_LIFT && pickPhase === 'lifting'
                ? { duration: LIFT_DURATION * 0.5, delay: LIFT_DURATION * 0.15, ease: smoothEase }
                : isFaceShown
                  ? { duration: 0.3 }
                  : { duration: 0 }
            }
            style={{ pointerEvents: 'none' }}
          >
            {liftingCard?.image ? (
              <img
                src={liftingCard.image}
                alt=""
                className="h-full w-full object-cover rounded-[10px]"
                style={{ transform: liftingCard?.is_reversed ? 'rotate(180deg)' : undefined }}
              />
            ) : (
              <div className="w-full h-full bg-amber-900/30 rounded-[10px]" />
            )}
          </motion.div>
          <motion.div
            className="absolute inset-0 flex items-center justify-center rounded-[12px] overflow-hidden bg-amber-950/40"
            initial={{ opacity: 1 }}
            animate={{ opacity: (isFaceShown || (FLIP_DURING_LIFT && pickPhase === 'lifting')) ? 0 : 1 }}
            transition={
              FLIP_DURING_LIFT && pickPhase === 'lifting'
                ? { duration: LIFT_DURATION * 0.4, delay: LIFT_DURATION * 0.1, ease: smoothEase }
                : isFaceShown
                  ? { duration: 0.2 }
                  : { duration: 0 }
            }
            style={{ pointerEvents: 'none' }}
          >
            {activeDeck?.backImage ? (
              <img src={activeDeck.backImage} alt="" className="h-full w-full object-cover rounded-[10px]" />
            ) : (
              <div className="w-full h-full bg-amber-900/30 rounded-[10px]" />
            )}
          </motion.div>
        </div>
      </motion.div>
    </motion.div>,
    document.body
  );

  const scrollByStep = useCallback((direction) => {
    const el = scrollRef.current;
    if (!el) return;
    const step = Math.round(containerW * 0.35);
    el.scrollBy({ left: direction * step, behavior: 'smooth' });
    triggerHaptics('light');
  }, [containerW, triggerHaptics]);

  return (
    <div className="relative w-full flex flex-col items-center flex-1 min-h-0 overflow-visible">
      {liftOverlay}
      <div className="flex-1 min-h-0 shrink" style={{ minHeight: 0 }} />
      <div ref={containerRef} className="relative w-full shrink-0 flex flex-col items-center px-0 max-w-full">
        {/* 1. Слот с текстом призыва */}
        <motion.div
          ref={slotRef}
          className="w-full shrink-0 flex flex-col items-center justify-center py-4 px-4 mb-1"
          animate={{ opacity: isDissolving ? 0 : 1 }}
          transition={{ duration: DISSOLVE_DURATION * 0.5 }}
          style={{ minHeight: 100 }}
        >
          <p
            className="w-full text-center leading-snug max-w-[280px] font-medium"
            style={{
              fontFamily: "'Cormorant Garamond', serif",
              fontSize: '24px',
              color: '#f6e08a',
              filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.35))',
            }}
          >
            Узнай ответ на свой вопрос.<br />Мысленно задай его и вытяни карту.
          </p>
        </motion.div>
        {/* Колода (прямая линия); подпись «Прокрути колоду» со стрелками снизу */}
        <div
          ref={scrollRef}
          className={cn('flex overscroll-x-contain scrollbar-hide w-full shrink-0', !selectedCardLifted && 'touch-manipulation overflow-x-auto')}
          onTouchStart={onScrollTouch}
          onTouchMove={onScrollTouch}
          style={{
            paddingLeft: 0,
            paddingRight: 0,
            paddingBottom: 8,
            paddingTop: 4,
            marginTop: 0,
            WebkitOverflowScrolling: 'touch',
            scrollSnapType: 'none',
            overflowY: selectedCardLifted ? 'visible' : 'hidden',
            overflowX: selectedCardLifted ? 'hidden' : 'auto',
            scrollBehavior: 'auto',
          }}
        >
        <div
          className="flex items-end justify-start"
          style={{
            minWidth: totalWidth,
            width: totalWidth,
            height: cardHeight + 60 + TAROT_PICK_DECK_ROW_OFFSET_Y,
            transform: `translate3d(0, ${TAROT_PICK_DECK_ROW_OFFSET_Y}px, 0)`,
            backfaceVisibility: 'hidden',
          }}
        >
          {deck.map((card, index) => {
            const levitateY = 2 + seededNoise(index + 41) * 4;
            const levitateRotate = (seededNoise(index + 13) - 0.5) * 4;
            const levitationDelay = seededNoise(index + 57) * 1.5;
            const levitationDuration = 2.2 + seededNoise(index + 73) * 1.0;
            const staticYOffset = (seededNoise(index + 101) - 0.5) * 12;
            const thisCardLifting = liftingCard && selectedIndex === index;

            return thisCardLifting ? (
              <div
                key={`${card?.id || ''}-${index}`}
                className="relative shrink-0 touch-manipulation cursor-pointer"
                style={{
                  width: cardWidth,
                  height: cardHeight + 40,
                  marginRight: index < n - 1 ? -(cardWidth - cardStep) : 0,
                  paddingBottom: 8,
                  opacity: 0,
                  visibility: 'hidden',
                }}
                onClick={(e) => !selectedCardLifted && handleCardTap(card, index, e)}
              >
                <div
                  className="relative w-full h-full rounded-[12px] overflow-hidden"
                  style={{
                    width: cardWidth,
                    height: cardHeight,
                    boxShadow: '0 12px 22px rgba(0,0,0,0.22)',
                  }}
                >
                  {card?.backImage ? (
                    <img src={card.backImage} alt="" className="h-full w-full object-cover rounded-[10px]" />
                  ) : (
                    <div className="w-full h-full bg-amber-900/30 rounded-[8px]" />
                  )}
                </div>
              </div>
            ) : (
              <motion.div
                key={`${card?.id || ''}-${index}`}
                className="relative shrink-0 touch-manipulation cursor-pointer"
                style={{
                  width: cardWidth,
                  height: cardHeight + 40,
                  marginRight: index < n - 1 ? -(cardWidth - cardStep) : 0,
                  paddingBottom: 8,
                  zIndex: index,
                  opacity: isDissolving ? 0 : 1,
                  transition: isDissolving ? `opacity ${DISSOLVE_DURATION}s` : 'none',
                }}
                onClick={(e) => !selectedCardLifted && handleCardTap(card, index, e)}
                animate={{
                  y: [staticYOffset, staticYOffset - Math.min(levitateY, 3.2), staticYOffset],
                  rotate: levitateRotate,
                }}
                transition={{
                  y: {
                    duration: Math.min(levitationDuration + 2.2, 7.5),
                    delay: levitationDelay,
                    repeat: Infinity,
                    repeatType: 'reverse',
                    ease: 'easeInOut',
                  },
                  rotate: { duration: 0 },
                }}
              >
                <div
                  className="relative w-full h-full rounded-[12px] overflow-hidden"
                  style={{
                    width: cardWidth,
                    height: cardHeight,
                    boxShadow: '0 12px 22px rgba(0,0,0,0.22)',
                  }}
                >
                  <div className="absolute inset-0 flex items-center justify-center rounded-[12px] overflow-hidden bg-amber-950/40 border border-white/10">
                    {card?.backImage ? (
                      <img
                        src={card.backImage}
                        alt=""
                        className="h-full w-full object-cover rounded-[12px]"
                      />
                    ) : (
                      <div className="w-full h-full rounded-[12px]" style={{ background: 'radial-gradient(circle at 50% 18%, rgba(251,191,36,0.3), transparent 46%), linear-gradient(180deg, rgba(15,12,35,0.98) 0%, rgba(6,5,18,0.99) 100%)' }} />
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
        </div>
        {!selectedCardLifted && (
          <div
            className="flex w-full max-w-md mx-auto items-center justify-center gap-2 sm:gap-3 mt-4 px-3"
            style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom, 0px) + 0.5rem)' }}
          >
            <button type="button" onClick={() => scrollByStep(-1)} className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0" aria-label="Прокрутить колоду влево">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#d4a84a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
            <p
              className="flex-1 text-center text-[10px] uppercase tracking-[0.18em] text-amber-300/90 min-w-0 leading-tight px-1"
              style={{ fontFamily: "'Cormorant Garamond', serif" }}
            >
              Прокрути колоду
            </p>
            <button type="button" onClick={() => scrollByStep(1)} className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0" aria-label="Прокрутить колоду вправо">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#d4a84a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18l6-6-6-6" /></svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

const CinematicSpreadStage = React.memo(function CinematicSpreadStage({
  spreadId,
  cards = [],
  currentPositions = [],
}) {
  const containerRef = useRef(null);
  const [layout, setLayout] = useState({ w: 360, h: 560 });
  const [cardAspect, setCardAspect] = useState(TAROT_ASPECT);
  const [labelsVisible, setLabelsVisible] = useState(false);
  const [landedCardIndexes, setLandedCardIndexes] = useState(() => new Set());
  const [revealedCardIndexes, setRevealedCardIndexes] = useState(() => new Set());
  const [tenColumnGlow, setTenColumnGlow] = useState(false);
  const [tenCrossGlow, setTenCrossGlow] = useState(false);
  const [relationHeartPulse, setRelationHeartPulse] = useState(false);
  const financialAudioPlayedRef = useRef(new Set());
  const specs = getCinematicSpecs(spreadId).slice(0, cards.length);
  const maxCardW =
    spreadId === 'financial' || spreadId === 'six_cards'
      ? Math.min(280, layout.w * 0.46)
      : Math.min(220, layout.w * 0.34);
  const normalizedAspect = clamp(cardAspect, 0.5, 0.72);
  const desiredCardH = maxCardW / normalizedAspect;
  const heightCap = 0.58;
  const baseCardH = Math.min(desiredCardH, layout.h * heightCap);
  const baseCardW = baseCardH * normalizedAspect;
  const scaleBase = 0.32;
  const ease = TAROT_ANIM.SMOOTH_EASE;
  const maxDealDelay = useMemo(
    () => specs.reduce((m, s) => Math.max(m, s?.delay || 0), 0),
    [specs]
  );
  const isLevitateSpread = spreadId === 'ten_cards' || spreadId === 'financial' || spreadId === 'six_cards';
  const cardsRunKey = useMemo(
    () => cards.map((c, idx) => `${c?.id || idx}:${c?.image || ''}:${c?.is_reversed ? 1 : 0}`).join('|'),
    [cards]
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) setLayout({ w: rect.width, h: rect.height });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const probeSrc = cards.find((c) => c?.backImage)?.backImage || cards.find((c) => c?.image)?.image || '';
    if (!probeSrc || typeof Image === 'undefined') return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      if (img.naturalWidth > 0 && img.naturalHeight > 0) {
        setCardAspect(img.naturalWidth / img.naturalHeight);
      }
    };
    img.src = probeSrc;
    return () => {
      cancelled = true;
    };
  }, [cards]);

  useEffect(() => {
    setLabelsVisible(false);
    if (spreadId !== 'three_cards' || cards.length < 3) return;
    const t = setTimeout(() => setLabelsVisible(true), 1300);
    return () => clearTimeout(t);
  }, [spreadId, cardsRunKey, cards.length]);

  useEffect(() => {
    setLandedCardIndexes(new Set());
    setRevealedCardIndexes(new Set());
    setTenColumnGlow(false);
    setTenCrossGlow(false);
    setRelationHeartPulse(false);
    financialAudioPlayedRef.current = new Set();
    if (!cards.length) return undefined;

    const localSpecs = getCinematicSpecs(spreadId).slice(0, cards.length);
    const duration = spreadId === 'single' ? CINEMATIC_SINGLE_DURATION_S : CINEMATIC_DEFAULT_DURATION_S;
    const timers = localSpecs.map((spec, idx) => {
      const ms = Math.round(((spec.delay || 0) + duration) * 1000);
      return setTimeout(() => {
        setLandedCardIndexes((prev) => {
          if (prev.has(idx)) return prev;
          const next = new Set(prev);
          next.add(idx);
          return next;
        });
      }, ms);
    });
    const maxDealDelay = localSpecs.reduce((m, s) => Math.max(m, s?.delay || 0), 0);
    const flipDuration = Math.max(0.82, duration - 0.08);
    localSpecs.forEach((_, idx) => {
      const flipDelay = maxDealDelay + duration + 0.08 + idx * 0.14;
      const revealAtMs = Math.round((flipDelay + flipDuration * 0.5) * 1000);
      timers.push(setTimeout(() => {
        setRevealedCardIndexes((prev) => {
          if (prev.has(idx)) return prev;
          const next = new Set(prev);
          next.add(idx);
          return next;
        });
      }, revealAtMs));
    });

    if (spreadId === 'ten_cards' && cards.length >= 10) {
      const lastDelay = localSpecs[9]?.delay || 0;
      const columnGlowAt = Math.round((lastDelay + duration + 80) * 1000);
      const crossGlowAt = Math.round((lastDelay + duration + 420) * 1000);
      timers.push(setTimeout(() => setTenColumnGlow(true), columnGlowAt));
      timers.push(setTimeout(() => setTenCrossGlow(true), crossGlowAt));
    }
    if (spreadId === 'six_cards' && cards.length >= 6) {
      const lastDelay = localSpecs[5]?.delay || 0;
      const heartAt = Math.round((lastDelay + duration + 120) * 1000);
      timers.push(setTimeout(() => setRelationHeartPulse(true), heartAt));
    }

    return () => timers.forEach(clearTimeout);
  }, [spreadId, cardsRunKey, cards.length]);

  useEffect(() => {
    if (spreadId !== 'financial') return;
    landedCardIndexes.forEach((idx) => {
      if (financialAudioPlayedRef.current.has(idx)) return;
      financialAudioPlayedRef.current.add(idx);
      playGoldSparkSound();
    });
  }, [spreadId, landedCardIndexes]);

  return (
    <div ref={containerRef} className="relative w-full flex-1 min-h-[62vh] overflow-visible">
      {cards.map((card, idx) => {
        const spec = specs[idx] || { x: 50, y: 50, scale: 0.3, rotateZ: 0, delay: idx * 0.16, fromY: -8 };
        const finalScale = spec.scale / scaleBase;
        const safeInsetX = spreadId === 'ten_cards' ? 8 : 6;
        const safeInsetY = spreadId === 'ten_cards' ? -28 : 6;
        const y =
          spreadId === 'financial'
            ? mapFinancialStairYTop(spec.y, layout.h, baseCardH, safeInsetY)
            : clamp(
                (layout.h * spec.y) / 100 - baseCardH / 2,
                safeInsetY,
                Math.max(safeInsetY, layout.h - baseCardH - safeInsetY)
              );
        const tenCardsNudge = spreadId === 'ten_cards' ? getTenCardsRightColumnNudgePx(idx) : 0;
        const yShifted = clamp(
          y - tenCardsNudge,
          safeInsetY,
          Math.max(safeInsetY, layout.h - baseCardH - safeInsetY)
        );
        let x;
        if (spreadId === 'financial') {
          const halfVisW = (baseCardW * finalScale) / 2;
          const cx = clamp(
            (layout.w * spec.x) / 100,
            safeInsetX + halfVisW,
            layout.w - safeInsetX - halfVisW
          );
          x = cx - baseCardW / 2;
        } else {
          const xRaw = (layout.w * spec.x) / 100 - baseCardW / 2;
          x = clamp(xRaw, safeInsetX, Math.max(safeInsetX, layout.w - baseCardW - safeInsetX));
        }
        const duration = spreadId === 'single'
          ? CINEMATIC_SINGLE_DURATION_S
          : spreadId === 'three_cards'
            ? 1.28
            : CINEMATIC_DEFAULT_DURATION_S;
        const initialY = yShifted + (layout.h * spec.fromY) / 100;
        const initialX = -baseCardW - 20 - idx * 10;
        const isReversed = Boolean(card?.is_reversed);
        const flipDelay = maxDealDelay + duration + 0.08 + idx * 0.14;
        const isFaceRevealed = revealedCardIndexes.has(idx);
        const useSafeCrossfadeFlip = spreadId === 'six_cards';
        const shouldLevitate = isLevitateSpread && landedCardIndexes.has(idx);
        const levitationPx = 3 + (idx % 2) * 0.8;
        return (
          <motion.div
            key={`${card?.id || idx}-${idx}`}
            className="absolute overflow-hidden rounded-[12px]"
            style={{
              left: 0,
              top: 0,
              width: baseCardW,
              height: baseCardH,
              transformOrigin: 'center center',
              perspective: 1200,
              WebkitPerspective: 1200,
              zIndex: 20 + idx,
              borderRadius: 12,
            }}
            initial={{ opacity: 0, x: initialX, y: initialY, scale: finalScale + 0.65, rotateZ: spec.rotateZ - 4, filter: 'blur(2px)' }}
            animate={{ opacity: 1, x, y: yShifted, scale: finalScale, rotateZ: spec.rotateZ, filter: 'blur(0px)' }}
            transition={{ duration, delay: spec.delay || 0, ease }}
          >
            <motion.div
              className="relative w-full h-full overflow-hidden rounded-[12px]"
              style={{ borderRadius: 12 }}
              animate={
                shouldLevitate
                  ? { y: [0, -levitationPx] }
                  : { y: -(2.2 + (idx % 2) * 0.8) }
              }
              transition={
                shouldLevitate
                  ? {
                      duration: 2.6 + idx * 0.12,
                      delay: (spec.delay || 0) + duration + 0.06,
                      repeat: Infinity,
                      repeatType: 'mirror',
                      ease: 'easeInOut',
                    }
                  : {
                      duration: 0.42,
                      delay: (spec.delay || 0) + duration + 0.06,
                      ease: [0.22, 1, 0.36, 1],
                    }
              }
            >
              <motion.div
                className="relative w-full h-full overflow-hidden rounded-[12px]"
                style={{
                  borderRadius: 12,
                  isolation: 'isolate',
                  willChange: 'transform',
                  transformStyle: 'preserve-3d',
                  WebkitTransformStyle: 'preserve-3d',
                }}
                initial={{ rotateY: 0, rotateX: 0 }}
                animate={{
                  rotateY: useSafeCrossfadeFlip ? 0 : (isFaceRevealed ? 180 : 0),
                  rotateX: useSafeCrossfadeFlip ? 0 : (isFaceRevealed ? [0, 4, 0] : 0),
                }}
                transition={{
                  rotateY: {
                    duration: Math.max(0.72, duration - 0.08),
                    delay: flipDelay,
                    ease: [0.22, 1, 0.36, 1],
                  },
                  rotateX: {
                    duration: Math.max(0.72, duration - 0.08),
                    delay: flipDelay,
                    ease: [0.22, 1, 0.36, 1],
                  },
                }}
              >
                {/* Рубашка: при 0° смотрит на зрителя, при 180° скрыта через backface */}
                <div
                  className="absolute inset-0 overflow-hidden rounded-[12px] tarot-back-wrap flex items-center justify-center"
                  style={{
                    backfaceVisibility: useSafeCrossfadeFlip ? 'visible' : 'hidden',
                    WebkitBackfaceVisibility: useSafeCrossfadeFlip ? 'visible' : 'hidden',
                    transform: useSafeCrossfadeFlip ? 'none' : 'rotateY(0deg) translateZ(-1px)',
                    opacity: useSafeCrossfadeFlip ? (isFaceRevealed ? 0 : 1) : 1,
                    transition: useSafeCrossfadeFlip ? 'opacity 320ms ease' : undefined,
                    zIndex: 0,
                  }}
                >
                  {card?.backImage ? (
                    <img src={card.backImage} alt="" className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]" />
                  ) : (
                    <div className="w-full h-full bg-amber-900/20 rounded-[12px]" />
                  )}
                </div>
                {/* Лицо: при 180° должно быть к зрителю; -180deg в локальных координатах даёт правильную сторону в WebKit */}
                <div
                  className="absolute inset-0 overflow-hidden rounded-[12px] flex items-center justify-center"
                  style={{
                    backfaceVisibility: useSafeCrossfadeFlip ? 'visible' : 'hidden',
                    WebkitBackfaceVisibility: useSafeCrossfadeFlip ? 'visible' : 'hidden',
                    transform: useSafeCrossfadeFlip ? 'none' : 'rotateY(-180deg) translateZ(1px)',
                    opacity: useSafeCrossfadeFlip ? (isFaceRevealed ? 1 : 0) : 1,
                    transition: useSafeCrossfadeFlip ? 'opacity 320ms ease' : undefined,
                    zIndex: 1,
                  }}
                >
                  {card?.image ? (
                    <img
                      src={card.image}
                      alt=""
                      className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]"
                      style={{ transform: isReversed ? 'rotate(180deg)' : undefined }}
                    />
                  ) : (
                    <div className="w-full h-full bg-amber-900/30 rounded-[12px]" />
                  )}
                </div>
              </motion.div>
              {/* Страховочный слой: после флипа показываем лицо поверх (обход бага backface и crossfade в Safari/WebKit) */}
              <AnimatePresence>
                {isFaceRevealed && (!useSafeCrossfadeFlip || spreadId === 'six_cards') ? (
                  <motion.div
                    key={`face-overlay-${idx}`}
                    className="absolute inset-0 overflow-hidden rounded-[12px] flex items-center justify-center pointer-events-none"
                    style={{
                      zIndex: 30,
                      boxShadow: '0 4px 24px rgba(0,0,0,0.25)',
                      borderRadius: 12,
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: useSafeCrossfadeFlip ? 0.28 : 0.2 }}
                  >
                    {card?.image ? (
                      <img
                        src={card.image}
                        alt=""
                        className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]"
                        style={{ transform: isReversed ? 'rotate(180deg)' : undefined, borderRadius: 12 }}
                      />
                    ) : (
                      <div className="w-full h-full bg-amber-900/30 rounded-[12px]" />
                    )}
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </motion.div>
          </motion.div>
        );
      })}

      {spreadId === 'three_cards' && cards.length >= 3 ? (
        <AnimatePresence>
          {labelsVisible ? (
            <motion.div
              className="absolute inset-0 pointer-events-none flex flex-col items-center"
              style={{ paddingTop: '36%', gap: 12 }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.32, ease }}
            >
              {cards.slice(0, 3).map((_, idx) => (
                <motion.p
                  key={`label-${idx}`}
                  className="text-amber-200/95 text-[12px] font-semibold tracking-[0.08em] uppercase text-center w-full"
                  style={{ whiteSpace: 'nowrap' }}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: idx * 0.1, ease }}
                >
                  {String(currentPositions[idx] || ['Прошлое', 'Настоящее', 'Будущее'][idx]).toUpperCase()}
                </motion.p>
              ))}
            </motion.div>
          ) : null}
        </AnimatePresence>
      ) : null}

      {spreadId === 'six_cards' && relationHeartPulse ? (
        <motion.div
          className="pointer-events-none absolute inset-0 z-[40] flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.85, 0.45] }}
          transition={{ duration: 1.2, ease: 'easeOut' }}
        >
          <motion.span
            className="text-pink-300 text-5xl"
            animate={{ scale: [0.8, 1.12, 0.95, 1.05], opacity: [0.5, 1, 0.75, 0.9] }}
            transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
          >
            ❤
          </motion.span>
        </motion.div>
      ) : null}

      {spreadId === 'ten_cards' && tenColumnGlow ? (
        <motion.div
          className="pointer-events-none absolute z-[45]"
          style={{
            left: '72%',
            top: '28%',
            width: '14%',
            height: '44%',
            borderRadius: '1rem',
            background: 'radial-gradient(ellipse at center, rgba(251,191,36,0.35) 0%, rgba(251,191,36,0.12) 55%, rgba(251,191,36,0) 75%)',
            filter: 'blur(4px)',
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.9, 0.45] }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
        />
      ) : null}

      {spreadId === 'ten_cards' && tenCrossGlow ? (
        <motion.div
          className="pointer-events-none absolute inset-0 z-[44]"
          style={{
            background: 'radial-gradient(ellipse 80% 72% at 52% 48%, rgba(251,191,36,0.28) 0%, rgba(251,191,36,0.12) 42%, rgba(251,191,36,0) 72%)',
            filter: 'blur(6px)',
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.95, 0.3] }}
          transition={{ duration: 1.05, ease: [0.22, 1, 0.36, 1] }}
        />
      ) : null}
    </div>
  );
});

function CardFaceWithFallback({ card, isReversed, useResultLikeFit = false }) {
  const [loadedSrc, setLoadedSrc] = useState(card?.image || '');
  const loadingRef = useRef(false);
  useEffect(() => {
    if (loadedSrc || !card?.imageLoader || loadingRef.current) return;
    loadingRef.current = true;
    card.imageLoader().then((url) => {
      if (url) setLoadedSrc(url);
    }).finally(() => { loadingRef.current = false; });
  }, [card?.imageLoader, loadedSrc]);
  const src = card?.image || loadedSrc;
  const radiusClass = useResultLikeFit ? 'rounded-[12px]' : 'rounded-[14px]';
  const fitClass = useResultLikeFit ? 'object-contain' : 'object-cover';
  if (src) {
    return (
      <img
        src={src}
        alt=""
        className={`h-full w-full ${fitClass} ${radiusClass}`}
        loading="eager"
        style={{ transform: isReversed ? 'rotate(180deg)' : undefined }}
      />
    );
  }
  return (
    <div className={`absolute inset-0 ${radiusClass}`} style={{ background: 'linear-gradient(180deg, rgba(46,32,14,0.92) 0%, rgba(15,10,6,0.98) 100%)' }} />
  );
}

const FAN_DECK_FORMATION_SPREAD_IDS = new Set(['financial', 'six_cards', 'ten_cards']);

/** Вибрация при прокрутке колоды: в Telegram часто заметнее связка selection + impact; плюс vibrate в браузере. */
function fireDeckScrollHaptic() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;
  try {
    tg?.HapticFeedback?.selectionChanged?.();
  } catch {
    /* ignore */
  }
  try {
    tg?.HapticFeedback?.impactOccurred?.('light');
  } catch {
    /* ignore */
  }
  if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
    try {
      navigator.vibrate(12);
    } catch {
      /* ignore */
    }
  }
}

function FanDeckPick({
  shuffledDeckForPick,
  selectedSpread,
  spreadHint,
  handleCardSelect,
  pickedIndices,
  pickedCards = [],
  justAppeared,
  freezeDeck,
  subPhase,
  triggerHaptics,
  spreadId = 'three_cards',
  singlePortalCardRef = null,
  /** Портал с вылетевшей картой в body не inherits opacity родителя: скрываем при переходе к экрану результата. */
  hideLiftedCardsPortal = false,
}) {
  const pickable = shuffledDeckForPick;
  const n = pickable.length;
  const containerRef = useRef(null);
  const scrollRef = useRef(null);
  const rafRef = useRef(null);
  const lastHapticRef = useRef(0);
  /** Не давать вибро от scroll-событий при программном scrollLeft (центрирование колоды). */
  const skipScrollHapticRef = useRef(false);
  const skipScrollHapticTimerRef = useRef(null);
  const deckTouchActiveRef = useRef(false);
  const lastScrollLeftForHapticRef = useRef(0);
  const deckHapticLoopRafRef = useRef(null);
  const initialViewportLayout = useMemo(
    () => ({
      w:
        typeof window !== 'undefined' && Number.isFinite(window.innerWidth)
          ? Math.max(320, Math.round(window.innerWidth))
          : 320,
      h:
        typeof window !== 'undefined' && Number.isFinite(window.innerHeight)
          ? Math.max(480, Math.round(window.innerHeight))
          : 480,
    }),
    []
  );
  const [layout, setLayout] = useState(initialViewportLayout);
  const [scrollState, setScrollState] = useState({
    left: 0,
    width: initialViewportLayout.w,
  });
  /** Мгновенно скрываем уже нажатую карту, чтобы не было flash-back кадра до синхронизации pickedIndices. */
  const [instantHiddenIndices, setInstantHiddenIndices] = useState(() => new Set());
  /** Карта дня: фиксируем старт тапа, чтобы колода/заголовок не моргали между кадрами. */
  const [singleTapStarted, setSingleTapStarted] = useState(false);
  /** Вылет карты из точки тапа (viewport), по порядку выбора */
  const flightOriginByOrderRef = useRef({});
  const pickedOrder = [...pickedIndices];

  useEffect(() => {
    if (pickedOrder.length === 0) flightOriginByOrderRef.current = {};
  }, [pickedOrder.length]);
  useEffect(() => {
    if (subPhase !== 'picking' || pickedOrder.length !== 0) return;
    // Не сбрасывать мгновенное скрытие/флаг тапа в тот же тик: иначе слой колоды может моргнуть.
    if (singleTapStarted) return;
    if (instantHiddenIndices.size > 0) setInstantHiddenIndices(new Set());
  }, [subPhase, pickedOrder.length, instantHiddenIndices.size, singleTapStarted]);

  useEffect(() => {
    if (subPhase !== 'picking' || pickedOrder.length !== 0) return;
    if (instantHiddenIndices.size !== 0) return;
    if (singleTapStarted) setSingleTapStarted(false);
  }, [subPhase, pickedOrder.length, instantHiddenIndices.size, singleTapStarted]);
  const pickedMap = new Map(pickedOrder.map((idx, order) => [idx, order]));
  const useFormationLayout = FAN_DECK_FORMATION_SPREAD_IDS.has(spreadId);
  const isTenCardsSpread = spreadId === 'ten_cards';
  const freezeDeckRef = useRef(freezeDeck);
  const subPhaseRef = useRef(subPhase);
  freezeDeckRef.current = freezeDeck;
  subPhaseRef.current = subPhase;

  /** После первого тапа не пересчитывать layout: смена шапки и фазы flipping меняет высоту flex-зоны и «дёргает» колоду. Ref обновляется каждый рендер, чтобы ResizeObserver ([] deps) не получал устаревший pickedOrder. */
  const deckPickCountRef = useRef(0);
  deckPickCountRef.current = pickedOrder.length;

  const layoutStableRef = useRef({ w: 0, h: 0 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      if (deckPickCountRef.current > 0) return;
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const nw = Math.round(rect.width);
      const nh = Math.round(rect.height);
      const prev = layoutStableRef.current;
      if (Math.abs(prev.w - nw) < 2 && Math.abs(prev.h - nh) < 6) return;
      layoutStableRef.current = { w: nw, h: nh };
      setLayout({ w: nw, h: nh });
    };
    update();
    const ro = new ResizeObserver(() => requestAnimationFrame(update));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || n <= 1) return;
    const updateScroll = () => {
      const left = el.scrollLeft;
      const width = el.clientWidth;
      setScrollState((prev) => {
        if (prev.left === left && prev.width === width) return prev;
        return { left, width };
      });
    };
    const onScroll = () => {
      if (!skipScrollHapticRef.current) {
        const now = Date.now();
        if (now - lastHapticRef.current > 72) {
          lastHapticRef.current = now;
          fireDeckScrollHaptic();
        }
      }
      updateScroll();
    };
    updateScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', onScroll);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (skipScrollHapticTimerRef.current) {
        window.clearTimeout(skipScrollHapticTimerRef.current);
        skipScrollHapticTimerRef.current = null;
      }
    };
  }, [n]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || n <= 1) return;
    const onTouchMoveCapture = () => {
      if (freezeDeckRef.current || subPhaseRef.current !== 'picking') return;
      if (skipScrollHapticRef.current) return;
      deckTouchActiveRef.current = true;
      const now = Date.now();
      if (now - lastHapticRef.current <= 52) return;
      lastHapticRef.current = now;
      fireDeckScrollHaptic();
    };
    el.addEventListener('touchmove', onTouchMoveCapture, { passive: true, capture: true });
    return () => {
      el.removeEventListener('touchmove', onTouchMoveCapture, { capture: true });
    };
  }, [n]);

  const CARD_W = Math.round(clamp(layout.w / 4.55, 62, 88));
  const CARD_H = Math.round(CARD_W / TAROT_ASPECT);
  const STEP_X = Math.round(CARD_W * 0.58);
  const edgePad = 56;
  const deckContentWidth = CARD_W + Math.max(0, n - 1) * STEP_X + CARD_W;
  const totalWidth = Math.max(layout.w, deckContentWidth) + 2 * edgePad;
  /** Колода под дугой; для кельтского креста чуть выше, чтобы схема не прижималась к низу */
  const deckTopBase = Math.round(
    clamp(layout.h * 0.44, CARD_H * 0.55 + 8, layout.h * 0.58) +
      (spreadId === 'financial' || spreadId === 'six_cards' || spreadId === 'ten_cards' ? 14 : 0)
  );
  const selectionY = Math.max(34, layout.h * 0.08);

  const deckScrollKeyRef = useRef(null);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // После выбора карты не трогаем scrollLeft: иначе колода «прыгает» к центру при смене шапки/вёрстки.
    if (pickedOrder.length > 0) {
      const left = el.scrollLeft;
      const width = el.clientWidth;
      setScrollState((prev) => {
        if (prev.left === left && prev.width === width) return prev;
        return { left, width };
      });
      return;
    }
    const target = Math.max(0, (totalWidth - el.clientWidth) / 2);
    const key = `${n}-${Math.round(totalWidth)}`;
    if (deckScrollKeyRef.current !== key) {
      deckScrollKeyRef.current = key;
      skipScrollHapticRef.current = true;
      if (skipScrollHapticTimerRef.current) window.clearTimeout(skipScrollHapticTimerRef.current);
      el.scrollLeft = target;
      skipScrollHapticTimerRef.current = window.setTimeout(() => {
        skipScrollHapticRef.current = false;
        skipScrollHapticTimerRef.current = null;
      }, 280);
    }
    const left = el.scrollLeft;
    const width = el.clientWidth;
    setScrollState((prev) => {
      if (prev.left === left && prev.width === width) return prev;
      return { left, width };
    });
  }, [n, totalWidth, pickedOrder.length]);

  const scrollDeckByStep = useCallback(
    (direction) => {
      const el = scrollRef.current;
      if (!el) return;
      const w = scrollState.width > 0 ? scrollState.width : layout.w;
      const step = Math.round(w * 0.35);
      el.scrollBy({ left: direction * step, behavior: 'smooth' });
      fireDeckScrollHaptic();
    },
    [scrollState.width, layout.w]
  );
  const stopDeckHapticLoop = useCallback(() => {
    deckTouchActiveRef.current = false;
    if (deckHapticLoopRafRef.current) {
      cancelAnimationFrame(deckHapticLoopRafRef.current);
      deckHapticLoopRafRef.current = null;
    }
  }, []);
  const runDeckHapticLoop = useCallback(() => {
    if (!deckTouchActiveRef.current) {
      deckHapticLoopRafRef.current = null;
      return;
    }
    const el = scrollRef.current;
    if (
      el
      && !freezeDeck
      && subPhase === 'picking'
      && !skipScrollHapticRef.current
    ) {
      const currentLeft = el.scrollLeft;
      const moved = Math.abs(currentLeft - lastScrollLeftForHapticRef.current);
      if (moved > 0.05) {
        const now = Date.now();
        if (now - lastHapticRef.current > 52) {
          lastHapticRef.current = now;
          fireDeckScrollHaptic();
        }
      }
      lastScrollLeftForHapticRef.current = currentLeft;
    }
    deckHapticLoopRafRef.current = requestAnimationFrame(runDeckHapticLoop);
  }, [freezeDeck, subPhase]);
  const handleDeckTouchStart = useCallback(() => {
    if (freezeDeck || subPhase !== 'picking') return;
    deckTouchActiveRef.current = true;
    if (scrollRef.current) {
      lastScrollLeftForHapticRef.current = scrollRef.current.scrollLeft;
    }
    if (!deckHapticLoopRafRef.current) {
      deckHapticLoopRafRef.current = requestAnimationFrame(runDeckHapticLoop);
    }
    const now = Date.now();
    if (now - lastHapticRef.current <= 95) return;
    lastHapticRef.current = now;
    fireDeckScrollHaptic();
  }, [freezeDeck, subPhase, runDeckHapticLoop]);
  useEffect(() => stopDeckHapticLoop, [stopDeckHapticLoop]);

  const getStableNoise = (seed) => {
    const raw = Math.sin(seed * 12.9898) * 43758.5453;
    return raw - Math.floor(raw);
  };

  const getDeckPose = (index) => {
    const floatSeed = getStableNoise(index + 1);
    const centerIndex = (n - 1) / 2;
    const centerDistance = centerIndex > 0 ? (index - centerIndex) / centerIndex : 0;
    const arcCurve = Math.pow(Math.abs(centerDistance), 1.35);
    // Небольшая дуга и стартовый хаос, чтобы колода не выглядела «линейкой» в первые секунды.
    const arcYOffset = arcCurve * 14.4 - 3.2;
    const staticYOffset = (getStableNoise(index + 91) - 0.5) * 17.6;
    const staticTilt = (getStableNoise(index + 17) - 0.5) * 9.2;
    return {
      x: Math.round(edgePad + index * STEP_X + CARD_W * 0.5),
      y: deckTopBase + arcYOffset + staticYOffset,
      rotate: staticTilt,
      floatAmp: 1 + getStableNoise(index + 33) * 1.2,
      floatDelay: getStableNoise(index + 51) * 1.2,
      floatDuration: 4.8 + getStableNoise(index + 71) * 1.2,
    };
  };

  /** Слот выбранной карты в координатах viewport: не зависит от scrollLeft колоды */
  const getPickedSlotViewport = useCallback(
    (order) => {
      const el = containerRef.current;
      if (!el || typeof el.getBoundingClientRect !== 'function') {
        return { left: 0, top: 0, width: CARD_W, height: CARD_H, rotateZ: 0 };
      }
      const cr = el.getBoundingClientRect();
      if (useFormationLayout && layout.w > 0 && layout.h > 0) {
        const boardW = layout.w;
        const boardH = layout.h * FAN_FORMATION_HEIGHT_RATIO;
        const px = getFanFormationSlotPixel(spreadId, order, boardW, boardH);
        return {
          left: cr.left + px.left,
          top: cr.top + px.top,
          width: px.width,
          height: px.height,
          rotateZ: px.rotateZ,
        };
      }
      const vw = scrollState.width > 0 ? scrollState.width : layout.w;
      const maxOrder = Math.max(0, selectedSpread.cards - 1);
      const spread = Math.min(
        layout.w * 0.31,
        CARD_W * 1.12,
        maxOrder > 0 ? (layout.w * 0.88) / maxOrder : layout.w * 0.31
      );
      const centerOffset = (selectedSpread.cards - 1) / 2;
      const left = cr.left + vw / 2 - CARD_W / 2 + (order - centerOffset) * spread;
      const oneCardPick = selectedSpread.cards === 1;
      const top =
        cr.top +
        selectionY +
        (oneCardPick
          ? -Math.min(40, layout.h * 0.055) + Math.min(26, layout.h * 0.038)
          : 0) +
        (order === 1 ? -8 : 0) +
        Math.abs(order - centerOffset) * 6;
      return { left, top, width: CARD_W, height: CARD_H, rotateZ: 0 };
    },
    [
      CARD_W,
      CARD_H,
      layout.w,
      layout.h,
      scrollState.width,
      selectedSpread.cards,
      selectionY,
      useFormationLayout,
      spreadId,
    ]
  );

  const singlePickStarted = selectedSpread.cards === 1 && (singleTapStarted || pickedOrder.length > 0);
  const shouldShowDeckCompleteState =
    (pickedOrder.length >= selectedSpread.cards && subPhase !== 'picking') || singlePickStarted;
  const shouldFadeDeckLayer =
    subPhase === 'flipping'
    || singlePickStarted;
  const shouldHideScrollCue = shouldFadeDeckLayer || shouldShowDeckCompleteState;
  const headerTitleParts = shouldShowDeckCompleteState
    ? null
    : (() => {
        const c = selectedSpread.cards;
        const after = c === 1 ? 'карту' : c >= 2 && c <= 4 ? 'карты' : 'карт';
        if (c === 1) {
          return { before: 'Выберите', after, skipNum: true };
        }
        return { before: 'Выберите', num: c, after, skipNum: false };
      })();
  const headerTitle = shouldShowDeckCompleteState
    ? (selectedSpread.cards === 1 ? 'Карты услышали твой голос' : 'Карты услышали твой вопрос')
    : `Выберите ${pluralCards(selectedSpread.cards)}`;
  const headerSubtitle = shouldShowDeckCompleteState
    ? ''
    : (spreadHint?.description || 'Прокрутите колоду и доверьтесь интуиции');

  return (
    <div className="flex flex-col w-full items-center flex-1 min-h-0 overflow-visible">
      <div
        className="shrink-0 flex items-center justify-center text-center w-full px-4"
        style={{
          paddingTop: 'max(2.85rem, calc(env(safe-area-inset-top, 0px) + 2.55rem))',
          /* Стабильная высота: иначе при смене «Выберите N карт» на итоговый заголовок шапка сжимается,
             flex-1 зона колоды растёт и абсолютные top-% пересчитываются — колода визуально «прыгает». */
          minHeight: '11rem',
        }}
      >
        <div className="max-w-sm flex flex-col items-center justify-center w-full" style={{ minHeight: '8.5rem' }}>
          <AnimatePresence mode="wait" initial={false}>
            {!shouldShowDeckCompleteState ? (
              <motion.div
                key="header-picking"
                className="w-full flex flex-col items-center"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
              >
                <p
                  className="text-[30px] leading-none uppercase tracking-[0.14em]"
                  style={{
                    fontFamily: "'Cormorant Garamond', 'Cinzel', serif",
                    background: 'linear-gradient(180deg, #fff7df 0%, #f6d06f 38%, #c9952d 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    textShadow: '0 0 22px rgba(251,191,36,0.12)',
                  }}
                >
                  {headerTitleParts ? (
                    <>
                      <span className="block">{headerTitleParts.before}</span>
                      {!headerTitleParts.skipNum && <span className="block">{headerTitleParts.num}</span>}
                      <span className="block mt-1">{headerTitleParts.after}</span>
                    </>
                  ) : null}
                </p>
                <div className="mt-2 w-full min-h-[2.75rem] flex items-start justify-center">
                  <p className="text-[12px] leading-5 tracking-[0.08em] uppercase text-amber-100/80">
                    {headerSubtitle}
                  </p>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="header-picked"
                className="w-full flex flex-col items-center"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.36, ease: [0.22, 1, 0.36, 1] }}
              >
                <p
                  className="text-[30px] leading-none uppercase tracking-[0.14em]"
                  style={{
                    fontFamily: "'Cormorant Garamond', 'Cinzel', serif",
                    background: 'linear-gradient(180deg, #fff7df 0%, #f6d06f 38%, #c9952d 100%)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                    textShadow: '0 0 22px rgba(251,191,36,0.12)',
                  }}
                >
                  {headerTitle}
                </p>
                <div className="mt-2 w-full min-h-[2.75rem] flex items-start justify-center">
                  <span className="invisible text-[12px] leading-5 tracking-[0.08em] uppercase select-none" aria-hidden>
                    &nbsp;
                  </span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <div
        ref={containerRef}
        className="relative flex-1 min-h-0 overflow-visible w-[calc(100%+2rem)] -mx-4"
        style={{
          minHeight: 320,
          paddingBottom: 'max(5.75rem, calc(env(safe-area-inset-bottom, 0px) + 4.75rem))',
        }}
      >
        {isTenCardsSpread ? (
          <motion.div
            className="absolute inset-x-0 z-[120] pointer-events-auto flex items-center justify-center gap-2 px-3 max-w-md mx-auto"
            style={{ top: '40%' }}
            initial={false}
            animate={{ opacity: shouldHideScrollCue ? 0 : 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              type="button"
              onClick={() => scrollDeckByStep(-1)}
              disabled={freezeDeck || subPhase !== 'picking'}
              className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0 disabled:opacity-40"
              aria-label="Прокрутить колоду влево"
            >
              <DeckScrollArrowTrail direction="left" hidden={shouldHideScrollCue} />
            </button>
            <p className="flex-1 text-center text-[11px] uppercase tracking-[0.2em] text-amber-200/90 min-w-0 leading-tight px-1">
              {shouldHideScrollCue ? 'Открываю расклад' : 'Прокрути колоду'}
            </p>
            <button
              type="button"
              onClick={() => scrollDeckByStep(1)}
              disabled={freezeDeck || subPhase !== 'picking'}
              className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0 disabled:opacity-40"
              aria-label="Прокрутить колоду вправо"
            >
              <DeckScrollArrowTrail direction="right" hidden={shouldHideScrollCue} />
            </button>
          </motion.div>
        ) : (
          <motion.div
            className="absolute inset-x-0 z-[120] pointer-events-auto flex items-center justify-center gap-2 px-3 max-w-md mx-auto"
            style={{ top: spreadId === 'financial' ? '43%' : '40%' }}
            initial={false}
            animate={{ opacity: shouldHideScrollCue ? 0 : 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <button
              type="button"
              onClick={() => scrollDeckByStep(-1)}
              disabled={freezeDeck || subPhase !== 'picking'}
              className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0 disabled:opacity-40"
              aria-label="Прокрутить колоду влево"
            >
              <DeckScrollArrowTrail direction="left" hidden={shouldHideScrollCue} />
            </button>
            <p className="flex-1 text-center text-[11px] uppercase tracking-[0.2em] text-amber-200/90 min-w-0 leading-tight px-1">
              {shouldHideScrollCue ? 'Открываю расклад' : 'Прокрути колоду'}
            </p>
            <button
              type="button"
              onClick={() => scrollDeckByStep(1)}
              disabled={freezeDeck || subPhase !== 'picking'}
              className="p-2.5 touch-manipulation rounded-lg active:scale-95 shrink-0 disabled:opacity-40"
              aria-label="Прокрутить колоду вправо"
            >
              <DeckScrollArrowTrail direction="right" hidden={shouldHideScrollCue} />
            </button>
          </motion.div>
        )}

        <motion.div
          className="absolute inset-0"
          initial={false}
          animate={{ opacity: shouldFadeDeckLayer ? 0 : 1 }}
          transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
          style={{
            pointerEvents: freezeDeck ? 'none' : 'auto',
          }}
        >
          <div
            ref={scrollRef}
            className="h-full w-full overflow-x-auto overflow-y-hidden scrollbar-hide"
            onTouchStart={handleDeckTouchStart}
            onTouchEnd={stopDeckHapticLoop}
            onTouchCancel={stopDeckHapticLoop}
            style={{
              WebkitOverflowScrolling: 'touch',
              overflowX: 'auto',
              overflowAnchor: 'none',
              overscrollBehaviorX: 'contain',
              overscrollBehaviorY: 'none',
              touchAction: freezeDeck ? 'none' : 'pan-x',
            }}
          >
            <div
              className="relative"
              style={{
                width: totalWidth,
                height: '100%',
                minHeight: layout.h,
              }}
            >
            {pickable.map((card, index) => {
              const pose = getDeckPose(index);
              const order = pickedMap.get(index);
              const isPicked = order != null || instantHiddenIndices.has(index);
              const isInteractive = subPhase === 'picking' && !freezeDeck && !isPicked;
              if (isPicked) {
                return null;
              }
              const levAmp = 6.4 + pose.floatAmp * 2.48;
              return (
                <motion.div
                  key={`${card.id}-${index}`}
                  className="absolute"
                  style={{
                    left: 0,
                    top: 0,
                    width: CARD_W,
                    height: CARD_H,
                    zIndex: 50 + index,
                    transformOrigin: 'center center',
                    pointerEvents: isInteractive ? 'auto' : 'none',
                    filter:
                      'drop-shadow(0 2px 0 rgba(0,0,0,0.12)) drop-shadow(4px 6px 10px rgba(0,0,0,0.28)) drop-shadow(0 14px 22px rgba(0,0,0,0.35))',
                    willChange: 'transform',
                  }}
                  initial={{
                    x: pose.x,
                    y: pose.y + 24 + TAROT_PICK_DECK_ROW_OFFSET_Y,
                    rotate: pose.rotate,
                    scale: 0.96,
                    opacity: justAppeared ? 0 : 1,
                  }}
                  animate={{
                    x: pose.x,
                    y: [
                      pose.y + 24 + TAROT_PICK_DECK_ROW_OFFSET_Y,
                      pose.y + 24 + TAROT_PICK_DECK_ROW_OFFSET_Y - levAmp,
                      pose.y + 24 + TAROT_PICK_DECK_ROW_OFFSET_Y,
                    ],
                    rotate: pose.rotate,
                    scale: 1,
                    opacity: 1,
                  }}
                  transition={{
                    y: {
                      duration: pose.floatDuration,
                      delay: pose.floatDelay,
                      repeat: Infinity,
                      repeatType: 'reverse',
                      ease: 'easeInOut',
                    },
                    x: { duration: 0 },
                    rotate: { duration: 0 },
                    scale: { duration: 0 },
                    opacity: { duration: 0 },
                  }}
                >
                  {isInteractive ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        const nextOrder = pickedOrder.length;
                        flightOriginByOrderRef.current[nextOrder] = e.currentTarget.getBoundingClientRect();
                        if (selectedSpread.cards === 1) setSingleTapStarted(true);
                        setInstantHiddenIndices((prev) => {
                          if (prev.has(index)) return prev;
                          const nextSet = new Set(prev);
                          nextSet.add(index);
                          return nextSet;
                        });
                        handleCardSelect(card, index);
                      }}
                      className="relative block h-full w-full overflow-hidden rounded-[14px] touch-manipulation"
                    >
                      <motion.div
                        className="absolute inset-0 rounded-[14px]"
                        whileTap={{ scale: 0.97 }}
                        transition={{ duration: 0.2 }}
                        style={{ transformStyle: 'preserve-3d', WebkitTransformStyle: 'preserve-3d' }}
                      >
                        <div
                          className="tarot-back-wrap h-full w-full overflow-hidden rounded-[14px] border border-white/12 bg-[rgba(7,6,18,0.96)]"
                          style={{
                            boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.06), 0 1px 0 rgba(0,0,0,0.35)',
                          }}
                        >
                          {card.backImage ? (
                            <img src={card.backImage} alt="" className="h-full w-full object-cover rounded-[14px]" loading="lazy" />
                          ) : (
                            <div className="absolute inset-0 rounded-[14px]" style={{ background: 'radial-gradient(circle at 50% 18%, rgba(251,191,36,0.32), transparent 46%), linear-gradient(180deg, rgba(15,12,35,0.98) 0%, rgba(6,5,18,0.99) 100%)' }} />
                          )}
                        </div>
                      </motion.div>
                    </button>
                  ) : null}
                </motion.div>
              );
            })}
          </div>
          </div>
        </motion.div>
      </div>
      {typeof document !== 'undefined' && !hideLiftedCardsPortal
        ? createPortal(
            <div className="pointer-events-none fixed inset-0 z-[400]">
              {pickedOrder.map((deckIndex, order) => {
                const selectedCard = pickedCards[order];
                if (!selectedCard) return null;
                const pose = getDeckPose(deckIndex);
                const slot = getPickedSlotViewport(order);
                const slotW = slot.width ?? CARD_W;
                const slotH = slot.height ?? CARD_H;
                const origin = flightOriginByOrderRef.current[order];
                const ix = origin ? origin.left + origin.width / 2 - CARD_W / 2 : slot.left;
                const iy = origin ? origin.top + origin.height / 2 - CARD_H / 2 : slot.top + TAROT_PICK_DECK_ROW_OFFSET_Y;
                const oneCardLift = selectedSpread.cards === 1;
                /** Карта дня: крупнее при вылете и перевороте (~на 20% меньше прежнего крупного). */
                const liftEndScale = useFormationLayout ? 1 : (oneCardLift ? 1.952 : 1.02);
                const liftStartScale = oneCardLift ? 1.0 : 0.96;
                const endRotate = slot.rotateZ ?? 0;
                const liftRadiusClass = oneCardLift ? 'rounded-[12px]' : 'rounded-[14px]';
                const liftFaceFrame = oneCardLift
                  ? 'absolute inset-0 overflow-hidden rounded-[12px] border-0 bg-transparent'
                  : 'absolute inset-0 overflow-hidden rounded-[14px] border border-white/10 bg-[rgba(7,6,18,0.96)]';
                const liftFaceFrameFront = oneCardLift
                  ? 'absolute inset-0 overflow-hidden rounded-[12px] border-0 bg-transparent'
                  : 'absolute inset-0 overflow-hidden rounded-[14px] border border-amber-200/25 bg-[rgba(17,11,7,0.96)]';
                const liftShadow = oneCardLift
                  ? 'drop-shadow(0 10px 28px rgba(0,0,0,0.4))'
                  : 'drop-shadow(0 2px 0 rgba(0,0,0,0.1)) drop-shadow(4px 8px 14px rgba(0,0,0,0.3)) drop-shadow(0 16px 26px rgba(0,0,0,0.36))';
                return (
                  <motion.div
                    key={`portal-pick-${order}-${deckIndex}`}
                    ref={oneCardLift && order === 0 && singlePortalCardRef ? singlePortalCardRef : undefined}
                    className={`fixed ${liftRadiusClass}`}
                    style={{
                      width: slotW,
                      height: slotH,
                      zIndex: 420 + order,
                      filter: liftShadow,
                    }}
                    initial={{ left: ix, top: iy, width: CARD_W, height: CARD_H, scale: liftStartScale, rotate: pose.rotate }}
                    animate={{
                      left: slot.left,
                      top: slot.top,
                      width: slotW,
                      height: slotH,
                      scale: liftEndScale,
                      rotate: endRotate,
                    }}
                    transition={{ duration: 0.92, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <motion.div
                      className="relative h-full w-full"
                      initial={{ rotateY: 0 }}
                      animate={{ rotateY: 180 }}
                      transition={{
                        duration: 0.78,
                        delay: 0.94,
                        ease: [0.22, 1, 0.36, 1],
                      }}
                      style={{
                        transformStyle: 'preserve-3d',
                        WebkitTransformStyle: 'preserve-3d',
                        perspective: 1200,
                        WebkitPerspective: 1200,
                      }}
                    >
                      <div
                        className={liftFaceFrame}
                        style={{
                          backfaceVisibility: 'hidden',
                          WebkitBackfaceVisibility: 'hidden',
                        }}
                      >
                        {pickable[deckIndex]?.backImage ? (
                          <img
                            src={pickable[deckIndex].backImage}
                            alt=""
                            className={`h-full w-full object-cover ${oneCardLift ? 'rounded-[12px]' : 'rounded-[14px]'}`}
                            loading="lazy"
                          />
                        ) : (
                          <div
                            className={`absolute inset-0 ${oneCardLift ? 'rounded-[12px]' : 'rounded-[14px]'}`}
                            style={{ background: 'radial-gradient(circle at 50% 18%, rgba(251,191,36,0.32), transparent 46%), linear-gradient(180deg, rgba(15,12,35,0.98) 0%, rgba(6,5,18,0.99) 100%)' }}
                          />
                        )}
                      </div>
                      <div
                        className={liftFaceFrameFront}
                        style={{
                          backfaceVisibility: 'hidden',
                          WebkitBackfaceVisibility: 'hidden',
                          transform: 'rotateY(-180deg)',
                        }}
                      >
                        <CardFaceWithFallback
                          card={{ ...selectedCard, imageLoader: selectedCard?.imageLoader || null }}
                          isReversed={selectedCard?.is_reversed}
                          useResultLikeFit={oneCardLift}
                        />
                      </div>
                    </motion.div>
                  </motion.div>
                );
              })}
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
function TenCardConsultPanel({
  spread = [],
  currentPositions = [],
  onRetry,
  overallInterpretation = '',
  readingId,
  followUpQuestions = [],
  sendChatMessage,
  chatMessages = [],
  chatLoading = false,
  dialogueRequired = false,
  guidedFinished = true,
  showFinalSummary = false,
  practicalAdvice = '',
  onNewSpread,
  question = '',
  spreadId = 'ten_cards',
  triggerHaptics,
}) {
  const [activeIdx, setActiveIdx] = useState(null);
  const [zoomOpen, setZoomOpen] = useState(false);
  const [shareSending, setShareSending] = useState(false);
  const celticCards = Array.isArray(spread) ? spread.slice(0, 10) : [];
  const activeCard = activeIdx != null ? celticCards[activeIdx] : null;
  const showResultBlock =
    Boolean((overallInterpretation || '').trim()) && (guidedFinished || !dialogueRequired) && (showFinalSummary || !dialogueRequired);
  return (
    <div className="space-y-4">
      {showResultBlock ? (
        <>
          {celticCards.length > 0 ? (
            <div className="mx-auto w-full max-w-md space-y-2 pt-4">
              <p className="text-center text-amber-200/90 text-xs flex items-center justify-center gap-1.5">
                <LayoutGrid className="w-3.5 h-3.5 shrink-0 opacity-85" aria-hidden />
                Карты расклада
              </p>
              <p className="text-center text-white/70 text-[12px] leading-snug">Нажмите на карту, чтобы прочитать трактовку по каждой позиции.</p>
              <div className="grid grid-cols-5 gap-2">
                {celticCards.map((card, idx) => (
                  <button
                    key={`celtic-grid-${card?.id || idx}-${idx}`}
                    type="button"
                    onClick={() => setActiveIdx(idx)}
                    className="rounded-[10px] overflow-hidden bg-transparent"
                    style={{ aspectRatio: `${500}/${895}` }}
                  >
                    {card?.image ? (
                      <img
                        src={card.image}
                        alt={getCardDisplayName(card) || `Карта ${idx + 1}`}
                        className="w-full h-full object-cover rounded-[10px]"
                        style={{ transform: card?.is_reversed ? 'rotate(180deg)' : undefined }}
                      />
                    ) : (
                      <div className="w-full h-full bg-amber-900/20" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="flex flex-col items-center max-w-md mx-auto w-full">
            <TtsPlayButton text={fixOverallInterpretationTypo(overallInterpretation)} className="mb-3" />
            <div className="w-full text-center">
              <p className="text-violet-200 text-sm mb-2 flex items-center justify-center gap-1.5">
                <Sparkles className="w-4 h-4 shrink-0 opacity-90 text-violet-300/90" aria-hidden />
                Итоговый расклад
              </p>
              <TarotInterpretBody text={fixOverallInterpretationTypo(overallInterpretation)} center />
            </div>
          </div>
          {guidedFinished && !spread.some((c) => c?.loading) && (overallInterpretation || '').trim() ? (
            <>
              <div className="max-w-md mx-auto pt-4 border-t border-amber-400/20 text-center">
                <p className="text-amber-200 font-medium text-xs mb-2 flex items-center justify-center gap-1.5">
                  <Lightbulb className="w-3.5 h-3.5 shrink-0 opacity-90" aria-hidden />
                  Совет
                </p>
                <TarotInterpretBody text={practicalAdvice || 'Доверьтесь интуиции при осмыслении расклада.'} center />
              </div>
              <div className="flex flex-col gap-3 pt-4 max-w-md mx-auto w-full">
                <motion.button
                  type="button"
                  disabled={shareSending}
                  onClick={async () => {
                    if (shareSending) return;
                    setShareSending(true);
                    try {
                      const initData = window?.Telegram?.WebApp?.initData || '';
                      const cardsPayload = spread.map((c, idx) => ({
                        position_name: c?.position_name || currentPositions[idx] || `Позиция ${idx + 1}`,
                        name: getCardNameRu(c?.id, c?.astrovDeckId) || c?.card_name || c?.name || 'Карта',
                        meaning: c?.meaning || c?.interpretation || '',
                        image: c?.image ? (c.image.startsWith('http') ? c.image : `${ABS_BASE}/${c.image.replace(/^\//, '')}`) : '',
                        is_reversed: typeof c?.is_reversed === 'boolean' ? c.is_reversed : null,
                      }));
                      const res = await fetch(`${API_BASE}/api/tarot/share`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                          init_data: initData,
                          question: question || '',
                          overall: overallInterpretation || '',
                          spread_id: spreadId || '',
                          cards: cardsPayload,
                          chat_transcript: formatTarotChatTranscript(chatMessages),
                          practical_advice: (practicalAdvice || '').trim(),
                        }),
                      });
                      const data = res.ok ? await res.json() : {};
                      if (!data.ok) throw new Error(data.message || 'Не удалось отправить.');
                      triggerHaptics?.('medium');
                      window?.Telegram?.WebApp?.showPopup?.({
                        title: 'Готово',
                        message: 'Расклад отправлен в личку бота. Перешлите сообщение в нужный чат, чтобы поделиться.',
                      });
                    } catch (e) {
                      window?.Telegram?.WebApp?.showPopup?.({
                        title: 'Ошибка',
                        message: e?.message || 'Не удалось отправить.',
                      });
                    } finally {
                      setShareSending(false);
                    }
                  }}
                  className={TAROT_MAIN_CTA_CLASS}
                  style={TAROT_SHARE_CTA_STYLE}
                >
                  {shareSending ? 'Отправка...' : 'Поделиться раскладом'}
                </motion.button>
                <motion.button type="button" onClick={onNewSpread} className={TAROT_GHOST_CTA_CLASS}>
                  ↩ Вернуться
                </motion.button>
              </div>
            </>
          ) : null}
          <AnimatePresence>
            {activeCard ? (
              <motion.div
                className="fixed inset-0 z-[300] bg-black/60 backdrop-blur-md pt-[max(48px,env(safe-area-inset-top)+40px)] pb-4 px-4 flex items-center justify-center"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setActiveIdx(null)}
              >
                <motion.div
                  className="w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-white/10 bg-slate-950/50 backdrop-blur-2xl tarot-scrollless"
                  initial={{ y: 16, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: 16, opacity: 0 }}
                  transition={{ duration: 0.25, ease: TAROT_ANIM.SMOOTH_EASE }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="shrink-0 pt-2 px-4 pb-2 border-b border-white/10">
                    <p className="text-center text-amber-200 text-sm">
                      {(currentPositions[activeIdx] || activeCard?.position_name || `Позиция ${activeIdx + 1}`)}
                    </p>
                  </div>
                  <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4" style={{ WebkitOverflowScrolling: 'touch', paddingBottom: 'max(88px, calc(env(safe-area-inset-bottom) + 72px))' }}>
                    <div className="mx-auto rounded-2xl overflow-hidden bg-transparent" style={{ width: 160, height: Math.round(160 / TAROT_ASPECT) }}>
                      {activeCard?.image ? (
                        <img
                          src={activeCard.image}
                          alt={getCardDisplayName(activeCard)}
                          className="w-full h-full object-cover rounded-2xl cursor-zoom-in"
                          style={{ transform: activeCard?.is_reversed ? 'rotate(180deg)' : undefined }}
                          onClick={() => setZoomOpen(true)}
                        />
                      ) : (
                        <div className="w-full h-full bg-amber-900/25" />
                      )}
                    </div>
                    <p className="mt-2 text-amber-200/95 text-xs text-center">
                      {getCardDisplayName(activeCard)}
                      {activeCard?.is_reversed ? ' (перевёрнутая)' : ''}
                    </p>
                    {!activeCard?.loading && formatCardInterpretation(activeCard) ? (
                      <div className="flex justify-center mt-3">
                        <TtsPlayButton text={formatCardInterpretation(activeCard)} />
                      </div>
                    ) : null}
                    {activeCard?.loading ? (
                      <p className="mt-3 text-white/75 text-[12px] leading-relaxed text-center">Идёт анализ карты...</p>
                    ) : (
                      <TarotInterpretBody className="mt-3" text={formatCardInterpretation(activeCard)} center />
                    )}
                    <Button size="md" className="w-full justify-center mt-6" onClick={() => setActiveIdx(null)}>
                      Закрыть
                    </Button>
                  </div>
                </motion.div>
              </motion.div>
            ) : null}
          </AnimatePresence>
          <CardZoomOverlay
            open={zoomOpen}
            onClose={() => setZoomOpen(false)}
            src={activeCard?.image || ''}
            alt={getCardDisplayName(activeCard)}
          />
        </>
      ) : null}

      {/* Для кельтского итога чат скрыт: после кнопок не показываем отдельное окно «Скрыть диалог». */}
    </div>
  );
}

function _firstSentence(text = '') {
  const src = String(text || '').trim();
  if (!src) return '';
  const m = src.match(/(.+?[.!?])(\s|$)/);
  return (m?.[1] || src).trim();
}

function _normalizeNarrative(text = '') {
  return String(text || '')
    .toLowerCase()
    .replace(/[«»"']/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function _isSameNarrative(a = '', b = '') {
  if (!a || !b) return false;
  return _normalizeNarrative(a) === _normalizeNarrative(b);
}

function _looksLikeOverallThreeCardsText(text = '') {
  const t = _normalizeNarrative(text);
  if (!t) return false;
  const hasAllPositions = t.includes('прошл') && t.includes('настоящ') && t.includes('будущ');
  return hasAllPositions || t.length > 460;
}

/** Убирает из текста интерпретации подстановки вида «Карта «Карта»», «Карта «40»», «Карта «Карта 7»» - заменяет на просто «Карта». */
function sanitizeCardLabelInText(text) {
  if (!text || typeof text !== 'string') return text;
  return text
    .replace(/Карта\s*«\s*Карта\s*\d*\s*»/gi, 'Карта')
    .replace(/Карта\s*«\s*\d+\s*»/g, 'Карта');
}

/** Исправляет опечатку «К карты демонстрируют» → «Карты демонстрируют» в итоге расклада. */
function fixOverallInterpretationTypo(text) {
  if (!text || typeof text !== 'string') return text;
  let cleaned = text.replace(
    /Свяжите вывод этой позиции с вашим вопросом и выберите один ближайший шаг\.?/gi,
    ''
  );
  cleaned = cleaned.replace(/\s{2,}/g, ' ').trim();
  const fixed = cleaned.replace(/^К\s+карты\s/iu, 'Карты ');
  const sentences = fixed
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const dedup = [];
  for (const s of sentences) {
    const norm = s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, '').replace(/\s+/g, ' ').trim();
    if (!norm) continue;
    if (dedup.some((d) => d.norm === norm)) continue;
    dedup.push({ norm, raw: s });
  }
  return dedup.map((d) => d.raw).join(' ');
}

/** Не показываем фразу «Сигнал карты считывается, но требует дополнительного размышления» - подменяем осмысленным текстом. */
function formatTarotChatTranscript(chatMessages) {
  if (!Array.isArray(chatMessages) || !chatMessages.length) return '';
  return chatMessages
    .map((m) => {
      const role = m?.role === 'user' ? 'Вы' : 'Таролог';
      const content = String(m?.content || '').trim();
      if (!content) return '';
      return `${role}: ${content}`;
    })
    .filter(Boolean)
    .join('\n\n');
}

function formatCardInterpretation(card, fallback = '-') {
  let raw = (card?.meaning || card?.interpretation || '').trim();
  if (!raw) return fallback;
  if (/требует дополнительного размышления|сигнал карты считывается/i.test(raw)) {
    let name = getCardNameRu(card?.id, card?.astrovDeckId) || (card?.card_name || card?.name || '').trim();
    const pos = card?.position_name || '';
    if (!name || name === 'Карта' || /^Карта\s*\d+$/i.test(name) || /^\d+$/.test(name)) name = '';
    const cardLabel = name ? `Карта «${name}»` : 'Карта';
    return pos
      ? `${cardLabel} в позиции «${pos}» - ключевой сигнал этой части расклада. Доверьтесь интуиции при осмыслении.`
      : `${cardLabel} указывает на важный акцент в этой части расклада. Доверьтесь интуиции.`;
  }
  raw = sanitizeCardLabelInText(raw);
  return raw;
}

function RelationshipPairsPanel({ spread = [] }) {
  const [zoomCard, setZoomCard] = useState(null);
  if (!Array.isArray(spread) || spread.length < 5) return null;
  const pairs = spread.length >= 6
    ? [
      { title: 'Пара 1: Роли (Он и Она)', left: spread[0], right: spread[3] },
      { title: 'Пара 2: Чувства (Он и Она)', left: spread[1], right: spread[4] },
      { title: 'Пара 3: Вектор и итог', left: spread[2], right: spread[5] },
    ]
    : [
      { title: 'Пара 1: Он и Она', left: spread[0], right: spread[3] },
      { title: 'Пара 2: Чувства и препятствие', left: spread[1], right: spread[4] },
      { title: 'Ключ союза', left: spread[2], right: null },
    ];

  return (
    <Card className="p-4 space-y-4 border-amber-400/30">
      <p className="text-amber-200 text-sm font-medium flex items-center gap-2">
        <Users className="w-4 h-4 shrink-0 opacity-90" aria-hidden />
        Синтез по парам (Он и Она, по 2 карты)
      </p>
      {pairs.map((p) => {
        const leftName = p.left?.card_name || p.left?.name || 'Карта';
        const rightName = p.right?.card_name || p.right?.name || '';
        const leftMeaning = (p.left?.meaning || p.left?.interpretation || '').trim();
        const rightMeaning = (p.right?.meaning || p.right?.interpretation || '').trim();
        const combined = p.right
          ? `Вместе: ${leftName} и ${rightName} - действуйте через диалог и синхронизацию ожиданий.`
          : `Вместе: ${leftName} - центральный ключ союза на ближайший этап.`;
        return (
          <div key={p.title} className="rounded-xl border border-amber-400/20 bg-black/25 p-4 space-y-3">
            <p className="text-amber-200/95 text-sm font-medium">{p.title}</p>
            <div className="flex items-stretch justify-center gap-3 min-h-[140px]">
              <div className="flex-1 flex flex-col items-center max-w-[100px]">
                <div className="rounded-[12px] overflow-hidden shadow-lg border border-white/10 flex-1 w-full min-h-[120px] bg-transparent flex items-center justify-center">
                  {p.left?.image ? (
                    <img
                      src={p.left.image}
                      alt={leftName}
                      className="w-full h-full object-cover rounded-2xl cursor-zoom-in"
                      style={{ transform: p.left?.is_reversed ? 'rotate(180deg)' : undefined }}
                      onClick={() => setZoomCard(p.left)}
                    />
                  ) : (
                    <span className="text-white/50 text-xs">Он</span>
                  )}
                </div>
                <p className="text-amber-200/90 text-[11px] mt-1.5 text-center truncate w-full">{leftName}</p>
              </div>
              <div className="flex-1 flex flex-col items-center max-w-[100px]">
                {p.right ? (
                  <>
<div className="rounded-[12px] overflow-hidden shadow-lg border border-white/10 flex-1 w-full min-h-[120px] bg-transparent flex items-center justify-center">
                  {p.right?.image ? (
                    <img
                      src={p.right.image}
                      alt={rightName}
                      className="w-full h-full object-cover rounded-2xl cursor-zoom-in"
                          style={{ transform: p.right?.is_reversed ? 'rotate(180deg)' : undefined }}
                          onClick={() => setZoomCard(p.right)}
                        />
                      ) : (
                        <span className="text-white/50 text-xs">Она</span>
                      )}
                    </div>
                    <p className="text-amber-200/90 text-[11px] mt-1.5 text-center truncate w-full">{rightName}</p>
                  </>
                ) : (
                  <div className="flex-1 w-full min-h-[120px] flex items-center justify-center text-white/40 text-xs">-</div>
                )}
              </div>
            </div>
            {leftMeaning ? (
              <p className="text-white/85 text-[12px] leading-relaxed m-0">
                <span className="text-amber-200/80 text-xs">Он:</span>{' '}
                <TarotInterpretInline text={leftMeaning} />
              </p>
            ) : null}
            {p.right && rightMeaning ? (
              <p className="text-white/85 text-[12px] leading-relaxed m-0">
                <span className="text-amber-200/80 text-xs">Она:</span>{' '}
                <TarotInterpretInline text={rightMeaning} />
              </p>
            ) : null}
            <p className="text-white/75 text-xs pt-1">{combined}</p>
          </div>
        );
      })}
      <CardZoomOverlay
        open={Boolean(zoomCard)}
        onClose={() => setZoomCard(null)}
        src={zoomCard?.image || ''}
        alt={getCardDisplayName(zoomCard)}
      />
    </Card>
  );
}

function SpreadSummaryModalView({
  spread = [],
  currentPositions = [],
  overallInterpretation = '',
  overallSummaryShort = '',
  practicalAdvice = '',
  spreadId = '',
  question = '',
  chatMessages = [],
  onNewSpread,
  triggerHaptics,
}) {
  const [activeIndex, setActiveIndex] = useState(null);
  const [zoomOpen, setZoomOpen] = useState(false);
  const activeCard = activeIndex != null ? spread[activeIndex] : null;
  const openCardDetails = (idx) => {
    triggerHaptics?.('light');
    setActiveIndex(idx);
  };
  const renderSpreadCardButton = (card, idx) => {
    const btn = (
      <button
        type="button"
        onClick={() => openCardDetails(idx)}
        className="rounded-[12px] overflow-hidden bg-transparent w-full"
        style={{
          aspectRatio: `${500}/${895}`,
          boxShadow: '0 14px 28px rgba(0,0,0,0.4), 0 3px 0 rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.08)',
        }}
      >
        {card?.image ? (
          <img
            src={card.image}
            alt={getCardDisplayName(card) || `Карта ${idx + 1}`}
            className="w-full h-full object-cover rounded-2xl"
            style={{ transform: card?.is_reversed ? 'rotate(180deg)' : undefined }}
          />
        ) : (
          <div className="w-full h-full bg-amber-900/20" />
        )}
      </button>
    );
    if (spreadId === 'three_cards') {
      return (
        <motion.div
          key={`${card?.id || idx}-${idx}`}
          className="w-full"
          style={{ transformOrigin: 'center bottom' }}
          animate={{ y: [0, -4, 0] }}
          transition={{
            duration: 3.6 + (idx % 3) * 0.35,
            repeat: Infinity,
            repeatType: 'reverse',
            ease: 'easeInOut',
            delay: idx * 0.12,
          }}
        >
          {btn}
        </motion.div>
      );
    }
    return (
      <div key={`${card?.id || idx}-${idx}`} className="w-full">
        {btn}
      </div>
    );
  };

  return (
    <div className="space-y-3 pt-4">
      <p className="text-center text-amber-200/90 text-xs flex items-center justify-center gap-1.5">
        <LayoutGrid className="w-3.5 h-3.5 shrink-0 opacity-85" aria-hidden />
        Карты расклада
      </p>
      <p className="text-center text-white/70 text-[12px] leading-snug">Нажмите на карту, чтобы прочитать трактовку по каждой позиции.</p>

      {spreadId === 'financial' && spread.length === 5 ? (
        <div className="mx-auto w-full max-w-[min(25rem,100%)] px-1 pt-1 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {spread.slice(0, 3).map((card, idx) => (
              <div key={`fin-row1-${card?.id || idx}-${idx}`} className="w-full">
                {renderSpreadCardButton(card, idx)}
              </div>
            ))}
          </div>
          <div className="flex justify-center gap-3">
            {spread.slice(3, 5).map((card, rowIdx) => {
              const idx = rowIdx + 3;
              return (
                <div key={`fin-row2-${card?.id || idx}-${idx}`} className="w-[31%] max-w-[7.5rem] min-w-[5.5rem]">
                  {renderSpreadCardButton(card, idx)}
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {spread.map((card, idx) => renderSpreadCardButton(card, idx))}
        </div>
      )}

      <FinalBlock
        overallInterpretation={overallInterpretation}
        overallSummaryShort={overallSummaryShort}
        practicalAdvice={practicalAdvice}
        spreadId={spreadId}
        question={question}
        chatMessages={chatMessages}
        onNewSpread={onNewSpread}
        triggerHaptics={triggerHaptics}
        spreadCards={spread}
        currentPositions={currentPositions}
      />

      <AnimatePresence>
        {activeCard ? (
          <motion.div
            className="fixed inset-0 z-[300] bg-black/50 backdrop-blur-md pt-[max(48px,env(safe-area-inset-top)+40px)] pb-4 px-4 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setActiveIndex(null)}
          >
            <motion.div
              className="w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-white/10 bg-slate-950/50 backdrop-blur-2xl tarot-scrollless"
              initial={{ y: 24, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 24, opacity: 0 }}
              transition={{ duration: 0.25, ease: TAROT_ANIM.SMOOTH_EASE }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="shrink-0 pt-2 px-4 pb-2 border-b border-white/10">
                <p className="text-amber-200 text-sm text-center">
                  {(currentPositions[activeIndex] || activeCard?.position_name || `Позиция ${activeIndex + 1}`)}
                </p>
              </div>
              <div
                className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 space-y-3"
                style={{ WebkitOverflowScrolling: 'touch', paddingBottom: 'max(88px, calc(env(safe-area-inset-bottom) + 72px))' }}
              >
                <div className="mx-auto rounded-2xl overflow-hidden bg-transparent" style={{ width: 180, height: Math.round(180 / TAROT_ASPECT) }}>
                  {activeCard?.image ? (
                    <img
                      src={activeCard.image}
                      alt={getCardDisplayName(activeCard)}
                      className="w-full h-full object-cover rounded-2xl cursor-zoom-in"
                      style={{ transform: activeCard?.is_reversed ? 'rotate(180deg)' : undefined }}
                      onClick={() => setZoomOpen(true)}
                    />
                  ) : (
                    <div className="w-full h-full bg-amber-900/20" />
                  )}
                </div>
                <p className="text-amber-200/95 text-xs text-center mt-2">
                  {getCardDisplayName(activeCard)}
                  {activeCard?.is_reversed ? ' (перевёрнутая)' : ''}
                </p>
                {!activeCard?.loading && formatCardInterpretation(activeCard) ? (
                  <div className="flex justify-center mt-3">
                    <TtsPlayButton text={formatCardInterpretation(activeCard)} />
                  </div>
                ) : null}
                {activeCard?.loading ? (
                  <p className="text-white/75 text-[12px] leading-relaxed text-center mt-2">Идёт анализ карты...</p>
                ) : (
                  <TarotInterpretBody className="mt-2" text={formatCardInterpretation(activeCard)} center />
                )}
                <Button size="md" variant="ghost" className="w-full justify-center mt-6" onClick={() => setActiveIndex(null)}>
                  Закрыть
                </Button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <CardZoomOverlay
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        src={activeCard?.image || ''}
        alt={getCardDisplayName(activeCard)}
      />
    </div>
  );
}

const RESULT_SLIDE_UP_OFFSET = 120;
const RESULT_SLIDE_UP_DURATION = 0.5;
const RESULT_SLIDE_UP_STAGGER = 0.18;

/** Базовый расклад: карты по очереди, свайп снизу вверх (вертикально). Прошлое → Настоящее → Будущее → итог. */
function BasicSpreadResultView({
  spread = [],
  overallInterpretation = '',
  overallSummaryShort = '',
  currentPositions = [],
  onRetry,
  onNewSpread,
  triggerHaptics,
  question,
  chatMessages = [],
}) {
  const cards = spread.slice(0, 3);
  const positionLabels = currentPositions.length >= 3 ? currentPositions : ['Прошлое', 'Настоящее', 'Будущее'];
  const overallText = fixOverallInterpretationTypo(overallInterpretation || '').trim();
  const shortText = fixOverallInterpretationTypo(overallSummaryShort || '').trim();
  const vectorCandidate = shortText || _firstSentence(overallText);
  const isVectorDuplicate =
    Boolean(vectorCandidate && overallText) &&
    _normalizeNarrative(vectorCandidate) === _normalizeNarrative(overallText);
  const mergedSummary = isVectorDuplicate
    ? ''
    : (vectorCandidate || 'Три карты складываются в одну историю: смотрите итог ниже.');

  if (!cards.length) return null;

  return (
    <div className="w-full pb-8 px-2 sm:px-3">
      <div className="mx-auto w-full max-w-[min(100%,100vw-0.5rem)]">
        <SpreadSummaryModalView
          spread={cards}
          currentPositions={positionLabels}
          overallInterpretation={overallInterpretation}
          overallSummaryShort={mergedSummary}
          practicalAdvice=""
          spreadId="three_cards"
          question={question}
          chatMessages={chatMessages}
          onNewSpread={onNewSpread}
          triggerHaptics={triggerHaptics}
        />
      </div>
    </div>
  );
}

function BasicSpreadCardFlip({ card, isActive }) {
  const showFace = Boolean(isActive && !card?.loading && card?.image);
  return (
    <div className="relative w-full h-full overflow-hidden flex items-center justify-center" style={{ borderRadius: '16px' }}>
      {showFace ? (
        <img
          src={card.image}
          alt=""
          className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]"
          style={{ transform: card?.is_reversed ? 'rotate(180deg)' : undefined }}
        />
      ) : card?.backImage ? (
        <img src={card.backImage} alt="" className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]" />
      ) : (
        <div className="w-full h-full bg-amber-900/20" style={{ borderRadius: '16px' }} />
      )}
    </div>
  );
}

function distance(p1, p2) {
  return Math.hypot(p2.clientX - p1.clientX, p2.clientY - p1.clientY);
}

const CARD_HEIGHT = 240;
const SINGLE_CARD_HEIGHT = 306;
const BASIC_CARD_ASPECT = 0.62;

const EASE_SMOOTH = [0.32, 0.72, 0.36, 1]; // плавное ускорение и замедление

const CARD_BORDER_RADIUS = '12px';
const SINGLE_CARD_TOP_GAP = 12;

/** Одна карта: карта сверху, печать текста, иконка TTS после печати, кнопки снизу. */
function SingleCardResultView({
  card,
  onRetry,
  practicalAdvice,
  children,
  cardBoxRef = null,
  suppressCardVisual = false,
  spreadOverallText = '',
}) {
  const [zoomOpen, setZoomOpen] = useState(false);
  const cardWidth = SINGLE_CARD_HEIGHT * TAROT_ASPECT;
  const interpretationText = formatCardInterpretation(card);
  const overallSynth = fixOverallInterpretationTypo(spreadOverallText || '').trim();
  const readingText = (overallSynth || interpretationText || '').trim();
  const hasText = !card?.loading && readingText && readingText !== '-';
  const { displayedText, isComplete } = useTypewriter(readingText, {
    charsPerSec: 38,
    enabled: hasText,
    instant: true,
  });
  const adviceText = practicalAdvice || (hasText ? 'Пусть этот день сложится чуть спокойнее, чем ты боишься. Ты не один на этом пути.' : '');
  const { displayedText: displayedAdvice, isComplete: adviceComplete } = useTypewriter(adviceText, {
    charsPerSec: 40,
    enabled: hasText && isComplete && Boolean(adviceText),
    instant: true,
  });
  const showAdvice = false;
  const allTextComplete = isComplete && (!showAdvice || !adviceText || adviceComplete);

  if (!card) return null;
  return (
    <div className="w-full flex flex-col">
      <div
        className="px-0"
        style={{
          paddingTop: 'max(76px, calc(env(safe-area-inset-top, 0px) + 68px))',
          paddingBottom: 'max(1.25rem, calc(env(safe-area-inset-bottom, 0px) + 0.75rem))',
        }}
      >
        <div style={{ height: '0.5rem' }} aria-hidden />
        <div
          className="flex flex-col items-center"
          style={{
            paddingLeft: '0.25rem',
            paddingRight: '0.25rem',
            paddingTop: `${SINGLE_CARD_TOP_GAP}px`,
          }}
        >
          <motion.div
            ref={cardBoxRef}
            className="relative mx-auto"
            style={{
              width: cardWidth,
              height: SINGLE_CARD_HEIGHT,
              borderRadius: CARD_BORDER_RADIUS,
              perspective: 1200,
              WebkitPerspective: 1200,
              transformOrigin: 'center top',
              transformStyle: 'preserve-3d',
              WebkitTransformStyle: 'preserve-3d',
              overflow: 'visible',
            }}
            initial={false}
            animate={{ y: -2.2, scale: suppressCardVisual ? 0.94 : 1, opacity: suppressCardVisual ? 0 : 1 }}
            transition={{
              y: { duration: 2.8, repeat: Infinity, repeatType: 'mirror', ease: 'easeInOut' },
              scale: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
              opacity: { duration: 0.38, ease: [0.22, 1, 0.36, 1] },
            }}
          >
            <div
              className="relative w-full h-full"
              style={{ borderRadius: CARD_BORDER_RADIUS }}
              onClick={() => {
                if (card?.image) setZoomOpen(true);
              }}
              onTouchStart={(e) => {
                if (e.touches.length >= 2 && card?.image) setZoomOpen(true);
              }}
            >
              <div
                className="absolute inset-0 flex items-center justify-center rounded-[12px] overflow-hidden"
                style={{
                  borderRadius: CARD_BORDER_RADIUS,
                  overflow: 'hidden',
                  backgroundColor: 'transparent',
                }}
              >
                {card.image ? (
                  <img
                    src={card.image}
                    alt={getCardDisplayName(card)}
                    className="max-w-full max-h-full w-auto h-auto object-contain rounded-[12px]"
                    style={{
                      borderRadius: CARD_BORDER_RADIUS,
                      transform: card?.is_reversed ? 'rotate(180deg)' : undefined,
                    }}
                  />
                ) : card.backImage ? (
                  <img src={card.backImage} alt="" className="max-w-full max-h-full w-auto h-auto object-contain rounded-[12px]" style={{ borderRadius: CARD_BORDER_RADIUS }} />
                ) : (
                  <div className="w-full h-full opacity-50" style={{ borderRadius: CARD_BORDER_RADIUS, background: 'radial-gradient(ellipse 70% 60% at 50% 40%, rgba(251,191,36,0.15), transparent 70%)' }} />
                )}
              </div>
            </div>
          </motion.div>
        </div>

        <div className="w-full mx-auto mt-6 px-4" style={{ width: 'min(100%, calc(100vw - 24px))' }}>
          <p className="text-amber-200 font-medium text-base mb-3 text-center">Расклад</p>
          {card.loading ? (
            <div className="flex flex-col items-center justify-center py-2 min-h-[2.5rem]">
              <p className="text-white/75 text-sm text-center">Идёт анализ карты...</p>
            </div>
          ) : hasText ? (
            <>
              <div className="text-center min-h-[2.5rem] rounded-2xl bg-black/30 border border-white/10 backdrop-blur-[1.5px] px-3 py-3">
                <TarotInterpretBody text={displayedText} center withIcons density="high" className="text-[13px]" />
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-2 min-h-[2.5rem]">
              <p className="text-white/40 text-xs text-center">Загрузка текста...</p>
            </div>
          )}
          {onRetry && !card.loading && /звезды молчат|не удалось загрузить/i.test(readingText || '') ? (
            <button type="button" onClick={onRetry} className="mt-3 w-full py-2.5 rounded-xl border border-amber-400/50 bg-amber-400/15 text-amber-200 text-sm font-medium">
              🔄 Повторить
            </button>
          ) : null}
          {showAdvice && !card.loading && hasText && adviceText ? (
            <div className="mt-6 pt-4 border-t border-amber-400/20 text-center">
              <p className="text-amber-200 font-medium text-base mb-2">Пожелание</p>
              <TarotInterpretBody text={displayedAdvice} center />
            </div>
          ) : null}
        </div>

        {allTextComplete ? (
          <div className="w-full mx-auto mt-8 px-4" style={{ width: 'min(100%, calc(100vw - 24px))' }}>
            {children}
          </div>
        ) : null}
        <CardZoomOverlay
          open={zoomOpen}
          onClose={() => setZoomOpen(false)}
          src={card?.image || ''}
          alt={getCardDisplayName(card)}
        />
      </div>
    </div>
  );
}

function SpreadCardsInteractivePanel({ spread = [], currentPositions = [] }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const activeCard = activeIndex != null ? spread[activeIndex] : null;

  if (!Array.isArray(spread) || spread.length === 0) return null;

  return (
    <>
      <Card className="p-4 border-amber-400/30">
        <p className="text-amber-200 text-sm mb-3 flex items-center gap-2">
          <LayoutGrid className="w-4 h-4 shrink-0 opacity-90" aria-hidden />
          Нажмите на карту, чтобы открыть значение
        </p>
        <div className="grid grid-cols-3 gap-2">
          {spread.map((card, index) => (
            <button
              key={`${card?.id || index}-thumb`}
              type="button"
              onClick={() => setActiveIndex(index)}
              className="rounded-xl border border-amber-200/25 bg-black/20 p-1.5"
            >
              <div className="w-full rounded-[12px] overflow-hidden bg-transparent" style={{ aspectRatio: `${500}/${895}` }}>
                {card?.image ? (
                  <img
                    src={card.image}
                    alt={getCardDisplayName(card)}
                    className="w-full h-full object-cover rounded-2xl"
                    style={{ transform: card?.is_reversed ? 'rotate(180deg)' : undefined }}
                  />
                ) : (
                  <div className="w-full h-full rounded-2xl bg-amber-900/25" />
                )}
              </div>
              <p className="mt-1 text-[11px] text-white/80 leading-tight">
                {currentPositions[index] || card?.position_name || `Позиция ${index + 1}`}
              </p>
            </button>
          ))}
        </div>
      </Card>

      <AnimatePresence>
        {activeCard ? (
          <motion.div
            className="fixed inset-0 z-[300] bg-black/50 backdrop-blur-md pt-[max(48px,env(safe-area-inset-top)+40px)] pb-4 px-4 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setActiveIndex(null)}
          >
            <motion.div
              className="w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-white/10 bg-slate-950/50 backdrop-blur-2xl tarot-scrollless"
              initial={{ y: 16, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 16, opacity: 0 }}
              transition={{ duration: 0.25, ease: TAROT_ANIM.SMOOTH_EASE }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="shrink-0 pt-2 px-4 pb-2 border-b border-white/10">
                <p className="text-center text-amber-200 text-sm">
                  {(currentPositions[activeIndex] || activeCard?.position_name || `Позиция ${activeIndex + 1}`)}
                </p>
              </div>
              <div
                className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4"
                style={{ WebkitOverflowScrolling: 'touch', paddingBottom: 'max(88px, calc(env(safe-area-inset-bottom) + 72px))' }}
              >
                <div className="mx-auto rounded-2xl overflow-hidden bg-transparent" style={{ width: 160, height: Math.round(160 / TAROT_ASPECT) }}>
                  {activeCard?.image ? (
                    <img
                      src={activeCard.image}
                      alt={getCardDisplayName(activeCard)}
                      className="w-full h-full object-cover rounded-2xl"
                      style={{ transform: activeCard?.is_reversed ? 'rotate(180deg)' : undefined }}
                    />
                  ) : (
                    <div className="w-full h-full rounded-2xl bg-amber-900/25" />
                  )}
                </div>
                <p className="mt-2 text-amber-200/95 text-xs text-center">
                  {getCardDisplayName(activeCard)}
                  {activeCard?.is_reversed ? ' (перевёрнутая)' : ''}
                </p>
                {!activeCard?.loading && formatCardInterpretation(activeCard) ? (
                  <div className="flex justify-center mt-3">
                    <TtsPlayButton text={formatCardInterpretation(activeCard)} />
                  </div>
                ) : null}
                {activeCard?.loading ? (
                  <p className="mt-3 text-white/75 text-[12px] leading-relaxed">Идёт анализ карты...</p>
                ) : (
                  <TarotInterpretBody className="mt-3" text={formatCardInterpretation(activeCard)} />
                )}
                <Button size="md" className="w-full justify-center mt-6" onClick={() => setActiveIndex(null)}>
                  Закрыть
                </Button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}

function ResultCardScroll({ card, positionName, onRetry, highlightFinancialFinal = false, isCelticCrossCard = false }) {
  const cardRef = useRef(null);
  const [pinchScale, setPinchScale] = useState(1);
  const [cardAspect, setCardAspect] = useState(TAROT_ASPECT);
  const [revealed, setRevealed] = useState(Boolean(card?.image));
  const revealLockedRef = useRef(Boolean(card?.image));
  const cardIdentityRef = useRef('');
  const [zoomOpen, setZoomOpen] = useState(false);
  const pinchRef = useRef({ initialDistance: 0, baseScale: 1 });
  const scaleRef = useRef(1);
  scaleRef.current = pinchScale;

  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const onTouchStart = (e) => {
      if (e.touches.length === 2) {
        pinchRef.current.initialDistance = distance(e.touches[0], e.touches[1]);
        pinchRef.current.baseScale = scaleRef.current;
      }
    };
    const onTouchMove = (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const d = distance(e.touches[0], e.touches[1]);
        const base = pinchRef.current.baseScale;
        const init = pinchRef.current.initialDistance;
        const scale = Math.min(3, Math.max(1, (base * d) / init));
        setPinchScale(scale);
      }
    };
    const onTouchEnd = (e) => {
      if (e.touches.length < 2) {
        setPinchScale(1);
        pinchRef.current = { initialDistance: 0, baseScale: 1 };
      }
    };
    el.addEventListener('touchstart', onTouchStart, { passive: true });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: true });
    el.addEventListener('touchcancel', onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
      el.removeEventListener('touchcancel', onTouchEnd);
    };
  }, []);

  useEffect(() => {
    const identity = String(card?.id || card?.card_id || '');
    if (identity && identity !== cardIdentityRef.current) {
      cardIdentityRef.current = identity;
      revealLockedRef.current = Boolean(card?.image);
      setRevealed(Boolean(card?.image));
    }
    // If face image became available once, lock reveal for this card instance.
    if (card?.image) {
      revealLockedRef.current = true;
      setRevealed(true);
      return;
    }
    if (card?.loading) {
      if (!revealLockedRef.current) setRevealed(false);
      return;
    }
    if (revealLockedRef.current) {
      setRevealed(true);
      return;
    }
    const t = setTimeout(() => setRevealed(true), 90);
    return () => clearTimeout(t);
  }, [card?.loading, card?.id, card?.image]);

  const cardWidth = CARD_HEIGHT * cardAspect;
  const renderCardWidth = isCelticCrossCard ? CARD_HEIGHT : cardWidth;
  const renderCardHeight = isCelticCrossCard ? CARD_HEIGHT * TAROT_ASPECT : CARD_HEIGHT;
  const maxZoomW = 320;
  const maxZoomH = Math.round(maxZoomW / TAROT_ASPECT);
  const zoomOverlay = pinchScale > 1 && typeof document !== 'undefined' && createPortal(
    <div
      className="fixed inset-0 z-[99999] flex items-center justify-center bg-black/80"
      onClick={() => setPinchScale(1)}
      style={{ touchAction: 'none' }}
    >
      <motion.div
        className="rounded-[12px] shadow-2xl overflow-hidden"
        style={{
          width: Math.min(renderCardWidth * pinchScale, maxZoomW),
          height: Math.min(renderCardHeight * pinchScale, maxZoomH),
          touchAction: 'none',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {card?.image ? (
          <img
            src={card.image}
            alt={card.name}
            className="w-full h-full object-cover rounded-2xl"
          />
        ) : (
          <div className="w-full h-full bg-amber-900/30" />
        )}
      </motion.div>
    </div>,
    document.body
  );

  if (!card) return null;
  return (
    <motion.div
      className="flex flex-col pt-24 pb-12 min-h-[70vh] justify-center relative overflow-visible"
      style={{ scrollMarginTop: 'max(148px, calc(80px + env(safe-area-inset-top, 0px)))' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {zoomOverlay}
      {positionName ? <p className="text-center text-amber-200 text-xs mb-4">{positionName}</p> : null}
      {card?.is_reversed ? (
        <p className="text-center text-amber-300/85 text-xs mb-2">↻ Карта выпала перевёрнутой</p>
      ) : null}
      <motion.div
        ref={cardRef}
        className={cn(
          'relative mx-auto rounded-[12px] [transform-style:preserve-3d] select-none tarot-shimmer z-10 overflow-hidden',
          highlightFinancialFinal && 'ring-1 ring-emerald-400/20'
        )}
        style={{
          touchAction: 'none',
          width: renderCardWidth,
          height: renderCardHeight,
        }}
        initial={{ y: 80, opacity: 0.6 }}
        onClick={() => {
          if (card?.image) setZoomOpen(true);
        }}
        animate={
          highlightFinancialFinal
            ? {
              y: [0, -12],
              opacity: 1,
              boxShadow: [
                '0 0 0px rgba(16,185,129,0)',
                '0 0 28px rgba(16,185,129,0.45)',
                '0 0 8px rgba(16,185,129,0.15)',
              ],
            }
            : card?.loading
              ? { y: [0, -12], opacity: 1 }
              : { y: [0, -8], opacity: 1 }
        }
        transition={
          highlightFinancialFinal
            ? {
              y: { duration: 2.1, repeat: Infinity, repeatType: 'mirror', ease: 'easeInOut', delay: 0.4 },
              opacity: { duration: 0.5 },
              boxShadow: { duration: 1.8, repeat: Infinity, ease: 'easeInOut' },
            }
            : card?.loading
              ? {
                y: { duration: 1.9, repeat: Infinity, repeatType: 'mirror', ease: 'easeInOut', delay: 0.1 },
                opacity: { duration: 0.5 },
              }
              : { y: { duration: 2.5, repeat: Infinity, repeatType: 'mirror', ease: 'easeInOut', delay: 0.6 }, opacity: { duration: 0.6 } }
        }
      >
        <div className="pointer-events-none absolute -inset-2 rounded-[12px] [transform:translateZ(-12px)] opacity-35" style={{ background: 'radial-gradient(circle at 50% 30%, rgba(255,255,255,0.22), rgba(0,0,0,0))' }} />
        <motion.div
          className="absolute inset-0 rounded-[12px] [transform-style:preserve-3d] overflow-hidden"
          style={{ transformOrigin: 'center center', perspective: 1200 }}
          initial={{ rotateY: revealed ? 360 : 180, rotateZ: 0, scale: 1, y: 0 }}
          animate={{
            rotateY: revealed ? 360 : 180,
            rotateZ: (revealed && card?.is_reversed ? 180 : 0),
            y: revealed ? [-4, 0] : [0, -4, 0],
            scale: pinchScale > 1 ? 1 : pinchScale,
          }}
          transition={{
            rotateY: {
              duration: revealed ? 0.72 : 0.35,
              ease: [0.22, 1, 0.36, 1],
            },
            rotateZ: {
              duration: 0.55,
              ease: [0.22, 1, 0.36, 1],
            },
            y: {
              duration: revealed ? 0.45 : 1.6,
              repeat: revealed ? 0 : Infinity,
              ease: 'easeInOut',
            },
            scale: { duration: pinchScale === 1 ? 0.35 : 0.05, ease: [0.22, 1, 0.36, 1] },
          }}
        >
          <div className="tarot-face tarot-face--back absolute inset-0 rounded-[12px] overflow-hidden bg-transparent">
            <div className="tarot-back-wrap h-full w-full flex items-center justify-center">
              {card.backImage ? (
                <img
                  src={card.backImage}
                  alt=""
                  className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]"
                  onLoad={(e) => {
                    const { naturalWidth, naturalHeight } = e.target;
                    if (naturalWidth && naturalHeight) setCardAspect(naturalWidth / naturalHeight);
                  }}
                />
              ) : (
                <div className="absolute inset-0 min-h-full min-w-full rounded-[12px]" style={{ backgroundColor: 'rgba(8,8,22,0.98)', backgroundImage: 'radial-gradient(ellipse 80% 70% at 50% 20%, rgba(251,191,36,0.35), transparent 50%), linear-gradient(180deg, rgba(15,12,35,0.98) 0%, rgba(6,5,18,0.99) 100%)' }} />
              )}
            </div>
          </div>
          <div className="tarot-face tarot-face--front absolute inset-0 rounded-[12px] overflow-hidden shadow-2xl bg-transparent flex items-center justify-center">
            {/* Лицевая сторона: только лицо карты (card.image). Рубашку сюда не подставлять. */}
            {card.image ? (
                <img
                  src={card.image}
                  alt={card.name}
                  className="max-h-full max-w-full w-auto h-auto object-contain rounded-[12px]"
                  onLoad={(e) => {
                    const { naturalWidth, naturalHeight } = e.target;
                    if (naturalWidth && naturalHeight) setCardAspect(naturalWidth / naturalHeight);
                  }}
                />
              ) : (
                <div className="h-full w-full rounded-[12px] bg-slate-900/80" />
              )}
          </div>
        </motion.div>
      </motion.div>
      <CardZoomOverlay
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        src={card?.image || ''}
        alt={getCardDisplayName(card)}
      />
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <Card className="mt-10 p-4 w-full max-w-[min(100%,100vw-0.75rem)] mx-auto relative z-0">
          {card.loading ? (
            <div className="flex flex-col items-center justify-center py-1">
              <p className="text-white/80 text-[12px] leading-relaxed text-center">Читаю энергию карты</p>
            </div>
          ) : (
            <>
              {formatCardInterpretation(card) && formatCardInterpretation(card) !== '-' ? (
                <div className="flex justify-center mb-3">
                  <TtsPlayButton text={formatCardInterpretation(card)} />
                </div>
              ) : null}
              <TarotInterpretBody text={formatCardInterpretation(card)} />
            </>
          )}
          {onRetry && !card.loading && /звезды молчат|не удалось загрузить/i.test(formatCardInterpretation(card) || '') ? (
            <button
              type="button"
              onClick={onRetry}
              className="mt-3 w-full py-2.5 rounded-xl border border-amber-400/50 bg-amber-400/15 text-amber-200 text-sm font-medium hover:bg-amber-400/25 transition-colors"
            >
              🔄 Повторить
            </button>
          ) : null}
        </Card>
      </motion.div>
    </motion.div>
  );
}

function SpreadCardsOverview({ spread = [], currentPositions = [] }) {
  const [activeIdx, setActiveIdx] = useState(null);
  const [zoomOpen, setZoomOpen] = useState(false);
  const activeCard = activeIdx != null ? spread[activeIdx] : null;
  if (!Array.isArray(spread) || spread.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 py-1 px-0.5">
        {spread.map((card, index) => (
          <button
            key={`${card?.id || index}-thumb`}
            type="button"
            onClick={() => setActiveIdx(index)}
            className="w-full rounded-[12px] overflow-hidden bg-transparent"
          >
            <div className="w-full h-[128px]">
              {card?.image ? (
                <img
                  src={card.image}
                  alt={getCardDisplayName(card)}
                  className="w-full h-full object-cover rounded-2xl"
                  style={{ transform: card?.is_reversed ? 'rotate(180deg)' : undefined }}
                />
              ) : card?.backImage ? (
                <img src={card.backImage} alt="" className="w-full h-full object-cover rounded-2xl" />
              ) : (
                <div className="w-full h-full rounded-2xl bg-amber-900/30" />
              )}
            </div>
            <p className="text-[11px] text-amber-200/85 py-1 px-1 truncate">
              {currentPositions[index] || `Позиция ${index + 1}`}
            </p>
          </button>
        ))}
      </div>
      <p className="text-center text-white/60 text-xs">Нажмите на карту для детального значения</p>

      <AnimatePresence>
        {activeCard ? (
          <motion.div
            className="fixed inset-0 z-[300] bg-black/50 backdrop-blur-md p-4 flex items-center justify-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setActiveIdx(null)}
          >
            <motion.div
              className="w-full max-w-md max-h-[85vh] flex flex-col rounded-2xl border border-white/10 bg-slate-950/50 backdrop-blur-2xl tarot-scrollless"
              initial={{ y: 20, opacity: 0, scale: 0.98 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 20, opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.28, ease: TAROT_ANIM.SMOOTH_EASE }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="shrink-0 pt-2 px-4 pb-2 border-b border-white/10">
                <p className="text-amber-200 text-sm text-center">{currentPositions[activeIdx] || `Позиция ${activeIdx + 1}`}</p>
              </div>
              <div
                className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4"
                style={{ WebkitOverflowScrolling: 'touch', paddingBottom: 'max(88px, calc(env(safe-area-inset-bottom) + 72px))' }}
              >
                <div className="mx-auto mb-3 rounded-2xl overflow-hidden bg-transparent" style={{ width: 160, height: Math.round(160 / TAROT_ASPECT) }}>
                  {activeCard?.image ? (
                    <img
                      src={activeCard.image}
                      alt={getCardDisplayName(activeCard)}
                      className="w-full h-full object-cover rounded-2xl cursor-zoom-in"
                      style={{ transform: activeCard?.is_reversed ? 'rotate(180deg)' : undefined }}
                      onClick={() => setZoomOpen(true)}
                    />
                  ) : activeCard?.backImage ? (
                    <img src={activeCard.backImage} alt="" className="w-full h-full object-cover rounded-2xl" />
                  ) : (
                    <div className="w-full h-full rounded-2xl bg-amber-900/30" />
                  )}
                </div>
                <p className="text-amber-200/95 text-xs text-center mb-1">
                  {getCardDisplayName(activeCard)}
                  {activeCard?.is_reversed ? ' (перевёрнутая)' : ''}
                </p>
                {formatCardInterpretation(activeCard, 'Загрузка...') && !/загрузка|-/i.test(formatCardInterpretation(activeCard, 'Загрузка...')) ? (
                  <div className="flex justify-center mb-3">
                    <TtsPlayButton text={formatCardInterpretation(activeCard, 'Загрузка...')} />
                  </div>
                ) : null}
                {/^загрузка|^-$/i.test((formatCardInterpretation(activeCard, 'Загрузка...') || '').trim()) ? (
                  <p className="text-white/75 text-[12px] leading-relaxed text-center">
                    {formatCardInterpretation(activeCard, 'Загрузка...')}
                  </p>
                ) : (
                  <TarotInterpretBody text={formatCardInterpretation(activeCard, 'Загрузка...')} center />
                )}
                <button
                  type="button"
                  onClick={() => setActiveIdx(null)}
                  className="mt-6 w-full rounded-xl border border-amber-300/40 py-2 text-amber-200 text-sm"
                >
                  Закрыть
                </button>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <CardZoomOverlay
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        src={activeCard?.image || ''}
        alt={getCardDisplayName(activeCard)}
      />
    </div>
  );
}

function FinalBlock({
  overallInterpretation,
  overallSummaryShort,
  practicalAdvice,
  spreadId,
  question,
  chatMessages = [],
  onNewSpread,
  triggerHaptics,
  spreadCards = [],
  currentPositions = [],
}) {
  const [shareSending, setShareSending] = useState(false);
  const overallText = fixOverallInterpretationTypo(overallInterpretation || '').trim();
  const singleCardReadingForShare =
    spreadId === 'single' && spreadCards?.[0]
      ? (overallText || fixOverallInterpretationTypo(formatCardInterpretation(spreadCards[0]) || '').trim()).trim()
      : '';
  const shortText = fixOverallInterpretationTypo(overallSummaryShort || '').trim();
  const showShortSummary = Boolean(
    shortText &&
    spreadId !== 'single' &&
    !_isSameNarrative(shortText, overallText)
  );
  return (
    <motion.div
      className={cn(
        'flex flex-col gap-6',
        spreadId === 'financial'
          ? 'py-6 pb-8 min-h-0'
          : spreadId === 'single'
            ? 'py-4 pb-8 min-h-0'
            : 'py-8 pb-8 min-h-0'
      )}
      initial={{ opacity: 0, y: 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      {spreadId !== 'single' ? (
        overallText ? (
          spreadId === 'six_cards' ? (
            <div className="w-full max-w-none mx-0 rounded-2xl bg-black/35 backdrop-blur-sm px-3 sm:px-4 py-4 flex flex-col items-center text-center">
              <TtsPlayButton text={showShortSummary ? `${shortText}. ${overallText}` : overallText} className="mb-3" />
              {showShortSummary ? (
                <TarotInterpretBody muted className="mb-3 text-center" text={shortText} center />
              ) : null}
              <p className="text-amber-300 font-serif text-lg mb-2 flex items-center justify-center gap-2">
                <ScrollText className="w-5 h-5 shrink-0 opacity-90 text-amber-200/90" aria-hidden />
                Итог расклада
              </p>
              <TarotInterpretBody text={overallText} center />
            </div>
          ) : spreadId === 'financial' ? (
            null
          ) : (
            <Card className="w-full max-w-none mx-0 px-3 sm:px-4 py-5 border-amber-500/30 text-center">
              <div className="flex justify-center mb-3">
                <TtsPlayButton text={showShortSummary ? `${shortText}. ${overallText}` : overallText} />
              </div>
              {showShortSummary ? (
                <TarotInterpretBody muted className="mb-3 text-center" text={shortText} center />
              ) : null}
              <p className="text-amber-300 font-serif text-lg mb-2 flex items-center justify-center gap-2">
                <ScrollText className="w-5 h-5 shrink-0 opacity-90 text-amber-200/90" aria-hidden />
                Итог расклада
              </p>
              <TarotInterpretBody text={overallText} center />
            </Card>
          )
        ) : (
          <p className="text-white/60 text-[12px] text-center">Загружаю итог...</p>
        )
      ) : null}
      {practicalAdvice && spreadId !== 'financial' && spreadId !== 'three_cards' && spreadId !== 'single' ? (
        spreadId === 'six_cards' ? (
          <div className="pt-6 border-t border-amber-400/20 text-center">
            <p className="text-amber-200 font-medium text-xs mb-2 flex items-center justify-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 shrink-0 opacity-90" aria-hidden />
              Совет
            </p>
            <TarotInterpretBody text={practicalAdvice} center />
          </div>
        ) : (
          <Card className="w-full max-w-none mx-0 px-3 sm:px-4 py-5 border-amber-500/25 text-center">
            <p className="text-amber-200 font-medium text-xs mb-2 flex items-center justify-center gap-1.5">
              <Lightbulb className="w-3.5 h-3.5 shrink-0 opacity-90" aria-hidden />
              Совет
            </p>
            <TarotInterpretBody text={practicalAdvice} center />
          </Card>
        )
      ) : null}
      {spreadId === 'financial' ? (
        <Card className="w-full max-w-none mx-0 px-3 sm:px-4 py-5 border-amber-500/30 bg-black/35 text-center">
          <div className="flex justify-center mb-3">
            <TtsPlayButton
              text={[showShortSummary && shortText, overallText || '-', (practicalAdvice || '').trim()]
                .filter(Boolean)
                .join('\n\n')}
            />
          </div>
          {showShortSummary ? (
            <TarotInterpretBody muted className="mb-3 text-center" text={shortText} center />
          ) : null}
          <p className="text-amber-300 font-serif text-lg mb-2 flex items-center justify-center gap-2">
            <ScrollText className="w-5 h-5 shrink-0 opacity-90 text-amber-200/90" aria-hidden />
            Итог расклада
          </p>
          <TarotInterpretBody text={overallText || '-'} center />
          {(practicalAdvice || '').trim() ? (
            <TarotInterpretBody muted className="mt-3 text-center" text={(practicalAdvice || '').trim()} center />
          ) : null}
        </Card>
      ) : null}
      <div
        className="flex flex-col gap-3 pt-4 w-full"
        style={spreadId === 'single' ? { paddingBottom: 'max(2.75rem, calc(env(safe-area-inset-bottom, 0px) + 2rem))' } : undefined}
      >
        {spreadCards?.length > 0 &&
        !spreadCards.some((c) => c?.loading) &&
        (spreadId === 'single' ? singleCardReadingForShare : overallText) ? (
          <>
            <motion.button
              type="button"
              disabled={shareSending}
              onClick={async () => {
                if (shareSending) return;
                setShareSending(true);
                try {
                  const initData = window?.Telegram?.WebApp?.initData || '';
                  const cardsPayload = spreadCards.map((c, idx) => ({
                    position_name: c?.position_name || currentPositions[idx] || `Позиция ${idx + 1}`,
                    name: getCardNameRu(c?.id, c?.astrovDeckId) || c?.card_name || c?.name || 'Карта',
                    meaning:
                      spreadId === 'single' && idx === 0
                        ? (overallText || c?.meaning || c?.interpretation || '').trim()
                        : (c?.meaning || c?.interpretation || ''),
                    image: c?.image ? (c.image.startsWith('http') ? c.image : `${ABS_BASE}/${c.image.replace(/^\//, '')}`) : '',
                    is_reversed: typeof c?.is_reversed === 'boolean' ? c.is_reversed : null,
                  }));
                  const res = await fetch(`${API_BASE}/api/tarot/share`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      init_data: initData,
                      question: question || '',
                      overall: spreadId === 'single' ? '' : overallText,
                      spread_id: spreadId || '',
                      cards: cardsPayload,
                      chat_transcript: formatTarotChatTranscript(chatMessages),
                      practical_advice: (practicalAdvice || '').trim(),
                    }),
                  });
                  const data = res.ok ? await res.json() : {};
                  if (!data.ok) throw new Error(data.message || 'Не удалось отправить.');
                  triggerHaptics?.('medium');
                  window?.Telegram?.WebApp?.showPopup?.({
                    title: 'Готово',
                    message: 'Расклад отправлен в личку бота. Перешлите сообщение в нужный чат, чтобы поделиться.',
                  });
                } catch (e) {
                  window?.Telegram?.WebApp?.showPopup?.({
                    title: 'Ошибка',
                    message: e?.message || 'Не удалось отправить.',
                  });
                } finally {
                  setShareSending(false);
                }
              }}
              className={TAROT_MAIN_CTA_CLASS}
              style={TAROT_SHARE_CTA_STYLE}
            >
              {shareSending ? 'Отправка...' : 'Поделиться раскладом'}
            </motion.button>
          </>
        ) : null}
        <motion.button
          type="button"
          onClick={onNewSpread}
          className={TAROT_GHOST_CTA_CLASS}
        >
          ↩ Вернуться к началу Таро
        </motion.button>
      </div>
    </motion.div>
  );
}

function TarotChat({
  enabled,
  defaultExpanded = false,
  readingId,
  quickQuestions = [],
  onSend,
  chatMessages,
  loading,
  guidedMode = false,
  guidedStep = 0,
  guidedTotal = 0,
  guidedOptions = [],
  guidedOnly = false,
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [text, setText] = useState('');
  const composerRef = useRef(null);
  const messagesRef = useRef(null);
  if (!enabled) return null;
  const showCollapse = !guidedOnly;
  const isExpanded = guidedOnly || expanded;
  useEffect(() => {
    const el = messagesRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [chatMessages, guidedStep, guidedMode]);
  return (
    <Card
      className={cn(
        'p-4 space-y-3 border-amber-400/25 bg-[linear-gradient(180deg,rgba(20,12,28,0.78),rgba(10,8,20,0.62))] backdrop-blur-sm',
        isExpanded && 'pb-[max(6.5rem,calc(env(safe-area-inset-bottom,0px)+5rem))]'
      )}
    >
      {showCollapse ? (
        <button
          type="button"
          className="w-full text-left text-amber-200 text-sm"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Скрыть диалог' : 'Открыть диалог с тарологом'}
        </button>
      ) : null}
      {isExpanded ? (
        <>
          {guidedMode ? (
            <p className="text-[11px] text-amber-200/80">
              Уточнение перед итогом: {Math.min(guidedStep + 1, Math.max(guidedTotal, 1))}/{Math.max(guidedTotal, 1)}
            </p>
          ) : null}
          <div ref={messagesRef} className="max-h-72 overflow-y-auto space-y-2 pr-0.5">
            {(chatMessages || []).length === 0 ? (
              <p className="text-white/60 text-xs">{guidedOnly ? 'Ответьте на уточняющие запросы ниже.' : 'Можно задать уточняющий запрос по раскладу.'}</p>
            ) : (
              (chatMessages || []).map((m, i) => {
                const isShortStep = guidedOnly && m.role === 'assistant' && (/\/\d+:\s*\n/.test(m.content || '') || m.content?.includes('Итог расклада готов') || m.content?.includes('Спасибо. Учитываю'));
                const showContent = guidedOnly && m.role === 'assistant' && m.content && m.content.length > 180 && !isShortStep
                  ? 'Итог расклада готов. Смотрите блок «Итоговый расклад» выше.'
                  : m.content;
                return (
                  <div
                    key={`${m.role}-${i}`}
                    className={cn(
                      'rounded-xl px-3 py-2 text-xs',
                      m.role === 'user' ? 'bg-amber-400/15 text-amber-100' : 'bg-white/5 text-white/85'
                    )}
                  >
                    {showContent}
                  </div>
                );
              })
            )}
          </div>
          {quickQuestions?.length && !guidedMode ? (
            <div className="w-full flex flex-wrap gap-2 justify-start items-start self-start text-left">
              {quickQuestions.slice(0, 3).map((q) => (
                <button
                  key={q}
                  type="button"
                  className="rounded-full border border-white/20 px-3 py-1 text-[11px] text-white/80"
                  onClick={async () => {
                    if (loading) return;
                    await onSend?.(q);
                  }}
                >
                  {q}
                </button>
              ))}
            </div>
          ) : null}
          <div
            className={cn(
              'space-y-2 rounded-xl p-1.5',
              guidedOnly ? 'relative bottom-auto' : 'sticky bottom-[max(74px,calc(env(safe-area-inset-bottom)+56px))]',
              !guidedOnly && 'bg-amber-900/20 backdrop-blur-sm'
            )}
            ref={composerRef}
          >
            {guidedMode && guidedOptions.length >= 2 ? (
              <div className="grid grid-cols-3 gap-2">
                {guidedOptions.map((option) => (
                  <Button
                    key={option}
                    size="md"
                    variant="ghost"
                    className="w-full justify-center border border-amber-400/30 text-amber-200 hover:bg-amber-400/10"
                    disabled={loading}
                    onClick={async () => {
                      await onSend?.(option);
                    }}
                  >
                    {option}
                  </Button>
                ))}
              </div>
            ) : guidedOnly ? null : (
              <>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onFocus={() => {
                    requestAnimationFrame(() => {
                      composerRef.current?.scrollIntoView({ behavior: 'auto', block: 'nearest' });
                    });
                  }}
                  placeholder="Ваш запрос по раскладу..."
                  className="w-full min-h-[70px] rounded-xl border border-amber-200/20 bg-black/25 p-2 text-xs text-white"
                />
                <Button
                  size="md"
                  className="w-full justify-center"
                  disabled={loading || !text.trim()}
                  onClick={async () => {
                    const msg = text.trim();
                    if (!msg) return;
                    setText('');
                    await onSend?.(msg);
                  }}
                >
                  {loading ? 'Отвечаю...' : 'Отправить'}
                </Button>
              </>
            )}
          </div>
        </>
      ) : null}
    </Card>
  );
}

function TarotStatsPanel({ stats, onClose }) {
  const pieData = [
    { name: 'Прямые', value: stats?.reversed_ratio?.upright || 0 },
    { name: 'Перевёрнутые', value: stats?.reversed_ratio?.reversed || 0 },
  ];
  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 p-3 pb-24 pt-[max(96px,calc(env(safe-area-inset-top)+64px))] overflow-y-auto flex items-start justify-center"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: 30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="w-full max-w-xl max-h-[calc(100dvh-170px)] overflow-y-auto rounded-3xl border border-white/10 bg-[#0b0b1e] p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-white/85 text-sm">Статистика Таро</p>
        <Card className="p-3 text-sm text-white/80">
          Всего раскладов: <span className="text-amber-200">{stats?.total_readings || 0}</span>
        </Card>
        <Card className="p-3 h-52">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={72}>
                <Cell fill="#fcd34d" />
                <Cell fill="#f97316" />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </Card>
        <Card className="p-3 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stats?.top_cards || []}>
              <XAxis dataKey="card_id" hide />
              <YAxis />
              <Tooltip />
              <Bar dataKey="count" fill="#fbbf24" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Button size="md" variant="ghost" className="w-full justify-center" onClick={onClose}>
          Закрыть
        </Button>
      </motion.div>
    </div>
  );
}

const ARCANA = [
  'The Fool', 'The Magician', 'The High Priestess', 'The Empress', 'The Emperor',
  'The Hierophant', 'The Lovers', 'The Chariot', 'Strength', 'The Hermit',
  'Wheel of Fortune', 'Justice', 'The Hanged Man', 'Death', 'Temperance',
  'The Devil', 'The Tower', 'The Star', 'The Moon', 'The Sun',
  'Judgement', 'The World',
];

const arcanaDeck = ARCANA.map((name, index) => ({
  id: index + 1,
  name,
  meaning:
    'Карта открывает глубинный смысл происходящего. Сейчас важно довериться интуиции и принять знак.',
}));

function useTarot() {
  const [spread, setSpread] = useState([]);
  const [activeDeckId, setActiveDeckId] = useState('rider_waite');

  const reset = () => {
    setSpread([]);
  };

  return {
    spread,
    setSpread,
    reset,
    activeDeckId,
    setActiveDeckId,
  };
}

export default function Tarot() {
  const { activeUser } = useProfile();
  const { status, limits, authLoaded, refetchAuth } = useAuth();
  const { pushBottomNavSuppression, popBottomNavSuppression } = useChromeLayout();
  const isPaidAccess = status === 'full_access' || status === 'trial' || Boolean(limits?.is_paid);
  const isPaidAccessRef = useRef(isPaidAccess);
  const tarotPriceCents = Math.max(0, Number(limits?.tarot?.price_cents ?? 1000));
  const tarotPriceRub = Math.max(0, Math.floor((limits?.tarot?.price_cents ?? 1000) / 100));
  const tarotBalanceCents = Math.max(0, Number(limits?.balance_cents ?? 0));
  const { session, startSession, updateSession, finishSession, clearSession } = useTarotSession();
  const {
    spread,
    setSpread,
    reset,
    activeDeckId,
    setActiveDeckId,
  } = useTarot();
  const fan = useMemo(() => [-26, -16, -6, 6, 16, 26, 36], []);
  const { decks: decksFromLoader, resolveCardImage } = useTarotDecks(tarotDecks);
  const decksBase = decksFromLoader.filter((d) => d.id !== 'hermetic');
  const [selectedSpreadId, setSelectedSpreadId] = useState('single');
  const decks = useMemo(() => {
    const recIds = getSpreadHint(selectedSpreadId)?.recommendedDeckIds || [];
    if (!recIds.length) return decksBase;
    const recommended = recIds.map((id) => decksBase.find((d) => d.id === id)).filter(Boolean);
    const rest = decksBase.filter((d) => !recIds.includes(d.id));
    return [...recommended, ...rest];
  }, [decksBase, selectedSpreadId]);
  const activeDeck = decks.find((d) => d.id === activeDeckId) || decks[0] || EMPTY_TAROT_DECK;
  const cardPool = activeDeck.cards?.length ? activeDeck.cards : [];
  const deckView = cardPool.slice(0, fan.length);
  const [question, setQuestion] = useState('');
  const [resultQuestion, setResultQuestion] = useState('');
  /** Синхронная копия для API: в snapshot сессии иногда попадал старый question до flush setState. */
  const questionRef = useRef('');
  const [spreadSize, setSpreadSize] = useState(1);
  const [isDrawing, setIsDrawing] = useState(false);
  const [overallInterpretation, setOverallInterpretation] = useState('');
  const [tarotSummaryShort, setTarotSummaryShort] = useState('');
  const [practicalAdvice, setPracticalAdvice] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [liveTranscript, setLiveTranscript] = useState('');
  const [speechSupported, setSpeechSupported] = useState(false);
  const [speechError, setSpeechError] = useState('');
  const [phase, setPhase] = useState('select'); // 'select' | 'chat' | 'animating' | 'analyzing' | 'result'
  const [tarotStep, setTarotStep] = useState('spread'); // 'spread' | 'deck' (только когда phase === 'select')
  const [animatingSubPhase, setAnimatingSubPhase] = useState('deck'); // 'deck' | 'flyRight' | 'flyLeft' | 'spreading' | 'picking' | 'deckExiting' | 'formation' | 'hang' | 'defocus' | 'uniteFlip' | 'cinematic'
  const [spreadFailed, setSpreadFailed] = useState(false);
  const [shuffledDeckForPick, setShuffledDeckForPick] = useState([]);
  const [pickedIndices, setPickedIndices] = useState(() => new Set());
  const [cinematicCards, setCinematicCards] = useState([]);
  const pickedIndicesRef = useRef(new Set());
  const pickedCardsByIndexRef = useRef(new Map());
  const [showAnalysisCue, setShowAnalysisCue] = useState(false);
  const [questionError, setQuestionError] = useState('');
  const [allowReversed, setAllowReversed] = useState(true);
  const [readingId, setReadingId] = useState('');
  const [followUpQuestions, setFollowUpQuestions] = useState([]);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [dialogueRequired, setDialogueRequired] = useState(false);
  const [guidedQuestions, setGuidedQuestions] = useState([]);
  const [guidedStep, setGuidedStep] = useState(0);
  const [guidedAnswers, setGuidedAnswers] = useState([]);
  const [guidedFinished, setGuidedFinished] = useState(true);
  const [showFinalSummary, setShowFinalSummary] = useState(true);
  const [showStats, setShowStats] = useState(false);
  const [tarologistMessages, setTarologistMessages] = useState([]);
  const [tarologistInput, setTarologistInput] = useState('');
  const [tarologistLoading, setTarologistLoading] = useState(false);
  const [tarologistPromptStage, setTarologistPromptStage] = useState(false);
  const [tarologistPromptVariant, setTarologistPromptVariant] = useState(0);
  const [statsData, setStatsData] = useState(null);
  const [showAccessModal, setShowAccessModal] = useState(false);
  const [accessModalMessage, setAccessModalMessage] = useState('');
  const [accessModalDismissed, setAccessModalDismissed] = useState(false);
  const [showMagicBall, setShowMagicBall] = useState(false);
  const [showTarotCostModal, setShowTarotCostModal] = useState(false);
  const pendingDeckForCostModalRef = useRef(null);
  const pendingTarotRunRef = useRef(null);
  const skipSingleCostGateRef = useRef(false);
  const singleCardDailyFreeRef = useRef(false);
  const [viewportWidth, setViewportWidth] = useState(() => (
    typeof window !== 'undefined' ? window.innerWidth : 390
  ));
  const [questionInputFocused, setQuestionInputFocused] = useState(false);
  const [spreadImgBroken, setSpreadImgBroken] = useState({});
  const [waitingFact, setWaitingFact] = useState('');
  const isMountedRef = useRef(true);
  const lastAppliedSessionTsRef = useRef(0);
  const questionBlockRef = useRef(null);
  const resultScrollRef = useRef(null);
  const animatingStartedRef = useRef(false);
  const basicPrePickedRef = useRef(null); // для базового расклада: [i0, i1, i2] - карты уже выбраны и API запущен
  const [cinematicRunId, setCinematicRunId] = useState(0); // ключ перемонтирования: каждый новый расклад - новая сцена, анимация влета и флипа с нуля
  const recognitionRef = useRef(null);
  const recordingBaseRef = useRef('');
  const recordingCommittedRef = useRef('');
  const silenceTimeoutRef = useRef(null);
  const creatingReadingPromiseRef = useRef(null);
  const guidedStepLockRef = useRef(false);
  const drawRequestIdRef = useRef(0);
  const chatRequestIdRef = useRef(0);
  const vantaRef = useRef(null);
  const vantaEffectRef = useRef(null);
  const waitingFactTypingEnabled = phase === 'animating' && showAnalysisCue;
  const waitingFactBody = (waitingFact || '').trim();
  const waitingFactUseShortPool = selectedSpreadId === 'single' || selectedSpreadId === 'three_cards';
  const { displayedText: waitingFactDisplayed, isComplete: waitingFactComplete } = useTypewriter(waitingFactBody, {
    charsPerSec: waitingFactUseShortPool ? 38 : 22,
    enabled: waitingFactTypingEnabled && Boolean(waitingFactBody),
  });

  useEffect(() => {
    isPaidAccessRef.current = isPaidAccess;
  }, [isPaidAccess]);

  useEffect(() => {
    const tg = window?.Telegram?.WebApp;
    if (!tg?.BackButton) return undefined;
    try {
      tg.BackButton.hide();
    } catch (_) {}
    return undefined;
  }, []);

  useEffect(() => {
    updateSession({
      tarologistChatUi: phase === 'chat',
      tarologistPromptStage: phase === 'chat' && tarologistPromptStage,
    });
    return () => {
      updateSession({ tarologistChatUi: false, tarologistPromptStage: false });
    };
  }, [phase, tarologistPromptStage, updateSession]);

  useEffect(() => {
    if (phase !== 'result') return undefined;
    pushBottomNavSuppression();
    return () => popBottomNavSuppression();
  }, [phase, pushBottomNavSuppression, popBottomNavSuppression]);

  useEffect(() => {
    if (phase !== 'chat') setTarologistPromptStage(false);
  }, [phase]);

  useEffect(() => {
    if (!waitingFactTypingEnabled) {
      setWaitingFact('');
      return;
    }
    const pool = waitingFactUseShortPool ? TAROT_WAITING_FACTS_SHORT : TAROT_WAITING_FACTS_LONG;
    const idx = Math.floor(Math.random() * pool.length);
    setWaitingFact(pool[idx] || pool[0]);
  }, [waitingFactTypingEnabled, cinematicRunId, waitingFactUseShortPool]);

  useEffect(() => {
    questionRef.current = question;
  }, [question]);

  useEffect(() => {
    pickedIndicesRef.current = pickedIndices;
  }, [pickedIndices]);

  const selectedSpread = useMemo(() => getSpreadById(selectedSpreadId), [selectedSpreadId]);
  const welcomeBySpread = limits?.tarot?.welcome_by_spread || {};
  const hasWelcomeFreeForSpread = Boolean(welcomeBySpread[selectedSpreadId]);
  const hasEnoughTarotBalance = useMemo(
    () => tarotPriceCents <= 0 || tarotBalanceCents >= tarotPriceCents,
    [tarotBalanceCents, tarotPriceCents]
  );
  const spreadHint = useMemo(() => getSpreadHint(selectedSpreadId), [selectedSpreadId]);
  const tarologistSuggestedQuestions = useMemo(
    () => getRotatedSuggestedQuestions(selectedSpreadId, tarologistPromptVariant, 5),
    [selectedSpreadId, tarologistPromptVariant]
  );
  const activeProfileId = useMemo(() => sanitizeProfileId(activeUser?.id), [activeUser?.id]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!activeDeckId) return;
    try {
      window.localStorage?.setItem(TAROT_LAST_DECK_STORAGE_KEY, String(activeDeckId));
    } catch (_) {}
  }, [activeDeckId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!selectedSpreadId) return;
    try {
      window.localStorage?.setItem(TAROT_LAST_SPREAD_STORAGE_KEY, String(selectedSpreadId));
    } catch (_) {}
  }, [selectedSpreadId]);
  const spreadPickerItems = useMemo(
    () => [
      ...SPREADS.map((s) => ({ id: s.id, ...s })),
      { id: 'magic_ball', name: 'Магический шар', icon: '🔮' },
    ],
    [],
  );
  const deckPickerItems = useMemo(
    () => decks.map((d) => ({ id: d.id, name: d.name, description: d.description, deckImage: d.deckImage, backImage: d.backImage })),
    [decks]
  );
  const deckCardSize = useMemo(() => {
    const safeW = viewportWidth || 390;
    const baseW = clamp(Math.round(safeW * 0.295), 108, 148);
    const baseH = clamp(Math.round(baseW * 1.46), 160, 218);
    return { w: Math.round(baseW * 1.2), h: Math.round(baseH * 1.2) };
  }, [viewportWidth]);
  const spreadPickerCardSize = useMemo(() => {
    const safeW = viewportWidth || 390;
    const baseW = clamp(Math.round(safeW * 0.252), 94, 122);
    const baseH = clamp(Math.round(baseW * 1.42), 134, 173);
    return { w: Math.round(baseW * 1.2), h: Math.round(baseH * 1.2) };
  }, [viewportWidth]);
  const spreadGapPx = useMemo(
    () => 0,
    []
  );
  const deckGapPx = useMemo(
    () => 0,
    []
  );
  const deckPickerSize = useMemo(
    () => ({ w: Math.round(deckCardSize.w * 1.05), h: Math.round(deckCardSize.h * 1.05) }),
    [deckCardSize]
  );

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const buildTarotSnapshot = (overrides = {}) => ({
    selectedSpreadId,
    activeDeckId,
    question,
    resultQuestion,
    spreadSize,
    spread,
    phase,
    animatingSubPhase,
    isDrawing,
    showAnalysisCue,
    overallInterpretation,
    tarotSummaryShort,
    practicalAdvice,
    spreadFailed,
    readingId,
    followUpQuestions,
    chatMessages,
    dialogueRequired,
    guidedQuestions,
    guidedStep,
    guidedAnswers,
    guidedFinished,
    showFinalSummary,
    ...overrides,
  });

  useEffect(() => {
    const snap = session?.snapshot;
    if (!snap || typeof snap !== 'object') return;
    const snapTs = Number(snap.updatedAt || 0);
    if (snapTs && snapTs <= lastAppliedSessionTsRef.current) return;
    const hasSpread = Array.isArray(snap.spread) && snap.spread.length > 0;
    if (!session?.inProgress && !hasSpread) return;
    const isFreshMountRestore = spread.length === 0 && phase === 'select';
    if (snapTs) lastAppliedSessionTsRef.current = snapTs;
    if (snap.selectedSpreadId) setSelectedSpreadId(String(snap.selectedSpreadId));
    if (snap.activeDeckId) setActiveDeckId(String(snap.activeDeckId));
    if (typeof snap.question === 'string') {
      questionRef.current = snap.question;
      setQuestion(snap.question);
    }
    if (typeof snap.resultQuestion === 'string') {
      setResultQuestion(snap.resultQuestion);
    }
    if (Number.isFinite(Number(snap.spreadSize))) setSpreadSize(Number(snap.spreadSize));
    if (Array.isArray(snap.spread) && (snap.spread.length > 0 || spread.length === 0)) {
      setSpread(snap.spread);
    }
    if (typeof snap.phase === 'string') {
      // Возврат во вкладку: не переигрываем cinematic-раскладку, показываем уже разложенные карты.
      if (isFreshMountRestore && session?.inProgress && hasSpread && snap.phase === 'animating') {
        setPhase('result');
      } else {
        setPhase(snap.phase);
      }
    }
    if (typeof snap.animatingSubPhase === 'string') setAnimatingSubPhase(snap.animatingSubPhase);
    if (typeof snap.showAnalysisCue === 'boolean') setShowAnalysisCue(snap.showAnalysisCue);
    if (typeof snap.overallInterpretation === 'string') setOverallInterpretation(snap.overallInterpretation);
    if (typeof snap.tarotSummaryShort === 'string') setTarotSummaryShort(snap.tarotSummaryShort);
    if (typeof snap.practicalAdvice === 'string') setPracticalAdvice(snap.practicalAdvice);
    if (typeof snap.spreadFailed === 'boolean') setSpreadFailed(snap.spreadFailed);
    if (typeof snap.readingId === 'string') setReadingId(snap.readingId);
    if (Array.isArray(snap.followUpQuestions)) setFollowUpQuestions(snap.followUpQuestions);
    if (Array.isArray(snap.chatMessages)) setChatMessages(snap.chatMessages);
    if (typeof snap.dialogueRequired === 'boolean') setDialogueRequired(snap.dialogueRequired);
    if (Array.isArray(snap.guidedQuestions)) setGuidedQuestions(snap.guidedQuestions);
    if (Number.isFinite(Number(snap.guidedStep))) setGuidedStep(Number(snap.guidedStep));
    if (Array.isArray(snap.guidedAnswers)) setGuidedAnswers(snap.guidedAnswers);
    if (typeof snap.guidedFinished === 'boolean') setGuidedFinished(snap.guidedFinished);
    if (typeof snap.showFinalSummary === 'boolean') setShowFinalSummary(snap.showFinalSummary);
    setIsDrawing(Boolean(session?.inProgress || snap.isDrawing));
  }, [session, setActiveDeckId, setSpread, spread.length, phase]);

  useEffect(() => {
    if (phase !== 'animating') return;
    const needDeck = (
      (
        selectedSpreadId === 'single'
        || selectedSpreadId === 'three_cards'
        || selectedSpreadId === 'financial'
        || selectedSpreadId === 'six_cards'
        || selectedSpreadId === 'ten_cards'
      )
      && animatingSubPhase === 'picking'
    ) || animatingSubPhase === 'singleArcPick';
    if (!needDeck || shuffledDeckForPick.length > 0 || cardPool.length === 0) return;
    const shuffled = shuffleArray(cardPool).map((c) => ({
      ...c,
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      astrovDeckId: activeDeck.id,
    }));
    setShuffledDeckForPick(shuffled);
  }, [phase, animatingSubPhase, selectedSpreadId, shuffledDeckForPick.length, cardPool.length, activeDeck?.backClass, activeDeck?.backImage, activeDeck?.id]);

  const positionLabelsLegacy = {
    1: ['Сегодня'],
    5: ['Ситуация', 'Препятствие', 'Ресурс', 'Совет', 'Итог'],
    7: ['Основание', 'Суть', 'Препятствие', 'Ресурс', 'Скрытое', 'Совет', 'Итог'],
  };

  const maybeOpenAccessModal = useCallback(() => {
    // Оплата скрыта на этапе запуска TARO.
  }, []);

  const canStartTarotPaidFlow = useCallback(() => true, []);

  useEffect(() => {
    if (isPaidAccess) return;
    if (showAccessModal) return;
    if (accessModalDismissed) return;
    if (overallInterpretation) maybeOpenAccessModal(overallInterpretation);
    const cardMessage = spread.find((card) => {
      const m = String(card?.meaning || '').toLowerCase();
      return m.includes('лимит исчерпан') || m.includes('недостаточно средств') || m.includes('подписк');
    })?.meaning;
    if (cardMessage) maybeOpenAccessModal(cardMessage);
  }, [overallInterpretation, spread, showAccessModal, accessModalDismissed, maybeOpenAccessModal, isPaidAccess]);
  const currentPositions =
    spreadSize === selectedSpread.cards ? selectedSpread.positions : positionLabelsLegacy[spreadSize] || [];

  const buildGuidedQuestions = (source = []) => {
    const fromAi = Array.isArray(source)
      ? source.map((q) => String(q || '').trim()).filter(Boolean)
      : [];
    const q = String(question || '').toLowerCase();
    const isThirdPerson = /\b(друг|подруг|брата|сестр|муж|жен|партнер|партнёр|сын|дочь|он|она|ему|ей|его|ее|её)\b/.test(q);
    const bankSelf = [
      [
        'Вы уже предпринимали конкретные шаги по этой теме?',
        'Сейчас для вас важнее стабильность, чем быстрый результат?',
        'Вы готовы действовать в ближайшие 7 дней?',
        'Что для вас сейчас важнее: ясность или скорость?',
        'Готовы ли вы зафиксировать один следующий шаг и срок?',
      ],
      [
        'У вас есть чёткий критерий, по которому поймёте, что движетесь верно?',
        'В этой ситуации вас больше сдерживает страх ошибки, чем нехватка ресурсов?',
        'Вы готовы начать с малого теста, а не с большого рывка?',
        'Что для вас сейчас важнее: ясность или скорость?',
        'Готовы ли вы зафиксировать один следующий шаг и срок?',
      ],
      [
        'Вы обсуждали это решение с тем, кто реально влияет на результат?',
        'Сейчас есть хотя бы один ресурс, на который можно опереться уже сегодня?',
        'Вы готовы временно отказаться от второстепенного ради главной цели?',
        'Что для вас сейчас важнее: ясность или скорость?',
        'Готовы ли вы зафиксировать один следующий шаг и срок?',
      ],
    ];
    const bankThird = [
      [
        'Он уже предпринимал конкретные шаги по этой теме?',
        'Сейчас для него важнее стабильность, чем быстрый результат?',
        'Он готов действовать в ближайшие 7 дней?',
        'Что для него сейчас важнее: ясность или скорость?',
        'Готов ли он зафиксировать один следующий шаг и срок?',
      ],
      [
        'У него есть чёткий критерий, по которому он поймёт, что движется верно?',
        'В этой ситуации его больше сдерживает страх ошибки, чем нехватка ресурсов?',
        'Он готов начать с малого теста, а не с большого рывка?',
        'Что для него сейчас важнее: ясность или скорость?',
        'Готов ли он зафиксировать один следующий шаг и срок?',
      ],
      [
        'Он обсуждал это решение с человеком, который реально влияет на результат?',
        'Сейчас у него есть хотя бы один ресурс, на который можно опереться уже сегодня?',
        'Он готов временно отказаться от второстепенного ради главной цели?',
        'Что для него сейчас важнее: ясность или скорость?',
        'Готов ли он зафиксировать один следующий шаг и срок?',
      ],
    ];
    const src = isThirdPerson ? bankThird : bankSelf;
    const pick = src[Math.abs(q.split('').reduce((acc, ch) => acc + ch.charCodeAt(0), 0)) % src.length];
    const merged = [...fromAi, ...pick];
    const target = Math.min(5, Math.max(3, fromAi.length >= 3 ? fromAi.length : 5));
    return merged.slice(0, target);
  };

  useEffect(() => {
    if (!decks.find((deck) => deck.id === activeDeckId)) {
      setActiveDeckId(decks[0]?.id);
    }
  }, [decks, activeDeckId, setActiveDeckId]);

  useEffect(() => {
    setSpreadSize(selectedSpread.cards);
  }, [selectedSpreadId, selectedSpread.cards]);


  useEffect(() => {
    setShowFinalSummary(selectedSpread.cards < 6);
  }, [selectedSpread.cards, selectedSpreadId]);

  // Быстрый расклад: принудительно показывать начало страницы с картой, а не конец
  const singleCardResultRef = useRef(null);
  const skipSingleSelectTransitionRef = useRef(false);
  const preloadedImagePromisesRef = useRef(new Map());
  /** DOM-узел карты в портале выбора (карта дня), для плавного перехода к блоку результата */
  const singlePickPortalRef = useRef(null);
  const singleResultCardBoxRef = useRef(null);
  const [singleCardFly, setSingleCardFly] = useState(null);
  /** Убрать портал вылета (z-400) при уходе с animating, иначе две карты визуально накладываются. */
  const [singleHidePickPortal, setSingleHidePickPortal] = useState(false);
  /** В середине полёта показать карту в раскладе и кроссфейд с исчезающей портальной картой. */
  const [singleCardRevealResult, setSingleCardRevealResult] = useState(false);
  const runBatchReadingRef = useRef(null);
  const waitForPaint = useCallback(async () => {
    if (typeof window === 'undefined') return;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }, []);
  const preloadImage = useCallback((src) => {
    if (!src || typeof Image === 'undefined') return Promise.resolve();
    const key = String(src);
    const cached = preloadedImagePromisesRef.current.get(key);
    if (cached) return cached;
    const promise = new Promise((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };
      const timer = window.setTimeout(finish, 220);
      const img = new Image();
      img.onload = () => {
        if (typeof img.decode === 'function') {
          img.decode().catch(() => {}).finally(() => {
            window.clearTimeout(timer);
            finish();
          });
          return;
        }
        window.clearTimeout(timer);
        finish();
      };
      img.onerror = () => {
        window.clearTimeout(timer);
        finish();
      };
      img.src = key;
    });
    preloadedImagePromisesRef.current.set(key, promise);
    return promise;
  }, []);
  useEffect(() => {
    if (!decks.length) return;
    decks.forEach((deck) => {
      if (deck?.backImage) preloadImage(deck.backImage);
    });
  }, [decks, preloadImage]);
  const singleResultCard = useMemo(() => {
    if (selectedSpreadId !== 'single') return null;
    const spreadCard = spread?.[0] || {};
    const cinematicCard = cinematicCards?.[0] || {};
    const hasSpreadImage = Boolean(spreadCard?.image);
    return {
      ...cinematicCard,
      ...spreadCard,
      // Keep single-card result consistent: spread card is the source of truth.
      image: spreadCard?.image || cinematicCard?.image || '',
      backImage: spreadCard?.backImage || cinematicCard?.backImage || activeDeck?.backImage,
      card_name: spreadCard?.card_name || cinematicCard?.card_name || 'Расклад',
      name: spreadCard?.name || cinematicCard?.name || 'Расклад',
      is_reversed:
        typeof spreadCard?.is_reversed === 'boolean'
          ? spreadCard.is_reversed
          : Boolean(cinematicCard?.is_reversed),
      loading: Boolean(spreadCard?.loading) && !hasSpreadImage,
    };
  }, [selectedSpreadId, spread, cinematicCards, activeDeck?.backImage]);

  useLayoutEffect(() => {
    if (!singleCardFly || singleCardFly.to != null) return undefined;
    if (phase !== 'result' || selectedSpreadId !== 'single') return undefined;
    let cancelled = false;
    let tries = 0;
    const maxTries = 32;
    const measure = () => {
      if (cancelled) return;
      tries += 1;
      const el = singleResultCardBoxRef.current;
      if (!el) {
        if (tries >= maxTries) setSingleCardFly(null);
        else requestAnimationFrame(measure);
        return;
      }
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) {
        if (tries >= maxTries) setSingleCardFly(null);
        else requestAnimationFrame(measure);
        return;
      }
      setSingleCardFly((s) =>
        s && !s.to ? { ...s, to: { left: r.left, top: r.top, width: r.width, height: r.height } } : s
      );
    };
    requestAnimationFrame(() => requestAnimationFrame(measure));
    return () => {
      cancelled = true;
    };
  }, [singleCardFly, phase, selectedSpreadId]);

  useEffect(() => {
    if (!singleCardFly?.to || !singleCardFly?.from) {
      setSingleCardRevealResult(false);
      return;
    }
    const CROSSFADE_AT_MS = Math.round(900 * 0.42);
    const id = window.setTimeout(() => setSingleCardRevealResult(true), CROSSFADE_AT_MS);
    return () => window.clearTimeout(id);
  }, [singleCardFly]);

  useEffect(() => {
    if (phase !== 'animating') return;
    if (!skipSingleSelectTransitionRef.current) return;
    const id = requestAnimationFrame(() => {
      skipSingleSelectTransitionRef.current = false;
    });
    return () => cancelAnimationFrame(id);
  }, [phase, cinematicRunId]);

  const forceScrollTop = useCallback(() => {
    if (typeof window === 'undefined') return;
    if (!window.location.pathname.startsWith('/tarot')) return;
    window.scrollTo({ top: 0, behavior: 'auto' });
    const se = document.scrollingElement;
    if (se) se.scrollTop = 0;
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const main = document.querySelector('main');
    if (main) main.scrollTo({ top: 0, behavior: 'auto' });
    const tarotResult = document.querySelector('[data-tarot-result-scroll="1"]');
    if (tarotResult && typeof tarotResult.scrollTo === 'function') {
      tarotResult.scrollTo({ top: 0, behavior: 'auto' });
    }
  }, []);

  useEffect(() => {
    if (phase !== 'select') return;
    forceScrollTop();
    const t1 = setTimeout(forceScrollTop, 40);
    const t2 = setTimeout(forceScrollTop, 160);
    const t3 = setTimeout(forceScrollTop, 360);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [phase, forceScrollTop]);

  /** Один проход прокрутки в начало результата: без цепочек таймеров, чтобы не было рывков при смене фазы. */
  useLayoutEffect(() => {
    if (phase !== 'result' || spread.length < 1) return;
    const applyTop = () => {
      forceScrollTop();
      resultScrollRef.current?.scrollTo({ top: 0, behavior: 'auto' });
      if (selectedSpreadId === 'single' && singleCardResultRef.current) {
        resultScrollRef.current?.scrollTo({ top: 0, behavior: 'auto' });
      }
    };
    applyTop();
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(applyTop);
    });
    const tLate = window.setTimeout(applyTop, 320);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(tLate);
    };
  }, [phase, spread.length, forceScrollTop, selectedSpreadId]);

  const spreadNameLines = useCallback((spread) => {
    if (spread.id === 'ten_cards') return ['Кельтский', 'крест'];
    return [spread.name];
  }, []);
  const handleSpreadPress = useCallback((spreadId) => {
    setSelectedSpreadId((prev) => (prev === spreadId ? prev : spreadId));
  }, []);
  const handleSpreadPickerSelect = useCallback(
    (id) => {
      handleSpreadPress(id);
    },
    [handleSpreadPress]
  );
  const handleDeckPickerSelect = useCallback(
    (id) => {
      setActiveDeckId(id);
      triggerHaptics('light');
    },
    []
  );

  const spreadPalette = useMemo(() => {
    if (selectedSpreadId === 'magic_ball') return { hi: 0xa78bfa, mid: 0x7c3aed, low: 0x1a0b2e };
    if (selectedSpreadId === 'financial') return { hi: 0x34d399, mid: 0x16a34a, low: 0x062814 };
    if (selectedSpread.cards >= 10) return { hi: 0x8b5cf6, mid: 0x1d4ed8, low: 0x0b1022 };
    if (selectedSpread.cards >= 6) return { hi: 0xf97316, mid: 0xdc2626, low: 0x1a0b1e };
    if (selectedSpread.cards >= 5) return { hi: 0xf59e0b, mid: 0x7c3aed, low: 0x0b0b1e };
    if (selectedSpread.cards >= 3) return { hi: 0x22d3ee, mid: 0x2563eb, low: 0x0b1020 };
    return { hi: 0xfbbf24, mid: 0xea580c, low: 0x120b1e };
  }, [selectedSpread.cards, selectedSpreadId]);
  const spreadPulseColor = useMemo(() => {
    const v = Number(spreadPalette.hi) || 0xfbbf24;
    const r = (v >> 16) & 255;
    const g = (v >> 8) & 255;
    const b = v & 255;
    return `rgba(${r}, ${g}, ${b}, 1)`;
  }, [spreadPalette.hi]);

  useEffect(() => {
    let cancelled = false;
    const init = async () => {
      if (!vantaRef.current) return;
      try {
        const THREE = await import('three');
        const FOG = await import('vanta/dist/vanta.fog.min');
        if (cancelled || !vantaRef.current) return;
        if (vantaEffectRef.current?.destroy) {
          vantaEffectRef.current.destroy();
        }
        const createFog = FOG.default || FOG;
        const baseHi = Number(spreadPalette.hi) || 0xfbbf24;
        const baseMid = Number(spreadPalette.mid) || 0xea580c;
        const baseLow = Number(spreadPalette.low) || 0x120b1e;
        vantaEffectRef.current = createFog({
          el: vantaRef.current,
          THREE,
          mouseControls: false,
          touchControls: false,
          gyroControls: false,
          minHeight: 200,
          minWidth: 200,
          speed: 1.6,
          blurFactor: 0.68,
          highlightColor: baseHi,
          midtoneColor: baseMid,
          lowlightColor: baseLow,
          baseColor: 0x090813,
        });
      } catch {
        // Silent fallback to existing CSS fog layers.
      }
    };
    init();
    return () => {
      cancelled = true;
      if (vantaEffectRef.current?.destroy) {
        vantaEffectRef.current.destroy();
        vantaEffectRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const fx = vantaEffectRef.current;
    if (!fx?.setOptions) return;
    const boost = phase === 'result' && spread.length > 0 ? 16 : 6;
    try {
      fx.setOptions({
        speed: 1.6,
        mouseControls: false,
        touchControls: false,
        blurFactor: 0.68,
        highlightColor: shiftHex(spreadPalette.hi, boost),
        midtoneColor: shiftHex(spreadPalette.mid, Math.round(boost * 0.66)),
        lowlightColor: shiftHex(spreadPalette.low, Math.round(boost * 0.33)),
      });
    } catch {
      // ignore
    }
  }, [phase, animatingSubPhase, spread.length, spreadPalette.hi, spreadPalette.mid, spreadPalette.low]);

  useEffect(() => {
    if (phase !== 'animating' || animatingStartedRef.current || shuffledDeckForPick.length === 0) return;
    animatingStartedRef.current = true;
    return undefined;
  }, [phase, shuffledDeckForPick.length, selectedSpread?.cards, selectedSpreadId]);

  useEffect(() => {
    // Для расклада "Отношения" итог показываем сразу, без кнопки "Получить итог расклада".
    if (selectedSpreadId === 'six_cards' && !dialogueRequired && !showFinalSummary) {
      setShowFinalSummary(true);
    }
  }, [selectedSpreadId, dialogueRequired, showFinalSummary]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      setSpeechSupported(false);
      return;
    }
    const speechCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
    setSpeechSupported(Boolean(speechCtor));
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onResize = () => setViewportWidth(window.innerWidth || 390);
    onResize();
    window.addEventListener('resize', onResize, { passive: true });
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const startVoiceInput = () => {
    setSpeechError('');
    setLiveTranscript('');
    if (typeof window === 'undefined') {
      setSpeechSupported(false);
      setSpeechError('Голосовой ввод недоступен в этом браузере.');
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setSpeechSupported(false);
      setSpeechError('Голосовой ввод недоступен в этом браузере.');
      return;
    }
    setSpeechSupported(true);
    const recognition = new SpeechRecognition();
    recognition.lang = 'ru-RU';
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    recognition.continuous = true;
    recognition.onstart = () => {
      const baseQuestion = (question || '').trim();
      recordingBaseRef.current = baseQuestion;
      recordingCommittedRef.current = baseQuestion;
      setIsRecording(true);
    };
    recognition.onerror = () => {
      setIsRecording(false);
      setSpeechError('Не удалось распознать голос. Попробуйте еще раз.');
    };
    recognition.onend = () => {
      if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = setTimeout(() => {
        setIsRecording(false);
        setLiveTranscript('');
      }, 4000);
    };
    recognition.onresult = (event) => {
      let interim = '';
      let finalText = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const text = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += text;
        } else {
          interim += text;
        }
      }
      if (finalText) {
        const nextBase = [recordingCommittedRef.current, finalText]
          .filter(Boolean)
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim();
        recordingCommittedRef.current = nextBase;
        recordingBaseRef.current = nextBase;
        setQuestion(nextBase);
      }
      if (interim) {
        const preview = [recordingCommittedRef.current, interim]
          .filter(Boolean)
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim();
        setQuestion((prev) => {
          if (!prev) return preview;
          return preview.length >= prev.length ? preview : prev;
        });
      }
      setLiveTranscript(interim);
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setIsRecording(false);
      setSpeechError('Не удалось запустить микрофон. Разрешите доступ и попробуйте снова.');
    }
  };

  const stopVoiceInput = () => {
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsRecording(false);
    setLiveTranscript('');
  };

  useEffect(() => () => {
    if (silenceTimeoutRef.current) {
      clearTimeout(silenceTimeoutRef.current);
      silenceTimeoutRef.current = null;
    }
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }
  }, []);

  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  const drawSingleCard = async () => {
    if (cardPool.length === 0) return null;
    const shuffled = shuffleArray(cardPool);
    const raw = shuffled[0];
    const card = {
      ...raw,
      is_reversed: allowReversed ? Math.random() < 0.5 : false,
    };
    const cardImage = await resolveCardImage(card, activeDeck?.id);
    const withMeta = {
      ...card,
      astrovDeckId: activeDeck.id,
      meaning: '',
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      loading: true,
    };
    try {
      const res = await fetch(`${API_BASE}/api/tarot/draw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deck: activeDeck.id,
          question: question || 'Одна карта',
          card_name: getCardNameRu(card?.id, activeDeck.id) || card?.name || '',
          card_id: (card?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
          position: 1,
          total: 1,
          is_reversed: Boolean(card?.is_reversed),
          init_data: getInitData(),
          personalize: false,
          profile_id: null,
        }),
      });
      const data = res.ok ? await res.json() : (res.status === 403 ? await res.json().catch(() => ({})) : {});
      const limitMsg = res.status === 403 ? (data?.detail || 'Лимит исчерпан. Оформите подписку для продолжения.') : null;
      return {
        ...withMeta,
        name: card?.name || data?.card_name || 'Карта',
        meaning: limitMsg || data?.interpretation || 'Звезды молчат. Попробуй позже.',
        image:
          cardImage ||
          `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=${encodeURIComponent(
            data?.card_name || card?.name || 'Tarot'
          )}`,
        loading: false,
      };
    } catch (_) {
      return {
        ...withMeta,
        meaning: 'Звезды молчат. Попробуй еще раз.',
        image: cardImage || `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=Tarot`,
        loading: false,
      };
    }
  };

  const drawSingleCardForPosition = async (card, positionIndex, positionName, total) => {
    if (!card) return null;
    const cardImage = await resolveCardImage(card, activeDeck?.id);
    const withMeta = {
      ...card,
      astrovDeckId: activeDeck.id,
      meaning: '',
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      loading: true,
    };
    const MAX_RETRIES = 4;
    const makeRequest = async () => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch(`${API_BASE}/api/tarot/draw`, {
        signal: controller.signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deck: activeDeck.id,
          question: question || 'Расклад',
          card_name: getCardNameRu(card?.id, activeDeck.id) || card?.name || '',
          card_id: (card?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
          position: positionIndex,
          total,
          position_name: positionName || undefined,
          is_reversed: Boolean(card?.is_reversed),
          init_data: getInitData(),
          personalize: false,
          profile_id: null,
        }),
      });
      clearTimeout(timeoutId);
      if (res.status === 503) {
        return { _limit: true, detail: 'Система перегружена. Повторите попытку позже.' };
      }
      if (res.status === 403) {
        const errData = await res.json().catch(() => ({}));
        return { _limit: true, detail: errData?.detail || 'Лимит исчерпан. Оформите подписку для продолжения.' };
      }
      return res.ok ? await res.json() : {};
    };
    let data = {};
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        data = await makeRequest();
        if (data?._limit) {
          return {
            ...withMeta,
            name: card?.name || 'Карта',
            meaning: data.detail,
            image: cardImage || `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=Tarot`,
            loading: false,
          };
        }
        const interpretation = data?.interpretation || '';
        const isSilent = !interpretation.trim() || /звезды молчат/i.test(interpretation);
        if (!isSilent || attempt === MAX_RETRIES) {
          return {
            ...withMeta,
            name: card?.name || data?.card_name || 'Карта',
            meaning: interpretation || 'Не удалось загрузить. Нажмите «Повторить» ниже.',
            image:
              cardImage ||
              `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=${encodeURIComponent(
                data?.card_name || card?.name || 'Tarot'
              )}`,
            loading: false,
          };
        }
        await new Promise((r) => setTimeout(r, 1000 + attempt * 800));
      } catch (_) {
        if (attempt === MAX_RETRIES) {
          return {
            ...withMeta,
            meaning: 'Не удалось загрузить. Нажмите «Повторить» ниже.',
            image: cardImage || `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=Tarot`,
            loading: false,
          };
        }
        await new Promise((r) => setTimeout(r, 800 + attempt * 600));
      }
    }
    return {
      ...withMeta,
      name: card?.name || data?.card_name || 'Карта',
      meaning: data?.interpretation || 'Звезды молчат. Попробуй позже.',
      image:
        cardImage ||
        `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=${encodeURIComponent(
          data?.card_name || card?.name || 'Tarot'
        )}`,
      loading: false,
    };
  };

  const drawCard = async (options = {}) => {
    const nextSize = options.size ?? spreadSize;
    const nextQuestion = options.question ?? question;
    if (options.size != null) setSpreadSize(options.size);
    if (options.question != null) setQuestion(options.question);
    setResultQuestion(String(nextQuestion || '').trim());
    if (isDrawing) return;
    if (cardPool.length === 0) return;
    if (!canStartTarotPaidFlow()) return;
    setAccessModalDismissed(false);
    setShowAccessModal(false);
    setIsDrawing(true);
    setOverallInterpretation('');
    setTarotSummaryShort('');
    const shuffled = shuffleArray(cardPool);
    const pickedCards = shuffled.slice(0, nextSize).map((card) => ({
      ...card,
      is_reversed: allowReversed ? Math.random() < 0.5 : false,
      meaning: '',
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      astrovDeckId: activeDeck.id,
      loading: true,
    }));
    setSpread(pickedCards);
    try {
      const interpretations = [];
      for (let index = 0; index < pickedCards.length; index += 1) {
        if (index > 0) await delay(1300);
        const card = pickedCards[index];
        let data = {};
        try {
          const res = await fetch(`${API_BASE}/api/tarot/draw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              deck: activeDeck.id,
              question: nextQuestion,
              card_name: getCardNameRu(card?.id, activeDeck.id) || card?.name || '',
              card_id: (card?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
              position: index + 1,
              total: nextSize,
              position_name: currentPositions[index] || undefined,
              is_reversed: Boolean(card?.is_reversed),
              init_data: getInitData(),
              personalize: false,
              profile_id: null,
            }),
          });
          if (res.status === 503) {
            data = { interpretation: 'Система перегружена. Повторите попытку позже.' };
          } else if (res.status === 403) {
            const errData = await res.json().catch(() => ({}));
            data = { interpretation: errData?.detail || 'Лимит исчерпан. Оформите подписку для продолжения.' };
          } else {
            data = res.ok ? await res.json() : {};
          }
        } catch (_) {
          data = {};
        }
        const cardImage = await resolveCardImage(card, activeDeck?.id);
        const updated = {
          ...card,
          name: card?.name || data?.card_name || 'Карта',
          meaning: data?.interpretation || 'Звезды молчат. Попробуй позже.',
          image:
            cardImage ||
            `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=${encodeURIComponent(
              data?.card_name || card?.name || 'Tarot'
            )}`,
          loading: false,
        };
        interpretations.push(updated);
        setSpread([...interpretations]);
      }

      await delay(1300);
      const summaryRes = await fetch(`${API_BASE}/api/tarot/draw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deck: activeDeck.id,
          question: `Общий итог расклада. Вопрос: ${nextQuestion || 'без вопроса'}. Карты: ${interpretations
            .map((c) => getCardNameRu(c?.id, activeDeck.id) || c?.name || '')
            .filter(Boolean)
            .join(', ')}.`,
          card_name: 'Общий расклад',
          is_reversed: false,
          init_data: getInitData(),
          personalize: false,
          profile_id: null,
        }),
      });
      if (summaryRes.status === 403) {
        const errData = await summaryRes.json().catch(() => ({}));
        setOverallInterpretation(errData?.detail || 'Лимит исчерпан. Оформите подписку для продолжения.');
      } else {
        const summary = summaryRes.ok ? await summaryRes.json() : {};
        setOverallInterpretation(summary?.interpretation || '');
      }
      refetchAuth?.();
    } catch (e) {
      setSpread((current) =>
        current.map((card) => ({
          ...card,
          meaning: 'Звезды молчат. Попробуй еще раз.',
          image:
            card?.image ||
            `https://placehold.co/300x500/${activeDeck.color}/fbbf24?text=Tarot`,
          loading: false,
        }))
      );
    }
    setIsDrawing(false);
  };

  const handleSingleCardPicked = useCallback(
    async (card) => {
      const posName = currentPositions[0] || 'Сегодня';
      const initialEntry = {
        ...card,
        astrovDeckId: activeDeck.id,
        card_id: (card?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
        card_name: resolveCardTitle(card?.id, card?.name, activeDeck.id),
        name: resolveCardTitle(card?.id, card?.name, activeDeck.id),
        position_name: posName,
        meaning: '',
        interpretation: '',
        loading: true,
        backClass: activeDeck.backClass,
        backImage: activeDeck.backImage,
        is_reversed: Boolean(card?.is_reversed),
      };
      setSpread([initialEntry]);
      setPhase('result');
      updateSession({
        phase: 'result',
        spread: [initialEntry],
        isDrawing: true,
        inProgress: true,
      });
      const run = runBatchReadingRef.current;
      if (run) await run([card], { needGuidedDialogue: false, skipPhaseUpdate: true });
      if (isMountedRef.current) {
        finishSession({
          phase: 'result',
          isDrawing: false,
          inProgress: false,
        });
      }
    },
    [
      currentPositions,
      activeDeck.id,
      activeDeck.backClass,
      activeDeck.backImage,
      updateSession,
      finishSession,
    ]
  );

  const triggerHaptics = (style = 'medium') => {
    const tg = window?.Telegram?.WebApp;
    if (style === 'selection' && tg?.HapticFeedback?.selectionChanged) {
      tg.HapticFeedback.selectionChanged();
      return;
    }
    if (tg?.HapticFeedback?.impactOccurred) {
      tg.HapticFeedback.impactOccurred(style === 'selection' ? 'light' : style);
    } else if (navigator?.vibrate) {
      navigator.vibrate(20);
    }
  };

  const validateQuestion = async () => {
    const q = (question || '').trim();
    if (!q) return true;
    const spreadForValidation =
      selectedSpread.cards >= 10 ? 'celtic' : selectedSpread.cards >= 6 ? 'relationship' : 'basic';
    try {
      const res = await fetch(`${API_BASE}/api/tarot/validate-question`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, spread: spreadForValidation }),
      });
      const data = res.ok ? await res.json() : {};
      if (data.valid === false && data.message) {
        setQuestionError(data.message);
        return false;
      }
      setQuestionError('');
      return true;
    } catch {
      return true;
    }
  };

  const handleContinueFromSpread = () => {
    if (!selectedSpreadId || isDrawing) return;
    triggerHaptics('medium');
    if (selectedSpreadId === 'magic_ball') {
      setShowMagicBall(true);
      return;
    }
    if (selectedSpreadId === 'single') {
      skipSingleSelectTransitionRef.current = true;
      const deckIds = decks.map((d) => d.id).filter(Boolean);
      const randomDeckId = deckIds[Math.floor(Math.random() * deckIds.length)] || deckIds[0];
      const chosenDeck = decks.find((d) => d.id === randomDeckId);
      const pool = chosenDeck?.cards?.length ? chosenDeck.cards : [];
      if (!pool.length) {
        setOverallInterpretation('Колоды временно недоступны. Перезайдите в Таро через несколько секунд.');
        setSpreadFailed(true);
        return;
      }
      handleStartSpreadWithDeck(chosenDeck);
      return;
    }
    handleStartSpread();
  };

  const handleStartSpreadWithDeck = async (deckOverride) => {
    const deckToUse = deckOverride || activeDeck;
    const poolToUse = deckOverride ? (deckOverride.cards || []) : cardPool;
    if (!selectedSpreadId || !deckToUse || !poolToUse?.length || isDrawing) return;

    singleCardDailyFreeRef.current = false;
    skipSingleCostGateRef.current = false;

    setQuestionError('');
    // Вибро уже даёт кнопка «Выполнить расклад» (handleContinueFromSpread); не дублировать.
    preloadImage(deckToUse?.backImage || '');
    // Сначала уходим со страницы выбора: это убирает «подпрыгивание» карточек раскладов в текущем экране.
    setPhase('animating');
    setSingleHidePickPortal(false);
    const shuffled = shuffleArray(poolToUse).map((c) => ({
      ...c,
      backClass: deckToUse.backClass,
      backImage: deckToUse.backImage,
      astrovDeckId: deckToUse.id,
    }));
    setShuffledDeckForPick(shuffled);
    setSpread([]);
    setOverallInterpretation('');
    setTarotSummaryShort('');
    setPickedIndices(new Set());
    pickedIndicesRef.current = new Set();
    pickedCardsByIndexRef.current = new Map();
    setCinematicCards([]);
    setShowAnalysisCue(false);
    setCinematicRunId((id) => id + 1);
    basicPrePickedRef.current = null;
    setAnimatingSubPhase('picking');
    if (deckToUse?.id) setActiveDeckId(deckToUse.id);
    startSession(
      buildTarotSnapshot({
        spread: [],
        phase: 'animating',
        animatingSubPhase: 'picking',
        isDrawing: false,
        showAnalysisCue: false,
        dialogueRequired: false,
      })
    );
  };

  const handleStartSpread = async () => {
    if (!selectedSpreadId || !activeDeckId || isDrawing) return;
    if (cardPool.length === 0) {
      setOverallInterpretation('Колоды временно недоступны. Перезайдите в Таро через несколько секунд.');
      setSpreadFailed(true);
      return;
    }
    const ok = await validateQuestion();
    if (!ok) return;
    setQuestionError('');
    triggerHaptics('medium');

    if (selectedSpreadId !== 'single') {
      setTarologistPromptVariant((v) => v + 1);
      setTarologistMessages([]);
      setTarologistInput('');
      setPhase('chat');
      return;
    }

    doStartSpreadWithQuestion('');
  };

  const handleStartSpreadFromChat = async () => {
    const questionFromChat = tarologistBuildQuestionFromMessages(tarologistMessages);
    if (cardPool.length === 0) {
      setOverallInterpretation('Колоды временно недоступны. Перезайдите в Таро через несколько секунд.');
      setSpreadFailed(true);
      return;
    }
    await doStartSpreadWithQuestion(questionFromChat);
  };

  const handleStartSpreadFromChatWithMessages = async (messagesOverride = [], forcedQuestion = '') => {
    const source = Array.isArray(messagesOverride) && messagesOverride.length
      ? messagesOverride
      : (tarologistMessages || []);
    const questionFromChat = tarologistBuildQuestionFromMessages(source, forcedQuestion);
    if (cardPool.length === 0) {
      setOverallInterpretation('Колоды временно недоступны. Перезайдите в Таро через несколько секунд.');
      setSpreadFailed(true);
      return;
    }
    await doStartSpreadWithQuestion(questionFromChat);
  };

  const confirmTarotCostModal = () => {
    setShowTarotCostModal(false);
    if (!canStartTarotPaidFlow()) return;
    const deck = pendingDeckForCostModalRef.current;
    pendingDeckForCostModalRef.current = null;
    const run = pendingTarotRunRef.current;
    pendingTarotRunRef.current = null;
    if (deck) {
      skipSingleCostGateRef.current = true;
      void handleStartSpreadWithDeck(deck);
      return;
    }
    if (run) {
      skipSingleCostGateRef.current = true;
      void run();
    }
  };

  /** Закрыли чат с тарологом без расклада: возврат на выбор расклада (как стартовая страница Таро). */
  const exitTarologistChatToTarotHome = useCallback(() => {
    forceScrollTop();
    setSingleHidePickPortal(false);
    setSingleCardRevealResult(false);
    setSingleCardFly(null);
    clearSession();
    reset();
    questionRef.current = '';
    setQuestion('');
    setResultQuestion('');
    setQuestionError('');
    setSpreadFailed(false);
    setSpreadSize(selectedSpread.cards);
    setOverallInterpretation('');
    setTarotSummaryShort('');
    animatingStartedRef.current = false;
    guidedStepLockRef.current = false;
    setPhase('select');
    setTarotStep('spread');
    setAnimatingSubPhase('deck');
    setTarologistMessages([]);
    setTarologistInput('');
    setTarologistLoading(false);
    setTarologistPromptStage(false);
    setTarologistPromptVariant((v) => v + 1);
    drawRequestIdRef.current += 1;
    chatRequestIdRef.current += 1;
    creatingReadingPromiseRef.current = null;
    setFollowUpQuestions([]);
    setChatMessages([]);
    setReadingId('');
    setGuidedQuestions([]);
    setGuidedStep(0);
    setGuidedAnswers([]);
    setGuidedFinished(true);
    setDialogueRequired(false);
    setPracticalAdvice('');
    setShowFinalSummary(selectedSpread.cards < 6);
  }, [forceScrollTop, clearSession, reset, selectedSpread.cards]);

  const cancelTarotCostModal = () => {
    setShowTarotCostModal(false);
    pendingDeckForCostModalRef.current = null;
    pendingTarotRunRef.current = null;
    skipSingleCostGateRef.current = false;
    if (phase === 'chat') {
      exitTarologistChatToTarotHome();
    }
  };

  const doStartSpreadWithQuestion = async (questionFromChat) => {
    const q = String(questionFromChat || '').trim();
    questionRef.current = q;
    setQuestion(q);
    setResultQuestion(q);
    animatingStartedRef.current = false;
    setReadingId('');
    setFollowUpQuestions([]);
    setChatMessages([]);
    setGuidedQuestions([]);
    setGuidedStep(0);
    setGuidedAnswers([]);
    setGuidedFinished(true);
    setDialogueRequired(false);
    setPracticalAdvice('');
    setShowFinalSummary(true);
    const shuffled = shuffleArray(cardPool).map((c) => ({
      ...c,
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      astrovDeckId: activeDeck.id,
    }));
    setShuffledDeckForPick(shuffled);
    setSpread([]);
    setOverallInterpretation('');
    setTarotSummaryShort('');
    setPickedIndices(new Set());
    pickedIndicesRef.current = new Set();
    pickedCardsByIndexRef.current = new Map();
    setCinematicCards([]);
    setShowAnalysisCue(false);
    setCinematicRunId((id) => id + 1);
    basicPrePickedRef.current = null;

    if (selectedSpreadId === 'single') {
      setAnimatingSubPhase('picking');
      await waitForPaint();
      setPhase('animating');
      startSession(
        buildTarotSnapshot({
          question: q,
          spread: [],
          phase: 'animating',
          animatingSubPhase: 'picking',
          isDrawing: false,
          showAnalysisCue: false,
          dialogueRequired: false,
        })
      );
      return;
    }

    if (selectedSpreadId === 'three_cards') {
      setAnimatingSubPhase('picking');
      setPhase('animating');
      startSession(
        buildTarotSnapshot({
          question: q,
          spread: [],
          phase: 'animating',
          animatingSubPhase: 'picking',
          isDrawing: false,
          showAnalysisCue: false,
          dialogueRequired: false,
        })
      );
      return;
    }

    if (selectedSpreadId === 'financial' || selectedSpreadId === 'six_cards' || selectedSpreadId === 'ten_cards') {
      setAnimatingSubPhase('picking');
      setPhase('animating');
      startSession(
        buildTarotSnapshot({
          question: q,
          spread: [],
          phase: 'animating',
          animatingSubPhase: 'picking',
          isDrawing: false,
          showAnalysisCue: false,
          dialogueRequired: false,
        })
      );
      return;
    }

    setAnimatingSubPhase('cinematic');
    setPhase('animating');
    const selected = shuffled.slice(0, selectedSpread.cards).map((c) => ({
      ...c,
      is_reversed: allowReversed ? Math.random() < 0.5 : false,
    }));
    const selectedWithImages = await Promise.all(
      selected.map(async (card) => ({
        ...card,
        image: card?.image || (await resolveCardImage(card, activeDeck?.id)),
      }))
    );
    setPickedIndices(new Set(selectedWithImages.map((_, idx) => idx)));
    setCinematicCards(selectedWithImages);
    const initialSpread = selectedWithImages.map((card, idx) => ({
      ...card,
      astrovDeckId: activeDeck.id,
      card_id: (card?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
      card_name: resolveCardTitle(card?.id, card?.name, activeDeck.id),
      name: resolveCardTitle(card?.id, card?.name, activeDeck.id),
      position_name: currentPositions[idx] || `Позиция ${idx + 1}`,
      meaning: '',
      interpretation: '',
      loading: true,
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
      is_reversed: Boolean(card?.is_reversed),
    }));
    setSpread(initialSpread);
    startSession(
      buildTarotSnapshot({
        question: q,
        spread: initialSpread,
        phase: 'animating',
        animatingSubPhase: 'cinematic',
        isDrawing: true,
        showAnalysisCue: false,
        dialogueRequired: false,
      })
    );
    const revealMs = getCinematicTotalMs(selectedSpreadId, selectedSpread.cards);
    const minAnalyzeMs = TAROT_ANIM.ANALYSIS_MIN_MS ?? 1800;
    const waitMs = revealMs + minAnalyzeMs;
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const runPromise = runBatchReading(selectedWithImages, { needGuidedDialogue: false });
    setTimeout(() => {
      if (isMountedRef.current) setShowAnalysisCue(true);
      updateSession({
        showAnalysisCue: true,
        phase: 'animating',
        animatingSubPhase: 'cinematic',
        inProgress: true,
      });
    }, Math.max(900, revealMs - 120));
    await Promise.all([runPromise, sleep(waitMs)]);
    if (isMountedRef.current) {
      setShowAnalysisCue(false);
      setPhase('result');
    }
    finishSession({
      showAnalysisCue: false,
      phase: 'result',
      isDrawing: false,
      inProgress: false,
    });
  };

  const runBatchReading = async (selectedCards, options = {}) => {
    const requestId = ++drawRequestIdRef.current;
    const isStale = () => requestId !== drawRequestIdRef.current;
    const qForApi = (questionRef.current || question || '').trim();
    const autoNeedGuided = false;
    const needGuidedDialogue = typeof options.needGuidedDialogue === 'boolean'
      ? options.needGuidedDialogue
      : autoNeedGuided;
    const skipPhaseUpdate = Boolean(options.skipPhaseUpdate);
    const apiDeckId =
      selectedCards.find((c) => c?.astrovDeckId)?.astrovDeckId || activeDeck?.id || 'classic';
    const deckForApi = decks.find((d) => d.id === apiDeckId) || activeDeck;
    setDialogueRequired(needGuidedDialogue);
    setIsDrawing(true);
    setOverallInterpretation('');
    setPracticalAdvice('');
    setShowFinalSummary(selectedSpread.cards < 6 || !needGuidedDialogue);
    updateSession({
      ...(skipPhaseUpdate ? {} : { phase: 'animating' }),
      isDrawing: true,
      dialogueRequired: needGuidedDialogue,
      practicalAdvice: '',
      overallInterpretation: '',
      inProgress: true,
      ...(selectedCards?.length ? { spread: selectedCards } : {}),
    });
    const runLegacyFallback = async () => {
      const fallbackLocal =
        cardPool.length > 0 ? cardPool[Math.floor(Math.random() * cardPool.length)] : null;
      const sourceCards = selectedCards.length ? selectedCards : (fallbackLocal ? [fallbackLocal] : []);
      if (!sourceCards.length) {
        setSpread([]);
        setOverallInterpretation('Не удалось загрузить колоды. Обновите экран Таро и повторите попытку.');
        setSpreadFailed(true);
        return;
      }
      const deckId = apiDeckId;
      const deckColor = deckForApi?.color || '1f2937';
      const mapped = (
        await Promise.all(
          sourceCards.map(async (local, index) => {
            try {
              const res = await fetch(`${API_BASE}/api/tarot/draw`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  deck: deckId,
                  question: qForApi,
                  card_name: resolveCardTitle(local?.id, local?.name, deckId),
                  card_id: (local?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
                  position: index + 1,
                  total: sourceCards.length,
                  position_name: currentPositions[index] || `Позиция ${index + 1}`,
                  is_reversed: Boolean(local?.is_reversed),
                  init_data: getInitData(),
                  personalize: false,
                  profile_id: null,
                }),
              });
              const data = res.ok ? await res.json() : await res.json().catch(() => ({}));
              const cardImage = await resolveCardImage(local, apiDeckId);
              return {
                id: local?.id || data?.card_name || `legacy-${index}`,
                card_id: (local?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
                card_name: resolveCardTitle(local?.id, data?.card_name || local?.name, deckId),
                name: resolveCardTitle(local?.id, data?.card_name || local?.name, deckId),
                position_name: currentPositions[index] || `Позиция ${index + 1}`,
                meaning: data?.interpretation || 'Звезды молчат. Попробуйте ещё раз.',
                interpretation: data?.interpretation || 'Звезды молчат. Попробуйте ещё раз.',
                is_reversed: Boolean(local?.is_reversed),
                image: cardImage || local?.image || `https://placehold.co/300x500/${deckColor}/fbbf24?text=Tarot`,
                loading: false,
                astrovDeckId: deckId,
                backClass: deckForApi?.backClass,
                backImage: deckForApi?.backImage,
              };
            } catch {
              const cardImage = await resolveCardImage(local, apiDeckId);
              return {
                id: local?.id || `legacy-${index}`,
                card_id: (local?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
                card_name: resolveCardTitle(local?.id, local?.name, deckId),
                name: resolveCardTitle(local?.id, local?.name, deckId),
                position_name: currentPositions[index] || `Позиция ${index + 1}`,
                meaning: 'Не удалось получить толкование для этой карты.',
                interpretation: 'Не удалось получить толкование для этой карты.',
                is_reversed: Boolean(local?.is_reversed),
                image: cardImage || local?.image || `https://placehold.co/300x500/${deckColor}/fbbf24?text=Tarot`,
                loading: false,
                astrovDeckId: deckId,
                backClass: deckForApi?.backClass,
                backImage: deckForApi?.backImage,
              };
            }
          })
        )
      ).filter(Boolean);
      if (isStale()) return;
      setSpread(mapped);
      updateSession({ spread: mapped });
      if (needGuidedDialogue) {
        const prepared = buildGuidedQuestions([]);
        if (isStale()) return;
        setOverallInterpretation('');
        setTarotSummaryShort('');
        setGuidedQuestions(prepared);
        setGuidedStep(0);
        setGuidedAnswers([]);
        setGuidedFinished(false);
        setShowFinalSummary(false);
        setChatMessages([
          {
            role: 'assistant',
            content: `Ваш вопрос:\n${qForApi || 'Без уточнения вопроса.'}`,
          },
          {
            role: 'assistant',
            content: `Вопрос таролога 1/${prepared.length}:\n${prepared[0]}\nОтветьте сообщением в чате ниже.`,
          },
        ]);
      } else {
        try {
          const summaryRes = await fetch(`${API_BASE}/api/tarot/draw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              deck: apiDeckId,
              question: `Общий итог расклада. Вопрос: ${qForApi || 'без вопроса'}. Карты: ${mapped.map((c) => c?.name).join(', ')}.`,
              card_name: 'Общий расклад',
              is_reversed: false,
              init_data: getInitData(),
              personalize: false,
              profile_id: null,
            }),
          });
          const summaryData = summaryRes.ok ? await summaryRes.json() : await summaryRes.json().catch(() => ({}));
          if (isStale()) return;
          setOverallInterpretation(summaryData?.interpretation || 'Расклад выполнен. Перечитайте трактовки карт выше.');
          setPracticalAdvice(
            selectedSpreadId === 'financial'
              ? [
                  'Сделайте один проверяемый денежный шаг в ближайшие дни и оцените эффект цифрами.',
                  'На этой неделе сфокусируйтесь на одном источнике дохода или одном ограничении расходов.',
                  'Опираясь на расклад: выберите один приоритетный шаг по деньгам и зафиксируйте результат.',
                  'Исходя из карт: наметьте конкретное действие по финансам и проверьте итог по факту.',
                ][Math.floor(Math.random() * 4)]
              : ''
          );
        } catch {
          if (isStale()) return;
          setOverallInterpretation('Расклад выполнен. Перечитайте трактовки карт выше.');
          setPracticalAdvice(
            selectedSpreadId === 'financial'
              ? [
                  'На этой неделе сфокусируйтесь на одном источнике дохода и одном ограничении расходов.',
                  'Опираясь на расклад: выберите один приоритетный денежный шаг и зафиксируйте результат.',
                  'Исходя из карт: наметьте конкретное действие по финансам и проверьте итог.',
                ][Math.floor(Math.random() * 3)]
              : ''
          );
        }
        if (isStale()) return;
        setGuidedQuestions([]);
        setGuidedStep(0);
        setGuidedAnswers([]);
        setGuidedFinished(true);
        setShowFinalSummary(true);
      }
      if (isStale()) return;
      setSpreadFailed(false);
    };
    try {
      const cardsPayload = selectedCards.map((c, index) => ({
        card_id: (c?.card_id || c?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
        card_name: c?.card_name || resolveCardTitle(c?.id, c?.name, apiDeckId),
        position: index,
        position_name: currentPositions[index] || `Позиция ${index + 1}`,
        is_reversed: Boolean(c?.is_reversed),
        image: c?.image || '',
      }));
      const doFetch = (signal) => fetch(`${API_BASE}/api/tarot/draw-batch`, {
        signal,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          init_data: getInitData(),
          profile_id: null,
          personalize: false,
            spread_code: selectedSpreadId,
            question: qForApi,
            cards: cardsPayload,
            allow_reversed: allowReversed,
            deck: apiDeckId,
            deck_card_ids:
              selectedSpread.cards === 1
                ? (decks.find((d) => d.id === apiDeckId)?.cards || cardPool).map((c) => String(c.id))
                : [],
            deck_card_names:
              selectedSpread.cards === 1
                ? Object.fromEntries(
                    (decks.find((d) => d.id === apiDeckId)?.cards || cardPool).map((c) => [
                      String(c.id),
                      resolveCardTitle(c.id, c.name, apiDeckId),
                    ])
                  )
                : {},
        }),
      });
      const FETCH_TIMEOUT_MS = 70000;
      let res;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
        try {
          res = await doFetch(controller.signal);
          clearTimeout(timeoutId);
          break;
        } catch (err) {
          clearTimeout(timeoutId);
          const retriable = err?.name === 'AbortError' || err?.name === 'TypeError';
          if (!retriable || attempt >= 1) throw err;
          await new Promise((resolve) => setTimeout(resolve, 250));
        }
      }
      if (!res) {
        throw new Error('Не удалось подключиться. Проверьте интернет и повторите.');
      }
      const data = res.ok ? await res.json() : await res.json().catch(() => ({}));
      if (isStale()) return;
      if (!res.ok) {
        const msg = res.status === 503 ? 'Система перегружена. Повторите попытку позже.' : (data?.detail || 'Не удалось получить расклад.');
        const err = new Error(msg);
        err.status = res.status;
        throw err;
      }
      refetchAuth?.();
      setReadingId(data?.reading_id || '');
      const aiQuestions = Array.isArray(data?.follow_up_questions) ? data.follow_up_questions : [];
      setFollowUpQuestions(aiQuestions);
      setPracticalAdvice(data?.advice || '');
      const byPosition = (data?.cards_interpretations || []).slice().sort((a, b) => (a.position ?? 0) - (b.position ?? 0));
      const interpByPosition = new Map();
      byPosition.forEach((item, idx) => {
        const pos = Number.isFinite(Number(item?.position)) ? Number(item.position) : idx;
        if (!interpByPosition.has(pos)) interpByPosition.set(pos, item);
      });
      const interpByCardKey = new Map();
      byPosition.forEach((item) => {
        const key = normalizeCardKey(item?.card_id || item?.card_name);
        if (key && !interpByCardKey.has(key)) interpByCardKey.set(key, item);
      });
      debugTarotMapping('before-map', {
        spread: selectedSpreadId,
        selectedCards: selectedCards.map((c, i) => ({
          i,
          id: c?.id,
          name: c?.name,
          card_name: c?.card_name,
          is_reversed: c?.is_reversed,
        })),
        responseCards: byPosition.map((item, i) => ({
          i,
          position: item?.position,
          card_id: item?.card_id,
          card_name: item?.card_name,
          is_reversed: item?.is_reversed,
        })),
      });
      const mapped = await Promise.all(
        selectedCards.map(async (local, index) => {
          const cardKey = normalizeCardKey(local?.id ?? local?.name);
          const item =
            (cardKey ? interpByCardKey.get(cardKey) : null) ||
            interpByPosition.get(index) ||
            byPosition[index] ||
            {};
          const apiCardId = String(item?.card_id || '').trim();
          const normalizedApiCardId = apiCardId.replace(/\.(jpg|jpeg|png|webp)$/i, '');
          const byApiId =
            selectedSpreadId === 'single' && normalizedApiCardId
              ? (deckForApi?.cards || []).find(
                  (dc) => normalizeCardKey(dc?.id) === normalizeCardKey(normalizedApiCardId)
                )
              : null;
          const resolvedLocal = byApiId
            ? {
                ...local,
                ...byApiId,
                id: byApiId.id || local?.id,
                name: byApiId.name || local?.name,
              }
            : (selectedSpreadId === 'single'
                ? {
                    ...local,
                    id: normalizedApiCardId || local?.id,
                    name: item?.card_name || local?.name,
                    image: '',
                  }
                : local);
          const cardImage = await resolveCardImage(resolvedLocal, apiDeckId);
          const cardIdForView =
            selectedSpreadId === 'single' && normalizedApiCardId
              ? normalizedApiCardId
              : (resolvedLocal?.id || item?.card_id || `mapped-${index}`);
          const fallbackLabel = (resolvedLocal?.name || item?.card_name || item?.card_id || 'Карта').toString().slice(0, 30);
          const displayName = resolveCardTitle(
            cardIdForView,
            resolvedLocal?.name || item?.card_name,
            apiDeckId
          );
          return {
            id: cardIdForView,
            card_id: cardIdForView,
            astrovDeckId: apiDeckId,
            card_name: displayName,
            name: displayName,
            position_name: item?.position_name || currentPositions[index] || `Позиция ${index + 1}`,
            meaning: item?.interpretation || resolvedLocal?.meaning || 'Интерпретация уточняется.',
            interpretation: item?.interpretation || resolvedLocal?.interpretation || resolvedLocal?.meaning || 'Интерпретация уточняется.',
            is_reversed: selectedSpreadId === 'single'
              ? Boolean(item?.is_reversed)
              : Boolean(resolvedLocal?.is_reversed),
            image: cardImage || resolvedLocal?.image || `https://placehold.co/300x500/${deckForApi.color}/fbbf24?text=${encodeURIComponent(fallbackLabel)}`,
            loading: false,
            backClass: deckForApi.backClass,
            backImage: deckForApi.backImage,
          };
        })
      );
      debugTarotMapping('after-map', {
        spread: selectedSpreadId,
        mapped: mapped.map((c, i) => ({
          i,
          id: c?.id,
          card_id: c?.card_id,
          card_name: c?.card_name,
          position_name: c?.position_name,
          is_reversed: c?.is_reversed,
        })),
      });
      if (import.meta.env.DEV) {
        mapped.forEach((mappedCard, idx) => {
          if (selectedSpreadId === 'single') return;
          const expected = selectedCards[idx];
          const expectedId = String(expected?.id || '').trim();
          const actualId = String(mappedCard?.id || mappedCard?.card_id || '').trim();
          if (!expectedId || !actualId) return;
          if (expectedId !== actualId) {
            console.error('[tarot-map] mismatch', {
              spread: selectedSpreadId,
              index: idx,
              expected: {
                id: expected?.id,
                name: expected?.name,
                card_name: expected?.card_name,
                is_reversed: expected?.is_reversed,
              },
              actual: {
                id: mappedCard?.id,
                card_id: mappedCard?.card_id,
                card_name: mappedCard?.card_name,
                position_name: mappedCard?.position_name,
                is_reversed: mappedCard?.is_reversed,
              },
              responseItem: byPosition[idx],
            });
          }
        });
      }
      if (isStale()) return;
      setSpread(mapped);
      updateSession({ spread: mapped });
      if (!needGuidedDialogue) {
        setOverallInterpretation(data?.overall || data?.summary || '');
        setTarotSummaryShort(data?.summary || '');
      }
      if (needGuidedDialogue) {
        const prepared = buildGuidedQuestions(aiQuestions);
        setGuidedQuestions(prepared);
        setGuidedStep(0);
        setGuidedAnswers([]);
        setGuidedFinished(false);
        setShowFinalSummary(false);
        setChatMessages([
          {
            role: 'assistant',
            content: `Ваш вопрос:\n${qForApi || 'Без уточнения вопроса.'}`,
          },
          {
            role: 'assistant',
            content: `Вопрос таролога 1/${prepared.length}:\n${prepared[0]}\nОтветьте сообщением в чате ниже.`,
          },
        ]);
      } else {
        setGuidedQuestions([]);
        setGuidedStep(0);
        setGuidedAnswers([]);
        setGuidedFinished(true);
      }
      if (isStale()) return;
      setSpreadFailed(false);
      const initialChatForGuided = needGuidedDialogue && (() => {
        const gq = buildGuidedQuestions(aiQuestions);
        if (gq.length === 0) return undefined;
        return [
          { role: 'assistant', content: `Ваш вопрос:\n${qForApi || 'Без уточнения вопроса.'}` },
          { role: 'assistant', content: `Вопрос таролога 1/${gq.length}:\n${gq[0]}\nОтветьте сообщением в чате ниже.` },
        ];
      })();
      updateSession({
        spread: mapped,
        readingId: data?.reading_id || '',
        followUpQuestions: aiQuestions,
        practicalAdvice: data?.advice || '',
        overallInterpretation: needGuidedDialogue ? '' : (data?.overall || data?.summary || ''),
        tarotSummaryShort: needGuidedDialogue ? '' : (data?.summary || ''),
        guidedQuestions: needGuidedDialogue ? buildGuidedQuestions(aiQuestions) : [],
        guidedStep: 0,
        guidedAnswers: [],
        guidedFinished: !needGuidedDialogue,
        dialogueRequired: needGuidedDialogue,
        showFinalSummary: !needGuidedDialogue,
        spreadFailed: false,
        isDrawing: true,
        inProgress: true,
        ...(initialChatForGuided ? { chatMessages: initialChatForGuided } : {}),
      });
    } catch (e) {
      const status = Number(e?.status || 0);
      const detail = String(e?.message || '').trim();
      const preserveCardsWithError = async (errorText) => {
        if (isStale() || !selectedCards?.length) return;
        const preserved = await Promise.all(
          selectedCards.map(async (c, idx) => ({
            id: c?.id || `err-${idx}`,
            card_id: (c?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
            astrovDeckId: apiDeckId,
            card_name: resolveCardTitle(c?.id, c?.name, apiDeckId),
            name: resolveCardTitle(c?.id, c?.name, apiDeckId),
            position_name: currentPositions[idx] || `Позиция ${idx + 1}`,
            meaning: errorText,
            interpretation: errorText,
            is_reversed: Boolean(c?.is_reversed),
            image: c?.image || (await resolveCardImage(c, apiDeckId)) || `https://placehold.co/300x500/${deckForApi?.color || '1f2937'}/fbbf24?text=Tarot`,
            loading: false,
            backClass: deckForApi?.backClass,
            backImage: deckForApi?.backImage,
          }))
        );
        if (isStale()) return;
        setSpread(preserved);
        updateSession({ spread: preserved });
      };
      if (status === 503) {
        if (isStale()) return;
        await preserveCardsWithError('Система перегружена. Повторите попытку позже.');
        setSpreadFailed(true);
        setOverallInterpretation('Система перегружена. Повторите попытку позже.');
        return;
      }
      if (status === 403) {
        if (isStale()) return;
        const limitText = detail || TAROT_DAILY_LIMIT_MESSAGE;
        await preserveCardsWithError(limitText);
        setSpreadFailed(true);
        setOverallInterpretation(limitText);
        await refetchAuth().catch(() => {});
        return;
      }
      if (status === 401) {
        if (isStale()) return;
        await preserveCardsWithError(detail || 'Откройте приложение из Telegram и повторите попытку.');
        setSpreadFailed(true);
        setOverallInterpretation(detail || 'Откройте приложение из Telegram и повторите попытку.');
        return;
      }
      try {
        await runLegacyFallback();
      } catch {
        if (isStale()) return;
        const errMsg = 'Сервис временно недоступен. Попробуйте ещё раз.';
        if (selectedCards?.length) {
          await preserveCardsWithError(errMsg);
          setOverallInterpretation(errMsg);
        } else {
          setSpread([]);
          updateSession({ spread: [] });
          setOverallInterpretation('Не удалось загрузить колоды. Обновите экран Таро и повторите попытку.');
        }
        setSpreadFailed(true);
      }
    } finally {
      // Даже при stale/размонтаже завершаем фоновую сессию, чтобы не зависать в "Идёт анализ..."
      if (!isStale() && isMountedRef.current) setIsDrawing(false);
      finishSession({ isDrawing: false, inProgress: false });
    }
  };
  runBatchReadingRef.current = runBatchReading;

  const ensureReadingForChat = async () => {
    if (readingId) return readingId;
    if (selectedSpread.cards < 6 || !Array.isArray(spread) || spread.length === 0) return '';
    if (creatingReadingPromiseRef.current) return creatingReadingPromiseRef.current;
    const cardsPayload = spread.map((c, index) => ({
      card_id: String(c?.card_id || c?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
      card_name: c?.card_name || c?.name || '',
      position: index,
      position_name: c?.position_name || currentPositions[index] || `Позиция ${index + 1}`,
      is_reversed: Boolean(c?.is_reversed),
      image: c?.image || '',
    }));
    creatingReadingPromiseRef.current = (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/tarot/draw-batch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            init_data: getInitData(),
            profile_id: null,
            personalize: false,
            spread_code: selectedSpreadId,
            question: (questionRef.current || question || '').trim(),
            cards: cardsPayload,
            allow_reversed: allowReversed,
            deck: activeDeck?.id,
            deck_card_ids: [],
          }),
        });
        const data = res.ok ? await res.json() : await res.json().catch(() => ({}));
        if (!res.ok || !data?.reading_id) return '';
        refetchAuth?.();
        setReadingId(data.reading_id);
        if (Array.isArray(data?.follow_up_questions)) setFollowUpQuestions(data.follow_up_questions);
        if (data?.advice) setPracticalAdvice(data.advice);
        return data.reading_id;
      } catch {
        return '';
      } finally {
        creatingReadingPromiseRef.current = null;
      }
    })();
    return creatingReadingPromiseRef.current;
  };

  const loadStats = async () => {
    try {
      const query = new URLSearchParams({
        init_data: getInitData(),
      });
      if (activeProfileId != null) query.set('profile_id', String(activeProfileId));
      const res = await fetch(`${API_BASE}/api/tarot/stats?${query.toString()}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || 'Не удалось получить статистику.');
      setStatsData(data || null);
      setShowStats(true);
    } catch {
      setStatsData(null);
      setShowStats(true);
    }
  };

  const sendChatMessage = async (message) => {
    if (chatLoading) return;
    const inGuidedFlow = dialogueRequired && !guidedFinished && guidedQuestions.length > 0;

    if (inGuidedFlow) {
      if (guidedStepLockRef.current) return;
      guidedStepLockRef.current = true;
      setChatMessages((prev) => [...prev, { role: 'user', content: message }]);
      const nextAnswers = [...guidedAnswers, message];
      setGuidedAnswers(nextAnswers);

      const nextStep = guidedStep + 1;
      if (nextStep < guidedQuestions.length) {
        setGuidedStep(nextStep);
        setChatMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `Вопрос таролога ${nextStep + 1}/${guidedQuestions.length}:\n${guidedQuestions[nextStep]}\nОтветьте сообщением в чате ниже.` },
        ]);
        setShowFinalSummary(false);
        guidedStepLockRef.current = false;
        return;
      }

      setGuidedFinished(true);
      setShowFinalSummary(false);
      setChatLoading(true);
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Спасибо. Учитываю ответы и собираю итог расклада...' },
      ]);

      const chatReqId = ++chatRequestIdRef.current;
      try {
        const chatReadingId = await ensureReadingForChat();
        if (!chatReadingId) {
          setChatMessages((prev) => [
            ...prev,
            { role: 'assistant', content: 'Не удалось подготовить диалог. Нажмите "Получить итог расклада".' },
          ]);
          guidedStepLockRef.current = false;
          return;
        }

        const dialogContext = guidedQuestions
          .map((q, i) => `${i + 1}) ${q}\nОтвет: ${nextAnswers[i] || '-'}`)
          .join('\n\n');
        const cardsContext = (spread || [])
          .map((c, i) => {
            const label = getCardDisplayName(c) || c?.card_name || c?.name || `Карта ${i + 1}`;
            const pos = c?.position_name || currentPositions[i] || `Позиция ${i + 1}`;
            const orient = c?.is_reversed ? 'перевёрнутая' : 'прямая';
            return `${i + 1}) ${label} - ${pos} - ${orient}`;
          })
          .join('\n');

        const res = await fetch(`${API_BASE}/api/tarot/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            init_data: getInitData(),
            reading_id: chatReadingId,
            message: `Контекст перед итогом расклада:\n${dialogContext}\n\nВыпавшие карты и позиции:\n${cardsContext}\n\nСформируй финальный вывод именно как интерпретацию Таро-расклада: опирайся на значения выпавших карт и их позиции, свяжи карты между собой, покажи причинно-следственную динамику и заверши практическим выводом. Не отвечай как общий совет на вопросы - отвечай как таролог по картам.`,
          }),
        });
        const data = await res.json();
        if (chatReqId !== chatRequestIdRef.current) return;
        if (!res.ok) throw new Error(data?.detail || 'Ошибка ответа.');

        if (data?.updated_advice) setPracticalAdvice(data.updated_advice);
        setOverallInterpretation(data?.response || data?.updated_advice || '');
        setShowFinalSummary(true);
        setChatMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Итог расклада готов. Смотрите блок «Итоговый расклад» выше.' },
        ]);
      } catch {
        if (chatReqId === chatRequestIdRef.current) {
        setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Не удалось сформировать итог по диалогу. Попробуйте еще раз.' }]);
        }
      } finally {
        setChatLoading(false);
        guidedStepLockRef.current = false;
      }
      return;
    }

    const chatReqId = ++chatRequestIdRef.current;
    const chatReadingId = await ensureReadingForChat();
    if (!chatReadingId) {
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Не удалось подготовить диалог. Нажмите "Получить итог расклада" или начните новый расклад.' },
      ]);
      return;
    }
    setChatMessages((prev) => [...prev, { role: 'user', content: message }]);
    setChatLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/tarot/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          init_data: getInitData(),
          reading_id: chatReadingId,
          message,
        }),
      });
      const data = await res.json();
      if (chatReqId !== chatRequestIdRef.current) return;
      if (!res.ok) throw new Error(data?.detail || 'Ошибка ответа.');
      const history = Array.isArray(data?.chat_history) ? data.chat_history : [];
      if (history.length) {
        setChatMessages(history);
      } else if (typeof data?.response === 'string' && data.response.trim()) {
        setChatMessages((prev) => [...prev, { role: 'assistant', content: data.response.trim() }]);
      }
      if (Array.isArray(data?.new_questions) && data.new_questions.length) {
        setFollowUpQuestions(data.new_questions);
      }
      if (data?.updated_advice) {
        setPracticalAdvice(data.updated_advice);
        setOverallInterpretation((prev) => prev || data.updated_advice);
      }
      setShowFinalSummary(true);
    } catch {
      if (chatReqId !== chatRequestIdRef.current) return;
      setChatMessages((prev) => [...prev, { role: 'assistant', content: 'Не удалось ответить. Попробуйте еще раз.' }]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleRetryCard = async () => {
    const selectedCards = spread.map((c) => ({ id: c.id, name: c.name, image: c.image }));
    await runBatchReading(selectedCards, { needGuidedDialogue: false });
  };

  const handleBackFromPicking = useCallback(() => {
    forceScrollTop();
    setSingleHidePickPortal(false);
    setSingleCardRevealResult(false);
    setSingleCardFly(null);
    clearSession();
    reset();
    setSpread([]);
    setTarotStep('spread');
    setShuffledDeckForPick([]);
    setCinematicCards([]);
    setShowAnalysisCue(false);
    setIsDrawing(false);
    setPhase('select');
    setAnimatingSubPhase('deck');
    setPickedIndices(new Set());
    pickedIndicesRef.current = new Set();
    pickedCardsByIndexRef.current = new Map();
    drawRequestIdRef.current += 1;
    chatRequestIdRef.current += 1;
    creatingReadingPromiseRef.current = null;
    basicPrePickedRef.current = null;
    forceScrollTop();
  }, [clearSession, reset, forceScrollTop]);

  const handleNewSpread = () => {
    forceScrollTop();
    setSingleHidePickPortal(false);
    setSingleCardRevealResult(false);
    setSingleCardFly(null);
    clearSession();
    reset();
    questionRef.current = '';
    setQuestion('');
    setResultQuestion('');
    setSpreadSize(selectedSpread.cards);
    setOverallInterpretation('');
    setTarotSummaryShort('');
    setSpreadFailed(false);
    setPhase('select');
    setTarotStep('spread');
    setAnimatingSubPhase('deck');
    setPickedIndices(new Set());
    pickedIndicesRef.current = new Set();
    pickedCardsByIndexRef.current = new Map();
    animatingStartedRef.current = false;
    setReadingId('');
    creatingReadingPromiseRef.current = null;
    guidedStepLockRef.current = false;
    drawRequestIdRef.current += 1;
    chatRequestIdRef.current += 1;
    setFollowUpQuestions([]);
    setChatMessages([]);
    setGuidedQuestions([]);
    setGuidedStep(0);
    setGuidedAnswers([]);
    setGuidedFinished(true);
    setDialogueRequired(false);
    setPracticalAdvice('');
    setTenCardMode('consult');
    setShowFinalSummary(selectedSpread.cards < 6);
    const t1 = setTimeout(forceScrollTop, 30);
    const t2 = setTimeout(forceScrollTop, 140);
    const t3 = setTimeout(forceScrollTop, 320);
    setTimeout(() => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    }, 400);
  };

  const handleCardSelect = async (card, slotIndex) => {
    const prev = pickedIndicesRef.current;
    if (prev.has(slotIndex) || prev.size >= selectedSpread.cards) return;

    const next = new Set(prev);
    next.add(slotIndex);
    pickedIndicesRef.current = next;
    setPickedIndices(next);

    const posIndex = next.size;
    const posName = currentPositions[posIndex - 1];
    const withReversed = {
      ...card,
      is_reversed: allowReversed ? Math.random() < 0.5 : false,
    };
    const resolvedImage = withReversed?.image || await resolveCardImage(withReversed, activeDeck?.id);
    const resolvedCard = {
      ...withReversed,
      image: resolvedImage || withReversed?.image || '',
      imageLoader: withReversed?.imageLoader,
      card_id: (withReversed?.id || '').replace(/\.(jpg|jpeg|png|webp)$/i, ''),
      astrovDeckId: activeDeck.id,
      card_name: resolveCardTitle(withReversed?.id, withReversed?.name, activeDeck.id),
      name: resolveCardTitle(withReversed?.id, withReversed?.name, activeDeck.id),
      position_name: posName,
      loading: true,
      meaning: '',
      backClass: activeDeck.backClass,
      backImage: activeDeck.backImage,
    };

    pickedCardsByIndexRef.current.set(slotIndex, resolvedCard);
    triggerHaptics('medium');
    setSpread((s) => {
      const arr = [...s];
      arr[posIndex - 1] = resolvedCard;
      return arr;
    });

      if (posIndex === selectedSpread.cards) {
      const ordered = [...next]
        .map((idx) => pickedCardsByIndexRef.current.get(idx) || shuffledDeckForPick[idx])
        .slice(0, selectedSpread.cards);

      if (
        selectedSpreadId === 'three_cards'
        || selectedSpreadId === 'single'
        || selectedSpreadId === 'financial'
        || selectedSpreadId === 'six_cards'
        || selectedSpreadId === 'ten_cards'
      ) {
        const revealDelayMs = selectedSpreadId === 'single' ? 320 : 1450;
        const minAnalyzeMs = selectedSpreadId === 'single'
          ? 220
          : (TAROT_ANIM.ANALYSIS_MIN_MS ?? 1800);
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        setAnimatingSubPhase('flipping');
        setTimeout(() => {
          if (!isMountedRef.current) return;
          setShowAnalysisCue(true);
          updateSession({
            showAnalysisCue: true,
            phase: 'animating',
            animatingSubPhase: 'flipping',
            inProgress: true,
            spread: ordered,
          });
        }, selectedSpreadId === 'single' ? 140 : Math.max(900, revealDelayMs - 180));
        const runPromise = runBatchReading(
          ordered,
          selectedSpreadId === 'ten_cards' ? {} : { needGuidedDialogue: false }
        );
        const minDisplayMs = revealDelayMs + minAnalyzeMs;
        try {
          await Promise.all([runPromise, sleep(minDisplayMs)]);
        } catch {
          // runBatchReading handles errors and sets spread
        }
        if (isMountedRef.current) {
          if (selectedSpreadId === 'single' && singleCardDailyFreeRef.current) {
            markSingleCardFreeUsedToday();
            singleCardDailyFreeRef.current = false;
          }
          setShowAnalysisCue(false);
          if (selectedSpreadId === 'single') {
            // Убираем полёт оверлея: он даёт редкий flash на стыке animating->result.
            setSingleCardFly(null);
            setSingleCardRevealResult(false);
            setSingleHidePickPortal(true);
          }
          setPhase('result');
          finishSession({
            showAnalysisCue: false,
            phase: 'result',
            isDrawing: false,
            inProgress: false,
          });
        }
      } else {
        setAnimatingSubPhase('deckExiting');
        setTimeout(() => setAnimatingSubPhase('formation'), 620);
        setTimeout(() => setAnimatingSubPhase('uniteFlip'), 1380);
        setTimeout(() => {
          setPhase('result');
          finishSession({
            phase: 'result',
            isDrawing: false,
            inProgress: false,
          });
        }, 2380);
        setTimeout(() => {
          runBatchReading(ordered, { needGuidedDialogue: false });
        }, 280);
      }
    }
  };

  return (
    <div
      className="relative flex min-h-0 flex-1 flex-col gap-0 tarot-scrollless h-full"
      style={{ overscrollBehavior: 'none' }}
    >
      <div ref={vantaRef} className="pointer-events-none fixed inset-0 opacity-45 -z-10" />
      <div className="pointer-events-none fixed inset-0 tarot-fog-particles -z-10" />
      <div className="pointer-events-none fixed inset-0 tarot-fog-particles tarot-fog-particles--deep -z-10" />
      <div
        className="pointer-events-none fixed inset-0 -z-10"
        style={{
          background: `radial-gradient(circle at 50% 36%, ${spreadPulseColor} 0%, transparent 55%)`,
          mixBlendMode: 'screen',
          opacity: 0.14,
        }}
      />

      {(phase === 'animating' ||
        (phase === 'select' && tarotStep === 'deck')) ? (
        <div
          className="fixed left-0 right-0 top-0 z-[250] flex items-start justify-start pointer-events-none px-3"
          style={{ paddingTop: TAROT_BACK_BELOW_TG_HEADER }}
        >
          <TarotBackNavButton
            onClick={() => {
              if (phase === 'animating') handleBackFromPicking();
              else if (phase === 'select' && tarotStep === 'deck') setTarotStep('spread');
            }}
          />
        </div>
      ) : null}

      <AnimatePresence mode="sync">
      {(phase === 'select' && spread.length === 0) ? (
        <motion.div
          key="screen-select"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={(skipSingleSelectTransitionRef.current || selectedSpreadId === 'single') ? { opacity: 1 } : { opacity: 0 }}
          transition={(skipSingleSelectTransitionRef.current || selectedSpreadId === 'single')
            ? { duration: 0 }
            : { duration: 0.22, ease: [0.32, 0.72, 0.36, 1] }}
          className="flex flex-col px-3 flex-1 min-h-0 overflow-x-visible overflow-y-hidden tarot-select-fixed"
          style={{ paddingBottom: 'max(5rem, calc(env(safe-area-inset-bottom) + 4rem))' }}
        >
          <div
            className="relative flex items-center justify-center mb-1 min-h-[3.5rem] -mt-2"
            style={{
              perspective: '600px',
              /* Как раньше: только отступ от потока, без второго calc под «Закрыть» (он уже в padding main). */
              marginTop: '1.35cm',
            }}
          >
            <motion.h1
              className="font-tarot-title"
              style={{
                fontSize: '2.25rem',
                textShadow: '0 0 20px currentColor, 0 0 40px currentColor',
                filter: 'drop-shadow(0 0 15px currentColor)',
              }}
              animate={{
                y: [0, -10, 0],
                rotateX: [0, 2, -2, 0],
                rotateY: [0, 1, -1, 0],
                color: ['#fde68a', '#e5a011', '#fde68a'],
              }}
              transition={{
                y: { duration: 4, repeat: Infinity, ease: 'easeInOut' },
                rotateX: { duration: 4, repeat: Infinity, ease: 'easeInOut' },
                rotateY: { duration: 4, repeat: Infinity, ease: 'easeInOut' },
                color: { duration: 5, repeat: Infinity, ease: 'easeInOut' },
              }}
            >
              ТАРО
            </motion.h1>
          </div>

          {tarotStep === 'spread' ? (
            <div className="flex-1 min-h-0 flex flex-col relative overflow-x-visible">
              {(() => {
                const h = SPREAD_PICKER_HINTS[selectedSpreadId];
                const spread = SPREADS.find((s) => s.id === selectedSpreadId);
                const name = spread?.name || h?.line1 || '';
                const cardSize = { w: Math.round(spreadPickerCardSize.w * 1.17), h: Math.round(spreadPickerCardSize.h * 1.17) };
                return (
                  <>
                    <div className="flex-1 min-h-0 overflow-hidden overflow-x-hidden pr-2 -mr-2 tarot-select-fixed">
                      <div className="flex-shrink-0 mb-2 mt-1 pb-[11rem]">
                        {h ? (
                          <div className="w-full flex flex-col items-center" style={{ fontFamily: "'Bion', sans-serif" }}>
                            <p
                              className="font-tarot-title text-center mb-2 uppercase"
                              style={{
                                fontSize: 'calc(2.25rem - 1pt)',
                                color: '#e5a011',
                                textShadow: '0 0 8px rgba(229,160,17,0.35), 0 0 16px rgba(229,160,17,0.2)',
                                filter: 'drop-shadow(0 0 5px rgba(229,160,17,0.3))',
                              }}
                            >
                              {h.line1Lines ? h.line1Lines.map((ln, i) => <span key={i}>{ln}{i < h.line1Lines.length - 1 ? <br /> : null}</span>) : name}
                            </p>
                            <div
                              className={cn(
                                'w-full text-center px-2 mb-3 mt-0',
                                selectedSpreadId === 'ten_cards' ? 'max-w-[min(22rem,90vw)]' : 'max-w-[min(18rem,85vw)]',
                              )}
                            >
                              {h.cardsLabel ? (
                                <p className="font-semibold text-sm tracking-wide" style={{ color: '#e5a011' }}>{h.cardsLabel}</p>
                              ) : null}
                              {h.description ? (
                                <p className="text-white/90 text-xs leading-snug mt-1">{h.description}</p>
                              ) : null}
                              {h.descriptionLines?.length ? (
                                <p className="text-white/90 text-xs leading-snug mt-1">
                                  {h.descriptionLines.map((ln, i) => (
                                    <span key={i}>{ln}{i < h.descriptionLines.length - 1 ? <br /> : null}</span>
                                  ))}
                                </p>
                              ) : null}
                              {h.descriptionExtra ? (
                                <p className="text-white/90 text-xs leading-snug mt-1">{h.descriptionExtra}</p>
                              ) : null}
                              {h.footer ? (
                                <p className="text-white/75 text-[11px] leading-snug mt-2">{h.footer}</p>
                              ) : null}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                    <div
                      className="absolute left-1/2 -translate-x-1/2 bottom-[9.9rem] w-[calc(100vw+96px)] min-w-[100vw] px-6 pt-2 pb-2 overflow-visible"
                      style={{ top: 'auto' }}
                    >
                      <SimpleSwipePicker
                        items={spreadPickerItems}
                        selectedId={selectedSpreadId}
                        onSelect={handleSpreadPickerSelect}
                        selectByCenter
                        hapticOnCenterSelect
                        itemWidth={cardSize.w}
                        itemHeight={cardSize.h}
                        gap={spreadGapPx}
                        scaleSelected={1.08}
                        levitate
                        levitateChaotic
                        swayPx={0}
                        useDistanceScaling
                        immediateNeighborScale={0.8}
                        immediateNeighborDistanceFactor={0.965}
                        secondNeighborScale={0.64}
                        secondNeighborPullPx={0}
                        secondNeighborDistanceFactor={0.76}
                        overflowVisible
                        edgePadding={typeof window !== 'undefined' ? Math.max(40, Math.floor(window.innerWidth / 2 - cardSize.w / 2)) : 80}
                        renderItem={(s) => {
                          if (s.id === 'magic_ball') {
                            return (
                              <div className="w-full rounded-[12px] overflow-hidden flex items-center justify-center" style={{ height: cardSize.h }}>
                                <div
                                  className="relative flex items-center justify-center w-[78%] aspect-square rounded-full"
                                  style={{
                                    background: 'radial-gradient(circle at 35% 30%, #2a2e38, #1a1e25 50%, #0c0f14)',
                                    boxShadow: 'inset -6px -6px 18px rgba(0,0,0,0.5), 0 12px 24px rgba(0,0,0,0.35)',
                                  }}
                                >
                                  <div
                                    className="w-[42%] aspect-square rounded-full"
                                    style={{
                                      background: 'linear-gradient(180deg, #2f79ff 0%, #1b53ff 50%, #1532d8 100%)',
                                      boxShadow: 'inset 0 0 16px rgba(47,121,255,0.4)',
                                    }}
                                  />
                                </div>
                              </div>
                            );
                          }
                          const imgSrc = SPREAD_IMAGE_MAP[s.id];
                          return (
                            <div className="w-full rounded-[12px] overflow-hidden flex items-center justify-center" style={{ height: cardSize.h }}>
                              {!spreadImgBroken[s.id] ? (
                                <img
                                  src={imgSrc}
                                  alt={s.name}
                                  className="w-full h-full object-contain object-top block [backface-visibility:hidden] [transform:translateZ(0)] will-change-transform"
                                  onError={() => setSpreadImgBroken((prev) => ({ ...prev, [s.id]: true }))}
                                />
                              ) : (
                                <span className="text-2xl">{s.icon}</span>
                              )}
                            </div>
                          );
                        }}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={handleContinueFromSpread}
                      disabled={isDrawing}
                      className={`fixed left-4 right-4 bottom-[max(108px,calc(env(safe-area-inset-bottom)+90px))] py-[1.05rem] px-6 rounded-xl font-medium uppercase border transition-colors disabled:opacity-40 disabled:pointer-events-none z-10 ${
                        selectedSpreadId === 'single'
                          ? 'text-[16px] sm:text-[17px] tracking-[0.02em] whitespace-nowrap'
                          : 'text-base tracking-wide'
                      }`}
                      style={{
                        background: (() => {
                          const v = Number(spreadPalette.mid) || 0x2563eb;
                          const r = (v >> 16) & 255;
                          const g = (v >> 8) & 255;
                          const b = v & 255;
                          return `rgba(${r}, ${g}, ${b}, 0.25)`;
                        })(),
                        borderWidth: 1,
                        borderColor: 'rgba(251, 191, 36, 0.85)',
                        color: '#fbbf24',
                      }}
                    >
                      {selectedSpreadId === 'single' ? (
                        <span className="flex flex-col items-center justify-center leading-tight normal-case">
                          <span className="uppercase">Выполнить расклад</span>
                        </span>
                      ) : selectedSpreadId === 'magic_ball' ? (
                        <span className="flex flex-col items-center justify-center leading-tight normal-case">
                          <span className="uppercase">Начать</span>
                        </span>
                      ) : (
                        <span className="flex flex-col items-center justify-center leading-tight normal-case">
                          <span className="uppercase">Начать</span>
                        </span>
                      )}
                    </button>
                    <div className="h-[6rem]" aria-hidden />
                  </>
                );
              })()}
            </div>
          ) : (
            <>
              <div className="flex-1 min-h-0 flex flex-col relative overflow-x-visible">
                <div className="flex-1 min-h-0 overflow-hidden overflow-x-hidden pr-2 -mr-2 tarot-select-fixed">
                  <div className="flex-shrink-0 mb-2 mt-14 pb-[8rem]">
                    <div className="w-full flex flex-col items-center" style={{ fontFamily: "'Bion', sans-serif" }}>
                      <p
                        className="font-tarot-title text-center mb-1"
                        style={{
                          fontSize: '1.25rem',
                          color: '#e5a011',
                          textShadow: '0 0 8px rgba(229,160,17,0.3), 0 0 16px rgba(229,160,17,0.2)',
                          filter: 'drop-shadow(0 0 4px rgba(229,160,17,0.25))',
                        }}
                      >
                        {activeDeck?.name}
                      </p>
                      <p className="text-white/70 text-xs leading-snug text-center max-w-[min(18rem,85vw)]">{activeDeck?.description}</p>
                    </div>
                  </div>
                </div>
                <div
                  className="absolute left-1/2 -translate-x-1/2 bottom-[2rem] w-[calc(100vw+96px)] min-w-[100vw] px-6 pt-2 pb-2 overflow-visible"
                  style={{ top: 'auto' }}
                >
                  <SimpleSwipePicker
                    items={deckPickerItems}
                    selectedId={activeDeckId}
                    onSelect={handleDeckPickerSelect}
                    selectByCenter
                    itemWidth={deckPickerSize.w}
                    itemHeight={deckPickerSize.h}
                    gap={deckGapPx}
                    overlapPx={-16}
                    levitate
                    levitateChaotic
                    swayPx={0}
                    scaleUnselected={0.95}
                    scaleSelected={1.03}
                    overflowVisible
                    edgePadding={typeof window !== 'undefined' ? Math.max(40, Math.floor(window.innerWidth / 2 - deckPickerSize.w / 2)) : 80}
                    renderItem={(deck, isSelected) => (
                      <div className="w-full flex flex-col items-center justify-center shadow-none" style={{ minHeight: deckPickerSize.h }}>
                        {(deck.deckImage || deck.backImage) ? (
                          <img src={deck.deckImage || deck.backImage} alt={deck.name} className="max-w-full w-auto h-auto object-contain rounded-[12px] shadow-none" style={{ maxHeight: deckPickerSize.h }} />
                        ) : (
                          <div className="w-full rounded-[12px] flex-1 flex items-center justify-center p-2" style={{ maxHeight: deckPickerSize.h, minHeight: 60 }}>
                            <div className="w-full h-full rounded-2xl flex items-center justify-center p-2" style={{ background: 'radial-gradient(circle at top, rgba(251,191,36,0.25), transparent 55%)' }}>
                              <span className="text-amber-200/80 text-sm text-center line-clamp-3">{deck.name}</span>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  />
                </div>
              </div>
              <button
                type="button"
                onClick={handleStartSpread}
                disabled={isDrawing}
                className="fixed left-4 right-4 bottom-[max(108px,calc(env(safe-area-inset-bottom)+90px))] py-[1.05rem] px-6 rounded-xl font-medium text-base uppercase tracking-wide border transition-colors disabled:opacity-40 disabled:pointer-events-none z-10"
                style={{
                  background: (() => {
                    const v = Number(spreadPalette.mid) || 0x2563eb;
                    const r = (v >> 16) & 255;
                    const g = (v >> 8) & 255;
                    const b = v & 255;
                    return `rgba(${r}, ${g}, ${b}, 0.25)`;
                  })(),
                  borderWidth: 1,
                  borderColor: 'rgba(251, 191, 36, 0.85)',
                  color: '#fbbf24',
                }}
              >
                <span className="flex flex-col items-center justify-center leading-tight normal-case">
                  <span className="uppercase">Начать</span>
                </span>
              </button>
              <div className="h-[6rem]" aria-hidden />
            </>
          )}
        </motion.div>
      ) : null}

      <AnimatePresence mode="wait">
        {phase === 'chat' ? (
          <motion.div
            key="tarot-phase-chat"
            className="fixed inset-0 z-[21]"
            exit={{ opacity: 0 }}
            transition={{ duration: 0.38, ease: [0.25, 0.1, 0.25, 1] }}
          >
        <TarologistChatScreen
          messages={tarologistMessages}
          onSendMessage={async (msg) => {
            setTarologistPromptStage(false);
            const prevMessages = [...(tarologistMessages || [])];
            const prevAssistantMessage = [...prevMessages].reverse().find((m) => m?.role === 'assistant')?.content || '';
            const nextMessages = [...prevMessages, { role: 'user', content: msg }];
            setTarologistMessages(nextMessages);
            setTarologistLoading(true);
            try {
              const ac = new AbortController();
              const to = setTimeout(() => ac.abort(), 90000);
              let res;
              try {
                const initData = await getInitDataWithRetry({ timeoutMs: 1800, intervalMs: 120 });
                if (!initData) {
                  setTarologistMessages((m) => [
                    ...m,
                    {
                      role: 'system',
                      content: 'Не удалось подтвердить сессию Telegram. Нажмите отправить еще раз.',
                    },
                  ]);
                  return;
                }
                res = await fetch(`${API_BASE}/api/tarot/tarologist-chat`, {
                  signal: ac.signal,
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                    init_data: initData,
                    spread_id: selectedSpreadId,
                    deck_id: activeDeckId,
                    deck_name: activeDeck?.name || '',
                    spread_name: selectedSpread?.name || '',
                    messages: nextMessages,
                    message: msg,
                  }),
                });
              } finally {
                clearTimeout(to);
              }
              const data = await res.json().catch(() => ({}));
              if (!res.ok) {
                const detail = typeof data?.detail === 'string' ? data.detail.trim() : '';
                const isAuthError = res.status === 401;
                setTarologistMessages((m) => [
                  ...m,
                  {
                    role: isAuthError ? 'system' : 'assistant',
                    content:
                      isAuthError
                        ? (detail || 'Сессия Telegram не подтвердилась. Закройте и снова откройте мини-апп из Telegram.')
                        : (detail || 'Сервис временно недоступен. Попробуйте ещё раз чуть позже.'),
                  },
                ]);
                return;
              }
              const reply = normalizeTarologistReplyText(data?.response || '') || 'Что именно вас интересует? Опишите подробнее.';
              setTarologistMessages((m) => [...m, { role: 'assistant', content: reply }]);
              const enoughInfo = Boolean(data?.enough_info);
              const refuseContinue = Boolean(data?.refuse_to_continue);
              const replySaysStart = tarologistReplyStartsSpread(reply);
              const userCount = nextMessages.filter((m) => m?.role === 'user').length;
              const minTurns = tarologistMinUserTurnsForAuto(selectedSpreadId);
              const longEnough = msg.length >= 320;
              const autoStartOk =
                enoughInfo && (userCount >= minTurns || longEnough);
              const userApprovedStart = tarologistUserAffirmative(msg);
              const celticAutoStart =
                selectedSpreadId === 'ten_cards' && autoStartOk && userApprovedStart;
              const otherAutoStart =
                selectedSpreadId !== 'ten_cards' && autoStartOk;
              const nonCelticConfirmedStart =
                selectedSpreadId !== 'ten_cards'
                && userApprovedStart
                && (tarologistReplyReadyForExecute(prevAssistantMessage) || tarologistReplyAskedExecuteQuestion(prevAssistantMessage));
              const replyForcedStart = selectedSpreadId !== 'ten_cards' && replySaysStart;
              const shouldStartSpread =
                !refuseContinue && (celticAutoStart || otherAutoStart || nonCelticConfirmedStart || replyForcedStart);
              debugTarologistAutostart('decision', {
                spreadId: selectedSpreadId,
                enoughInfo,
                refuseContinue,
                replySaysStart,
                userCount,
                minTurns,
                longEnough,
                autoStartOk,
                userApprovedStart,
                celticAutoStart,
                otherAutoStart,
                nonCelticConfirmedStart,
                replyForcedStart,
                shouldStartSpread,
                prevAssistantMessage,
                userMessage: msg,
                reply,
              });
              if (shouldStartSpread) {
                setTarologistLoading(false);
                await handleStartSpreadFromChatWithMessages(nextMessages);
                return;
              }
            } catch (err) {
              const aborted = typeof err?.name === 'string' && err.name === 'AbortError';
              setTarologistMessages((m) => [
                ...m,
                {
                  role: 'assistant',
                  content: aborted
                    ? 'Ответ долго не приходил. Попробуйте ещё раз.'
                    : 'Не удалось связаться с сервером. Проверьте сеть и попробуйте снова.',
                },
              ]);
            } finally {
              setTarologistLoading(false);
            }
          }}
          suggestedQuestions={tarologistSuggestedQuestions}
          onExecuteSpread={handleStartSpreadFromChat}
          isLoading={tarologistLoading}
          input={tarologistInput}
          onInputChange={setTarologistInput}
          onPromptStageChange={setTarologistPromptStage}
          reserveBottomTabBar
          onBack={() => setPhase('select')}
        />
          </motion.div>
        ) : phase === 'animating' ? (
        <motion.div
          key={`tarot-phase-anim-${cinematicRunId}`}
          initial={(skipSingleSelectTransitionRef.current || selectedSpreadId === 'single') ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={selectedSpreadId === 'single' ? { opacity: 1 } : { opacity: 0 }}
          transition={(skipSingleSelectTransitionRef.current || selectedSpreadId === 'single')
            ? { duration: 0 }
            : { duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="relative flex min-h-0 flex-1 flex-col overflow-visible pt-2"
          style={{ minHeight: selectedSpreadId === 'single' ? 'min(100dvh, 100%)' : 'min(70vh, 100%)' }}
        >
          <motion.div
            className="w-full flex flex-col items-center flex-1 min-h-0 overflow-visible px-4"
            transition={{ duration: 0.6, ease: TAROT_ANIM.SMOOTH_EASE }}
          >
            {(selectedSpreadId === 'single'
              || selectedSpreadId === 'three_cards'
              || selectedSpreadId === 'financial'
              || selectedSpreadId === 'six_cards'
              || selectedSpreadId === 'ten_cards') ? (
              <FanDeckPick
                shuffledDeckForPick={shuffledDeckForPick}
                selectedSpread={selectedSpread}
                spreadHint={getSpreadHint(selectedSpreadId)}
                activeDeck={activeDeck}
                handleCardSelect={handleCardSelect}
                pickedIndices={pickedIndices}
                pickedCards={spread}
                justAppeared={false}
                freezeDeck={animatingSubPhase !== 'picking'}
                subPhase={animatingSubPhase}
                triggerHaptics={triggerHaptics}
                spreadId={selectedSpreadId}
                singlePortalCardRef={singlePickPortalRef}
                hideLiftedCardsPortal={singleHidePickPortal}
              />
            ) : (
            <CinematicSpreadStage
              key={`cinematic-${cinematicRunId}`}
              spreadId={selectedSpreadId}
              cards={cinematicCards.length ? cinematicCards : spread}
              currentPositions={currentPositions}
            />
            )}
          </motion.div>
        </motion.div>
        ) : null}
      </AnimatePresence>

      {phase === 'result' && spread.length === 0 ? (
        <motion.div
          key="screen-result-empty"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center min-h-[40vh] gap-6 px-4"
        >
          <p className="text-amber-200/80 text-center text-sm">Не удалось загрузить расклад.</p>
          <Button onClick={() => { setPhase('select'); setSpread([]); }} variant="ghost" className="px-6 py-2">
            Выбрать снова
          </Button>
        </motion.div>
      ) : null}

      {phase === 'result' && spread.length > 0 ? (
        <motion.div
          ref={resultScrollRef}
          key={`screen-result-${cinematicRunId}`}
          data-tarot-result-scroll="1"
          initial={false}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.12, ease: [0.22, 1, 0.36, 1] }}
          className="fixed left-0 right-0 top-0 z-[12] overflow-x-hidden overflow-y-auto"
          style={{
            bottom: 0,
            overflowX: 'hidden',
            overflowY: 'auto',
            WebkitOverflowScrolling: 'touch',
          }}
        >
          <div
            className={cn('min-h-0 w-full', selectedSpreadId === 'single' && spread.length === 1 ? 'px-0' : 'px-4')}
            style={{
              paddingTop:
                selectedSpreadId === 'single' && spread.length === 1
                  ? TAROT_SINGLE_RESULT_TOP_SPACER
                  : TAROT_RESULT_TOP_SPACER,
              paddingBottom:
                selectedSpreadId === 'single' && spread.length === 1
                  ? 'max(1.25rem, calc(env(safe-area-inset-bottom, 0px) + 0.75rem))'
                  : TAROT_RESULT_SCROLL_BOTTOM_MULTI,
            }}
          >
            {spreadFailed && !spread.some((c) => c?.meaning && !/звезды молчат|не удалось загрузить/i.test(c.meaning)) ? (
              <div className="flex flex-col items-center justify-center gap-6 py-16">
                <p className="text-center text-amber-400/90 text-base">К сожалению, не удалось получить толкование. Попробуйте позже.</p>
                <Button onClick={handleNewSpread} className="px-6 py-3">
                  Попробовать снова
                </Button>
              </div>
            ) : (
              <>
            {selectedSpreadId === 'single' && spread.length === 1 ? (
              <motion.div
                ref={singleCardResultRef}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
              >
                <SingleCardResultView
                  card={singleResultCard || spread[0]}
                  onRetry={() => handleRetryCard(0)}
                  practicalAdvice={practicalAdvice}
                  cardBoxRef={singleResultCardBoxRef}
                  suppressCardVisual={Boolean(singleCardFly) && !singleCardRevealResult}
                  spreadOverallText={overallInterpretation}
                >
                  <FinalBlock
                    overallInterpretation={overallInterpretation}
                    overallSummaryShort={tarotSummaryShort}
                    practicalAdvice=""
                    spreadId="single"
                    question={resultQuestion || question}
                    chatMessages={chatMessages}
                    onNewSpread={handleNewSpread}
                    triggerHaptics={triggerHaptics}
                    spreadCards={spread}
                    currentPositions={currentPositions}
                  />
                </SingleCardResultView>
              </motion.div>
            ) : null}
            {selectedSpread.cards >= 10 ? (
              <TenCardConsultPanel
                spread={spread}
                currentPositions={currentPositions}
                onRetry={handleRetryCard}
                overallInterpretation={showFinalSummary ? overallInterpretation : ''}
                readingId={readingId}
                followUpQuestions={followUpQuestions}
                sendChatMessage={sendChatMessage}
                chatMessages={chatMessages}
                chatLoading={chatLoading}
                dialogueRequired={dialogueRequired}
                guidedFinished={guidedFinished}
                showFinalSummary={showFinalSummary}
                practicalAdvice={practicalAdvice}
                onNewSpread={handleNewSpread}
                question={resultQuestion || question}
                spreadId={selectedSpreadId}
                triggerHaptics={triggerHaptics}
              />
            ) : null}
            {selectedSpread.cards < 10 ? (
              <>
                {selectedSpreadId === 'three_cards' ? (
                  <BasicSpreadResultView
                    spread={spread}
                    overallInterpretation={overallInterpretation}
                    overallSummaryShort={tarotSummaryShort}
                    currentPositions={currentPositions}
                    onRetry={handleRetryCard}
                    onNewSpread={handleNewSpread}
                    triggerHaptics={triggerHaptics}
                    question={resultQuestion || question}
                    chatMessages={chatMessages}
                  />
                ) : null}
                {selectedSpreadId !== 'three_cards' && !(selectedSpreadId === 'single' && spread.length === 1) ? (
                  <SpreadSummaryModalView
                    spread={spread}
                    currentPositions={currentPositions}
                    overallInterpretation={overallInterpretation}
                    overallSummaryShort={tarotSummaryShort}
                    practicalAdvice={practicalAdvice}
                    spreadId={selectedSpreadId}
                    question={resultQuestion || question}
                    chatMessages={chatMessages}
                    onNewSpread={handleNewSpread}
                    triggerHaptics={triggerHaptics}
                  />
                ) : null}
                <TarotChat
                  enabled={selectedSpreadId !== 'six_cards' && selectedSpread.cards >= 6 && Boolean((question || '').trim())}
                  readingId={readingId}
                  quickQuestions={guidedFinished ? followUpQuestions : []}
                  onSend={sendChatMessage}
                  chatMessages={chatMessages}
                  loading={chatLoading}
                  guidedMode={dialogueRequired && !guidedFinished}
                  guidedStep={guidedStep}
                  guidedTotal={guidedQuestions.length}
                />
              </>
            ) : null}
            {selectedSpread.cards >= 6 && selectedSpreadId !== 'six_cards' && !showFinalSummary ? (
              <>
                <Button
                  size="lg"
                  onClick={() => {
                    triggerHaptics('light');
                    setShowFinalSummary(true);
                  }}
                  className="w-full justify-center mt-4"
                >
                  Получить итог расклада
                </Button>
                <button
                  type="button"
                  onClick={handleNewSpread}
                  className={cn(TAROT_GHOST_CTA_CLASS, 'mt-2')}
                >
                  ↩ Вернуться к началу Таро
                </button>
              </>
            ) : null}
              </>
            )}
          </div>
        </motion.div>
      ) : null}
      </AnimatePresence>

      {showStats ? (
        <TarotStatsPanel stats={statsData} onClose={() => setShowStats(false)} />
      ) : null}

      <TarotSpreadCostModal
        open={false}
        priceRub={tarotPriceRub}
        onConfirm={confirmTarotCostModal}
        onCancel={cancelTarotCostModal}
      />

      <AccessModal
        open={false}
        onClose={() => {
          setShowAccessModal(false);
          setAccessModalDismissed(true);
          if (phase === 'chat') {
            pendingDeckForCostModalRef.current = null;
            pendingTarotRunRef.current = null;
            skipSingleCostGateRef.current = false;
            setShowTarotCostModal(false);
            exitTarologistChatToTarotHome();
          }
        }}
        title="Доступ к Таро"
        message={accessModalMessage || 'Для расклада нужен доступ.'}
        status={status}
        balanceCents={limits?.balance_cents || 0}
        subscriptionNextChargeAt={limits?.subscription_next_charge_at || null}
        subscriptionCanceledAt={limits?.subscription_canceled_at || null}
        subscriptionEndDate={limits?.subscription_end_date || null}
        isTrialUsed={Boolean(limits?.is_trial_used)}
        refetchAuth={refetchAuth}
      />

      {phase === 'animating' && showAnalysisCue
        ? createPortal(
            <div
              className="pointer-events-none fixed inset-x-0 z-[600] flex justify-center px-4"
              style={{ bottom: 'max(6.75rem, calc(env(safe-area-inset-bottom) + 5.5rem))' }}
            >
              <div
                className="max-w-[min(24rem,calc(100vw-2.25rem))] overflow-hidden rounded-2xl border border-amber-400/40 shadow-[0_0_26px_rgba(251,191,36,0.16)] backdrop-blur-md"
                style={{ backgroundColor: 'rgba(0, 0, 0, 0.04)' }}
              >
                <TarotWaitingFactStarStrip />
                <div className="px-3.5 pb-3 pt-2 backdrop-blur-md" style={{ backgroundColor: 'rgba(0, 0, 0, 0.02)' }}>
                  <p className="text-xs sm:text-[13px] leading-snug text-amber-100/95">{TAROT_WAITING_FACT_INTRO}</p>
                  <p className="mt-2 text-xs sm:text-[13px] leading-relaxed text-amber-50/95 min-h-[2.75em]">
                    {waitingFactDisplayed}
                    {waitingFactTypingEnabled && waitingFactBody && !waitingFactComplete ? (
                      <span
                        className="inline-block ml-0.5 h-[0.95em] w-[1px] translate-y-[0.06em] bg-amber-200/85 animate-pulse"
                        aria-hidden
                      />
                    ) : null}
                  </p>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}

      {singleCardFly?.to && singleCardFly?.from && typeof document !== 'undefined'
        ? createPortal(
            <motion.div
              className="fixed z-[480] pointer-events-none rounded-[12px] overflow-hidden shadow-[0_10px_28px_rgba(0,0,0,0.4)]"
              initial={{
                left: singleCardFly.from.left,
                top: singleCardFly.from.top,
                width: singleCardFly.from.width,
                height: singleCardFly.from.height,
                opacity: 1,
              }}
              animate={{
                left: singleCardFly.to.left,
                top: singleCardFly.to.top,
                width: singleCardFly.to.width,
                height: singleCardFly.to.height,
                opacity: [1, 1, 0],
              }}
              transition={{
                duration: 0.9,
                times: [0, 0.4, 1],
                ease: [0.22, 1, 0.36, 1],
              }}
              onAnimationComplete={() => {
                setSingleCardFly(null);
                setSingleCardRevealResult(false);
              }}
              style={{ boxSizing: 'border-box' }}
            >
              {singleCardFly.card?.image ? (
                <img
                  src={singleCardFly.card.image}
                  alt=""
                  className="h-full w-full object-contain rounded-[12px]"
                  style={{ transform: singleCardFly.card?.is_reversed ? 'rotate(180deg)' : undefined }}
                />
              ) : (
                <div className="h-full w-full rounded-[12px] bg-amber-950/50" />
              )}
            </motion.div>,
            document.body
          )
        : null}

      <TarotMagicBallOverlay
        open={showMagicBall}
        onClose={() => setShowMagicBall(false)}
      />

    </div>
  );
}
