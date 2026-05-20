const MAX_EVENTS = 240;
const events = [];
const pendingRouteIntent = new Map();

function nowMs() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function pushEvent(type, payload = {}) {
  const event = {
    t: Number(nowMs().toFixed(2)),
    type,
    ...payload,
  };
  events.push(event);
  if (events.length > MAX_EVENTS) {
    events.splice(0, events.length - MAX_EVENTS);
  }
  return event;
}

export function markRouteIntent(route, source = 'unknown') {
  const r = String(route || '').trim();
  if (!r) return;
  pendingRouteIntent.set(r, { startAt: nowMs(), source });
  pushEvent('route_intent', { route: r, source });
}

export function markRouteRender(route) {
  const r = String(route || '').trim();
  if (!r) return;
  const pending = pendingRouteIntent.get(r);
  if (!pending) {
    pushEvent('route_render', { route: r, latencyMs: null, source: null });
    return;
  }
  pendingRouteIntent.delete(r);
  const latencyMs = Math.max(0, nowMs() - pending.startAt);
  pushEvent('route_render', {
    route: r,
    source: pending.source,
    latencyMs: Number(latencyMs.toFixed(2)),
  });
}

export function notePrewarm(route, source = 'unknown', status = 'start') {
  const r = String(route || '').trim();
  if (!r) return;
  pushEvent('prewarm', { route: r, source, status });
}

function buildSummary() {
  const lastByRoute = new Map();
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === 'route_render' && typeof e.latencyMs === 'number' && !lastByRoute.has(e.route)) {
      lastByRoute.set(e.route, e.latencyMs);
    }
  }
  return {
    eventsCount: events.length,
    lastRouteLatencyMs: Object.fromEntries(lastByRoute),
  };
}

if (typeof window !== 'undefined') {
  window.__ASTROV_PERF = {
    getEvents: () => [...events],
    clear: () => {
      events.length = 0;
      pendingRouteIntent.clear();
    },
    getSummary: () => buildSummary(),
  };
}

