/** Русские названия карт Таро. Маппинг по внутреннему ID (Major00, Wands01, Disks04 и т.п.) */
const MAJOR_RU = {
  0: 'Шут', 1: 'Маг', 2: 'Жрица', 3: 'Императрица', 4: 'Император', 5: 'Иерофант',
  6: 'Влюблённые', 7: 'Колесница', 8: 'Сила', 9: 'Отшельник', 10: 'Колесо Фортуны',
  11: 'Справедливость', 12: 'Повешенный', 13: 'Смерть', 14: 'Умеренность', 15: 'Дьявол',
  16: 'Башня', 17: 'Звезда', 18: 'Луна', 19: 'Солнце', 20: 'Суд', 21: 'Мир',
};
const RANK_RU = { 1: 'Туз', 11: 'Паж', 12: 'Рыцарь', 13: 'Королева', 14: 'Король' };
const SUIT_RU = { wands: 'Жезлов', cups: 'Кубков', swords: 'Мечей', pentacles: 'Пентаклей', pents: 'Пентаклей', disks: 'Дисков', coins: 'Монет' };

/** Стандартные названия по индексу карты 0–77 (0–21 старшие арканы, 22–35 жезлы, 36–49 кубки, 50–63 мечи, 64–77 пентакли). Колоды вроде Nightmare Before Christmas используют свои подписи (Page of Presents) - по номеру карты всегда известна стандартная карта. */
const RANK_NAMES_RU = ['', '', 'Двойка', 'Тройка', 'Четвёрка', 'Пятёрка', 'Шестёрка', 'Семёрка', 'Восьмёрка', 'Девятка', 'Десятка', 'Паж', 'Рыцарь', 'Королева', 'Король'];
const SUIT_ORDER = ['wands', 'cups', 'swords', 'pentacles'];

function buildStandardNamesByIndex() {
  const out = [];
  for (let i = 0; i <= 21; i++) out.push(MAJOR_RU[i] || '');
  for (const suit of SUIT_ORDER) {
    const suitRu = SUIT_RU[suit];
    for (let r = 1; r <= 14; r++) out.push(`${RANK_NAMES_RU[r] || ''} ${suitRu}`.trim());
  }
  return out;
}
const STANDARD_NAMES_RU = buildStandardNamesByIndex();

/**
 * Переопределение индекса 0–77 по decimal-id файла, если подпись на гравюре не совпадает с номером в имени.
 * Dark Mansion: 67 и 72 перепутаны на диске.
 * Nightmare Before Christmas: файла 67 нет; 72-Pentacles9 на гравюре IV OF PRESENTS (четвёрка), не девятка.
 */
const DECK_DECIMAL_ID_INDEX_FIX = {
  dark_mansion: new Map([
    ['72-pentacles9', 67],
    ['67-pentacles4', 72],
  ]),
  nightmare_christmas: new Map([['72-pentacles9', 67]]),
};

function parseCardId(filename) {
  const base = (filename || '').replace(/\.[^/.]+$/, '').toLowerCase();
  const major = base.match(/major\s*(\d+)/i);
  if (major) return { type: 'major', num: parseInt(major[1], 10) };
  const numPrefix = base.match(/^(\d+)/);
  if (numPrefix) {
    const num = parseInt(numPrefix[1], 10);
    if (num >= 0 && num <= 21) return { type: 'major', num };
    if (num >= 22 && num <= 77) return { type: 'index', num };
  }
  for (const suit of ['wands', 'cups', 'swords', 'pentacles', 'pents', 'disks', 'coins']) {
    const m = base.match(new RegExp(`${suit}\\s*(\\d+)`, 'i'));
    if (m) return { type: suit, num: parseInt(m[1], 10) };
  }
  const imgNum = base.match(/img(\d+)/i);
  if (imgNum) return { type: 'img', num: parseInt(imgNum[1], 10) };
  return null;
}

/** Английские названия старших арканов для распознавания по имени файла (без номера). */
const MAJOR_EN_TO_NUM = {
  fool: 0, magician: 1, priestess: 2, empress: 3, emperor: 4, hierophant: 5,
  lovers: 6, chariot: 7, strength: 8, hermit: 9, wheel: 10, justice: 11,
  hanged: 12, hanged_man: 12, death: 13, temperance: 14, devil: 15,
  tower: 16, star: 17, moon: 18, sun: 19, judgement: 20, judgment: 20, world: 21,
};

function parseMajorFromEnglish(base) {
  const lower = base.toLowerCase().replace(/[^a-z0-9]+/g, ' ');
  for (const [en, num] of Object.entries(MAJOR_EN_TO_NUM)) {
    if (lower.includes(en)) return { type: 'major', num };
  }
  return null;
}

/** Русское название по индексу карты 0–77 (для отображения вместо «Page of Presents» и т.п.). */
export function getCardNameByIndex(index) {
  const i = Number(index);
  if (Number.isFinite(i) && i >= 0 && i <= 77) return STANDARD_NAMES_RU[i] || null;
  return null;
}

/** Возвращает русское название карты по filename/id. Приоритет: колодные правки → номер файла 0–77 → стандартное имя; иначе разбор по масти/старшим. deckId: см. DECK_DECIMAL_ID_INDEX_FIX. */
export function getCardNameRu(filename, deckId) {
  const baseNorm = String(filename || '')
    .replace(/\.[^/.]+$/, '')
    .toLowerCase();
  const fixMap = deckId && DECK_DECIMAL_ID_INDEX_FIX[deckId];
  if (fixMap?.has(baseNorm)) {
    const idx = fixMap.get(baseNorm);
    if (idx != null && STANDARD_NAMES_RU[idx]) return STANDARD_NAMES_RU[idx];
  }
  const p = parseCardId(filename);
  if (p) {
    if (p.type === 'index' && STANDARD_NAMES_RU[p.num]) return STANDARD_NAMES_RU[p.num];
    if (p.type === 'major' && MAJOR_RU[p.num] != null) return MAJOR_RU[p.num];
    if (p.type !== 'major' && p.type !== 'img') {
      const suit = SUIT_RU[p.type] || p.type;
      const rank = RANK_RU[p.num] || (p.num >= 2 && p.num <= 10 ? RANK_NAMES_RU[p.num] : '');
      if (rank) return `${rank} ${suit}`;
    }
  }
  const base = (filename || '').replace(/\.[^/.]+$/, '').toLowerCase();
  const fromEn = parseMajorFromEnglish(base);
  if (fromEn && MAJOR_RU[fromEn.num] != null) return MAJOR_RU[fromEn.num];
  return null;
}
