import { tarotDecks } from '../data/tarotDecks';
import { getSpreadHint } from '../data/tarotSpreads';

let tarotPrewarmPromise = null;
const LAST_DECK_STORAGE_KEY = 'astrov_tarot_last_deck_id';
const LAST_SPREAD_STORAGE_KEY = 'astrov_tarot_last_spread_id';

function getTarotPreloadLimit() {
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const saveData = Boolean(nav?.connection?.saveData);
  const effectiveType = String(nav?.connection?.effectiveType || '').toLowerCase();
  if (saveData || effectiveType.includes('2g')) return 6;
  if (effectiveType.includes('3g')) return 10;
  return 18;
}

function getTarotBatchSize() {
  const nav = typeof navigator !== 'undefined' ? navigator : null;
  const saveData = Boolean(nav?.connection?.saveData);
  const effectiveType = String(nav?.connection?.effectiveType || '').toLowerCase();
  if (saveData || effectiveType.includes('2g')) return 1;
  if (effectiveType.includes('3g')) return 2;
  return 4;
}

function getPreferredDeckId() {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage?.getItem(LAST_DECK_STORAGE_KEY) || '').trim();
  } catch (_) {
    return '';
  }
}

function getPreferredSpreadId() {
  if (typeof window === 'undefined') return '';
  try {
    return String(window.localStorage?.getItem(LAST_SPREAD_STORAGE_KEY) || '').trim();
  } catch (_) {
    return '';
  }
}

function prioritizeDecksByHistory(decks) {
  const preferredId = getPreferredDeckId();
  const preferredSpreadId = getPreferredSpreadId();
  const hintRecommended = getSpreadHint(preferredSpreadId)?.recommendedDeckIds || [];
  const byId = new Map(decks.map((d) => [d?.id, d]));
  const ordered = [];
  const addDeck = (deck) => {
    if (!deck) return;
    if (ordered.some((d) => d.id === deck.id)) return;
    ordered.push(deck);
  };

  if (preferredId) addDeck(byId.get(preferredId));
  hintRecommended.forEach((id) => addDeck(byId.get(id)));
  decks.forEach((d) => addDeck(d));
  return ordered;
}

function loadImageWithTimeout(url, timeoutMs = 6000, highPriority = false) {
  return new Promise((resolve) => {
    if (!url || typeof Image === 'undefined') {
      resolve(false);
      return;
    }
    const img = new Image();
    let done = false;
    const finish = (ok) => {
      if (done) return;
      done = true;
      resolve(ok);
    };
    const timer = window.setTimeout(() => finish(false), timeoutMs);
    img.decoding = 'async';
    if (highPriority) img.fetchPriority = 'high';
    img.onload = () => {
      window.clearTimeout(timer);
      finish(true);
    };
    img.onerror = () => {
      window.clearTimeout(timer);
      finish(false);
    };
    img.src = url;
  });
}

function pushUniqueUrl(target, seen, url) {
  if (!url || seen.has(url)) return;
  seen.add(url);
  target.push(url);
}

async function collectTarotWarmUrls(maxCount) {
  const urls = [];
  const seen = new Set();
  const orderedDecks = prioritizeDecksByHistory(tarotDecks);

  for (const [index, deck] of orderedDecks.entries()) {
    if (urls.length >= maxCount) break;
    if (deck.deckImageLoader) {
      const u = await deck.deckImageLoader().catch(() => '');
      pushUniqueUrl(urls, seen, u);
    }
    if (urls.length >= maxCount) break;
    if (deck.backImageLoader) {
      const u = await deck.backImageLoader().catch(() => '');
      pushUniqueUrl(urls, seen, u);
    }
    if (urls.length >= maxCount) break;
    // Favor the last selected deck: warm more cards from it.
    const cardsToWarm = index === 0 ? 6 : 2;
    const cards = Array.isArray(deck.cards) ? deck.cards.slice(0, cardsToWarm) : [];
    for (const card of cards) {
      if (urls.length >= maxCount) break;
      const u = await card?.imageLoader?.().catch(() => '');
      pushUniqueUrl(urls, seen, u);
    }
  }
  return urls.slice(0, maxCount);
}

async function preloadInBatches(urls, batchSize = 3) {
  for (let i = 0; i < urls.length; i += batchSize) {
    const batch = urls.slice(i, i + batchSize);
    await Promise.allSettled(batch.map((url, idx) => loadImageWithTimeout(url, 6000, i === 0 && idx < 2)));
  }
}

export function prewarmTarot() {
  if (tarotPrewarmPromise) return tarotPrewarmPromise;

  tarotPrewarmPromise = (async () => {
    // Warm main tarot route and related data chunk before user navigates.
    await Promise.allSettled([
      import('../pages/Tarot'),
      import('../data/tarotCardNamesRu'),
    ]);

    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    const maxCount = getTarotPreloadLimit();
    const urls = await collectTarotWarmUrls(maxCount);
    if (!urls.length) return;
    await preloadInBatches(urls, getTarotBatchSize());
  })();

  return tarotPrewarmPromise;
}

