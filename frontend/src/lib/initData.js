/** Получение initData Telegram WebApp (SDK, URL, hash, localStorage). */
const INIT_DATA_CACHE_KEY = 'tg_init_data_cache';
let memoValue = '';
let memoTs = 0;

function getLiveInitData() {
  if (typeof window === 'undefined') return '';
  const fromSdk = window.Telegram?.WebApp?.initData || '';
  if (fromSdk) {
    try {
      window.localStorage.setItem(INIT_DATA_CACHE_KEY, fromSdk);
    } catch {}
    return fromSdk;
  }
  const fromSearch = new URLSearchParams(window.location.search).get('tgWebAppData') || '';
  if (fromSearch) {
    const decoded = decodeURIComponent(fromSearch);
    try {
      window.localStorage.setItem(INIT_DATA_CACHE_KEY, decoded);
    } catch {}
    return decoded;
  }
  const hashRaw = window.location.hash || '';
  const hashQuery = hashRaw.includes('?') ? hashRaw.slice(hashRaw.indexOf('?') + 1) : hashRaw.replace(/^#/, '');
  const fromHash = new URLSearchParams(hashQuery).get('tgWebAppData') || '';
  if (fromHash) {
    const decoded = decodeURIComponent(fromHash);
    try {
      window.localStorage.setItem(INIT_DATA_CACHE_KEY, decoded);
    } catch {}
    return decoded;
  }
  return '';
}

export function getInitData() {
  const now = Date.now();
  if (memoValue && now - memoTs < 1000) return memoValue;
  const live = getLiveInitData();
  if (live) {
    memoValue = live;
    memoTs = now;
    return live;
  }
  if (import.meta.env.DEV) {
    memoValue = 'dev_local';
    memoTs = now;
    return 'dev_local';
  }
  try {
    memoValue = window.localStorage.getItem(INIT_DATA_CACHE_KEY) || '';
    memoTs = now;
    return memoValue;
  } catch {
    return '';
  }
}

/** Строгое initData для операций записи: только текущая Telegram-сессия/URL без кэша. */
export function getInitDataStrict() {
  return getLiveInitData();
}

/**
 * Надежное чтение initData с коротким ожиданием для Telegram WebView,
 * где SDK иногда отдает initData не сразу после открытия.
 */
export async function getInitDataWithRetry(options = {}) {
  const timeoutMs = Number(options.timeoutMs ?? 1400);
  const intervalMs = Number(options.intervalMs ?? 120);
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    const strict = getInitDataStrict();
    if (strict) return strict;
    const cached = getInitData();
    if (cached) return cached;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return getInitDataStrict() || getInitData() || '';
}
