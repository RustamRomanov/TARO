import React, { useMemo } from 'react';
import { Coins, Droplets, Flame, Heart, Moon, ShieldAlert, Sparkles, Sun, Zap } from 'lucide-react';
import { cn } from '../../lib/cn';

/**
 * Семантические акценты: адаптивно по объёму текста.
 * Только целые слова, без Markdown.
 */
const SEMANTIC_GROUPS = [
  {
    words: [
      'любовь',
      'любви',
      'любовью',
      'любим',
      'любимого',
      'любимая',
      'любимый',
      'страсть',
      'страсти',
      'романтика',
      'поцелуй',
      'нежность',
    ],
    className: 'text-rose-300/95',
    Icon: Heart,
    iconClassName: 'text-rose-300/90',
  },
  {
    words: [
      'холод',
      'холода',
      'холодно',
      'холодный',
      'холодная',
      'лёд',
      'льда',
      'льдом',
      'лед',
      'мороз',
      'мороза',
      'замёрз',
      'замерз',
    ],
    className: 'text-sky-300/95',
    Icon: Droplets,
    iconClassName: 'text-sky-300/90',
  },
  {
    words: ['огонь', 'огня', 'огнём', 'огнем', 'пламя', 'пламени', 'жар', 'жара', 'жаром', 'пыл', 'пыла', 'энергия', 'энергии', 'энергией', 'энергичн'],
    className: 'text-orange-300/95',
    Icon: Flame,
    iconClassName: 'text-orange-300/90',
  },
  {
    words: ['импульс', 'импульса', 'импульсом', 'рывок', 'рывка', 'рывком', 'скорость', 'скорости'],
    className: 'text-sky-300/95',
    Icon: Zap,
    iconClassName: 'text-sky-300/90',
  },
  {
    words: ['надежда', 'надежды', 'надежду', 'верю', 'вера', 'веры', 'уверен', 'уверенность'],
    className: 'text-emerald-300/95',
    Icon: Sparkles,
    iconClassName: 'text-emerald-300/90',
  },
  {
    words: [
      'страх',
      'страха',
      'боюсь',
      'боязнь',
      'тревога',
      'тревоги',
      'опасность',
      'опасности',
      'угроза',
      'угрозы',
    ],
    className: 'text-violet-300/95',
    Icon: ShieldAlert,
    iconClassName: 'text-violet-300/90',
  },
  {
    words: ['деньги', 'денег', 'деньгам', 'богатство', 'богатства', 'доход', 'дохода', 'бедность', 'долг', 'долга'],
    className: 'text-amber-300/95',
    Icon: Coins,
    iconClassName: 'text-amber-300/90',
  },
  {
    words: ['смерть', 'смерти', 'умирает', 'умер', 'погиб', 'гибель'],
    className: 'text-slate-400',
  },
  {
    words: ['солнце', 'солнца', 'солнцем', 'свет', 'света', 'светом', 'сияние', 'сияния', 'луч', 'луча', 'лучом', 'заря', 'зари'],
    className: 'text-yellow-200/90',
    Icon: Sun,
    iconClassName: 'text-yellow-200/90',
  },
  {
    words: ['луна', 'луны', 'луной', 'луну', 'тьма', 'тьмы', 'мрак', 'мрака', 'темнота', 'темноты', 'тень', 'тени'],
    className: 'text-indigo-400/90',
    Icon: Moon,
    iconClassName: 'text-indigo-300/90',
  },
  {
    words: ['вода', 'воды', 'водой', 'река', 'реки', 'море', 'моря', 'волна', 'волны', 'океан', 'океана', 'поток', 'потока'],
    className: 'text-cyan-300/90',
    Icon: Droplets,
    iconClassName: 'text-cyan-300/90',
  },
  {
    words: ['радость', 'радости', 'счастье', 'счастья', 'смех', 'смеха', 'веселье'],
    className: 'text-amber-200/90',
  },
  {
    words: ['гнев', 'гнева', 'злость', 'злости', 'ярость', 'ярости', 'ненависть', 'ненависти'],
    className: 'text-red-400/90',
  },
];

function buildLookup() {
  const map = new Map();
  const sorted = [...SEMANTIC_GROUPS].flatMap((g) =>
    g.words.map((w) => ({
      w: w.toLowerCase(),
      className: g.className,
      Icon: g.Icon,
      iconClassName: g.iconClassName,
      len: w.length,
    })),
  );
  sorted.sort((a, b) => b.len - a.len);
  for (const row of sorted) {
    if (!map.has(row.w)) {
      map.set(row.w, {
        className: row.className,
        Icon: row.Icon,
        iconClassName: row.iconClassName,
      });
    }
  }
  return map;
}

