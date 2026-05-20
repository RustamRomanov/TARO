"""In-memory runtime metrics for lightweight observability."""

from __future__ import annotations

from threading import Lock
from typing import Any


_lock = Lock()
_started_at_ms: int = 0
_totals: dict[str, float] = {
    "requests_total": 0.0,
    "errors_5xx": 0.0,
    "total_duration_ms": 0.0,
    "max_duration_ms": 0.0,
}
_by_route: dict[str, dict[str, float]] = {}
_counters: dict[str, float] = {}


def _ensure_started(now_ms: int) -> None:
    global _started_at_ms
    if _started_at_ms <= 0:
        _started_at_ms = int(now_ms)


def record_request(*, route: str, method: str, status_code: int, duration_ms: float, now_ms: int) -> None:
    key = f"{method.upper()} {route or '/'}"
    with _lock:
        _ensure_started(now_ms)
        _totals["requests_total"] += 1
        _totals["total_duration_ms"] += max(0.0, float(duration_ms))
        if duration_ms > _totals["max_duration_ms"]:
            _totals["max_duration_ms"] = float(duration_ms)
        if int(status_code) >= 500:
            _totals["errors_5xx"] += 1

        stat = _by_route.get(key)
        if stat is None:
            stat = {
                "count": 0.0,
                "errors_5xx": 0.0,
                "total_duration_ms": 0.0,
                "max_duration_ms": 0.0,
            }
            _by_route[key] = stat
        stat["count"] += 1
        stat["total_duration_ms"] += max(0.0, float(duration_ms))
        if duration_ms > stat["max_duration_ms"]:
            stat["max_duration_ms"] = float(duration_ms)
        if int(status_code) >= 500:
            stat["errors_5xx"] += 1


def incr_counter(name: str, value: float = 1.0) -> None:
    key = (name or "").strip()
    if not key:
        return
    with _lock:
        _counters[key] = float(_counters.get(key, 0.0) + value)


def snapshot(*, top_limit: int = 30, now_ms: int) -> dict[str, Any]:
    with _lock:
        uptime_ms = max(0, int(now_ms) - int(_started_at_ms or now_ms))
        requests_total = int(_totals["requests_total"])
        avg_duration_ms = (
            float(_totals["total_duration_ms"]) / requests_total if requests_total > 0 else 0.0
        )
        routes = []
        for key, stat in _by_route.items():
            count = int(stat["count"])
            routes.append(
                {
                    "route": key,
                    "count": count,
                    "errors_5xx": int(stat["errors_5xx"]),
                    "avg_duration_ms": round((stat["total_duration_ms"] / count) if count > 0 else 0.0, 2),
                    "max_duration_ms": round(float(stat["max_duration_ms"]), 2),
                }
            )
        routes.sort(key=lambda x: x["count"], reverse=True)
        counters = {k: int(v) if float(v).is_integer() else round(float(v), 2) for k, v in _counters.items()}
        return {
            "uptime_ms": uptime_ms,
            "requests_total": requests_total,
            "errors_5xx": int(_totals["errors_5xx"]),
            "avg_duration_ms": round(avg_duration_ms, 2),
            "max_duration_ms": round(float(_totals["max_duration_ms"]), 2),
            "routes": routes[: max(1, int(top_limit))],
            "counters": counters,
        }
