const inflight = new Map();
const responseCache = new Map();

function buildKey(method, url, body, dedupeKey = '') {
  return `${method}|${url}|${dedupeKey || (body ? JSON.stringify(body) : '')}`;
}

export async function requestJson({
  url,
  method = 'GET',
  body,
  headers = {},
  signal,
  dedupe = true,
  dedupeKey = '',
  cacheTtlMs = 0,
}) {
  const key = buildKey(method, url, body, dedupeKey);
  const now = Date.now();

  if (cacheTtlMs > 0) {
    const cached = responseCache.get(key);
    if (cached && cached.expiresAt > now) return cached.value;
    if (cached) responseCache.delete(key);
  }

  if (dedupe && inflight.has(key)) {
    return inflight.get(key);
  }

  const requestPromise = fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: body != null ? JSON.stringify(body) : undefined,
    signal,
  })
    .then(async (res) => {
      const data = await res.json().catch(() => null);
      const value = { ok: res.ok, status: res.status, data };
      if (cacheTtlMs > 0 && res.ok) {
        responseCache.set(key, { expiresAt: Date.now() + cacheTtlMs, value });
      }
      return value;
    })
    .finally(() => {
      inflight.delete(key);
    });

  if (dedupe) inflight.set(key, requestPromise);
  return requestPromise;
}

export function postJson(url, body, options = {}) {
  return requestJson({ url, method: 'POST', body, ...options });
}