const LOOKUP = buildLookup();
const FALLBACK_COLOR_CLASSES = [
  'text-rose-300/95',
  'text-sky-300/95',
  'text-orange-300/95',
  'text-emerald-300/95',
  'text-violet-300/95',
  'text-amber-300/95',
  'text-cyan-300/90',
  'text-red-400/90',
];
const STEM_RULES = [
  { stems: ['перегор', 'выгор', 'огн', 'плам', 'жар', 'энерг'], className: 'text-red-400/90', Icon: Flame, iconClassName: 'text-red-400/90' },
  { stems: ['импульс', 'рыв', 'ускор', 'скорост'], className: 'text-sky-300/95', Icon: Zap, iconClassName: 'text-sky-300/90' },
  { stems: ['люб', 'серд', 'романт', 'нежн', 'чувств'], className: 'text-rose-300/95', Icon: Heart, iconClassName: 'text-rose-300/90' },
  { stems: ['деньг', 'бюдж', 'долг', 'доход', 'оплат', 'финанс'], className: 'text-amber-300/95', Icon: Coins, iconClassName: 'text-amber-300/90' },
  { stems: ['страх', 'тревог', 'риск', 'опас', 'угроз'], className: 'text-violet-300/95', Icon: ShieldAlert, iconClassName: 'text-violet-300/90' },
  { stems: ['солнц', 'свет', 'ясн', 'луч'], className: 'text-yellow-200/90', Icon: Sun, iconClassName: 'text-yellow-200/90' },
  { stems: ['лун', 'тьм', 'мрак', 'туман'], className: 'text-indigo-400/90', Icon: Moon, iconClassName: 'text-indigo-300/90' },
  { stems: ['вод', 'мор', 'вол', 'поток'], className: 'text-cyan-300/90', Icon: Droplets, iconClassName: 'text-cyan-300/90' },
];

function resolveAccent(lowerWord) {
  const exact = LOOKUP.get(lowerWord);
  if (exact) return exact;
  return STEM_RULES.find((rule) => rule.stems.some((stem) => lowerWord.includes(stem))) || null;
}

function countWords(text) {
  const m = String(text || '').match(/[\p{L}\p{N}]+/gu);
  return m ? m.length : 0;
}

function hashText(text) {
  let h = 0;
  const s = String(text || '');
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

/**
 * Разбивает строку на фрагменты: обычный текст, цветовой span и иконка рядом со словом.
 */
export function parseTarotSemanticHighlights(text, { withIcons = false, density = 'normal' } = {}) {
  const src = String(text || '');
  const wordsCount = countWords(src);
  const isDense = density === 'high';
  const ratio = isDense ? 0.22 : 0.14;
  const minHighlights = isDense ? 3 : 2;
  const maxHighlights = Math.min(isDense ? 24 : 14, Math.max(wordsCount >= 6 ? minHighlights : 0, Math.floor(wordsCount * ratio)));
  const maxIcons = withIcons ? Math.min(isDense ? 8 : 4, maxHighlights) : 0;
  if (!src || maxHighlights <= 0) {
    return src;
  }

  let used = 0;
  let iconsUsed = 0;
  const out = [];
  let partKey = 0;
  let i = 0;

  while (i < src.length) {
    const nonWord = src.slice(i).match(/^[^\p{L}\p{N}]+/u);
    if (nonWord) {
      out.push(nonWord[0]);
      i += nonWord[0].length;
      continue;
    }
    const wordMatch = src.slice(i).match(/^[\p{L}\p{N}]+/u);
    if (!wordMatch) {
      out.push(src[i]);
      i += 1;
      continue;
    }
    const word = wordMatch[0];
    const lower = word.toLowerCase();
    const accent = used < maxHighlights ? resolveAccent(lower) : null;
    if (accent) {
      used += 1;
      partKey += 1;
      const Icon = withIcons && iconsUsed < maxIcons ? accent.Icon : null;
      if (Icon) iconsUsed += 1;
      out.push(
        <span
          key={`h-${i}-${partKey}`}
          className={cn(
            accent.className,
            Icon && 'inline-flex items-baseline gap-0.5 align-baseline',
          )}
        >
          {Icon ? <Icon className={cn('w-3 h-3 shrink-0 translate-y-[1px]', accent.iconClassName)} aria-hidden /> : null}
          {word}
        </span>,
      );
    } else {
      out.push(word);
    }
    i += word.length;
  }

  // Fallback: если совпадений нет, добавляем цветовой акцент (без иконки).
  if (used === 0) {
    const fallbackMatch = src.match(/[\p{L}\p{N}]{5,}/u);
    if (fallbackMatch && typeof fallbackMatch.index === 'number') {
      const start = fallbackMatch.index;
      const word = fallbackMatch[0];
      const before = src.slice(0, start);
      const after = src.slice(start + word.length);
      return [
        before,
        <span
          key={`fallback-${start}`}
          className={FALLBACK_COLOR_CLASSES[hashText(src) % FALLBACK_COLOR_CLASSES.length]}
        >
          {word}
        </span>,
        after,
      ];
    }
  }

  return out;
}

/** Абзац трактовки: как гороскоп (13px, leading-relaxed), лёгкая семантическая окраска. */
export function TarotInterpretBody({ text, className, center, muted = false, withIcons = true, density = 'normal' }) {
  const nodes = useMemo(
    () => parseTarotSemanticHighlights(text, { withIcons, density }),
    [text, withIcons, density],
  );
  return (
    <p
      className={cn(
        muted ? 'text-white/80 text-[13px]' : 'text-white/90 text-[13px]',
        'leading-relaxed whitespace-pre-line m-0',
        center && 'text-center',
        className,
      )}
    >
      {nodes}
    </p>
  );
}

/** Строчный вариант (внутри других блоков). */
export function TarotInterpretInline({ text, className, withIcons = true, density = 'normal' }) {
  const nodes = useMemo(
    () => parseTarotSemanticHighlights(text, { withIcons, density }),
    [text, withIcons, density],
  );
  return <span className={cn('text-inherit leading-relaxed', className)}>{nodes}</span>;
}
