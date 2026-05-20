#!/usr/bin/env python3
"""
Lightweight load test for /api/tarot/draw-batch with p50/p95/p99 report.

Usage example:
  python scripts/load_test_tarot_draw_batch.py \
    --base-url http://127.0.0.1:8000 \
    --init-data "<telegram_init_data>" \
    --requests 100 \
    --concurrency 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class Sample:
    latency_ms: float
    status_code: int
    ok: bool


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (len(sorted_values) - 1) * max(0.0, min(1.0, q))
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_values[lo])
    return float(sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo))


async def _one_request(client: httpx.AsyncClient, payload: dict[str, Any]) -> Sample:
    started = time.perf_counter()
    try:
        response = await client.post("/api/tarot/draw-batch", json=payload)
        latency = (time.perf_counter() - started) * 1000.0
        return Sample(latency_ms=latency, status_code=response.status_code, ok=response.status_code < 500)
    except Exception:
        latency = (time.perf_counter() - started) * 1000.0
        return Sample(latency_ms=latency, status_code=0, ok=False)


async def run_load(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "init_data": args.init_data,
        "spread_code": args.spread_code,
        "question": args.question,
        "cards": args.cards,
        "allow_reversed": args.allow_reversed,
        "deck": args.deck,
        "personalize": False,
        "profile_id": None,
        "deck_card_ids": [],
    }

    limits = asyncio.Semaphore(max(1, args.concurrency))
    samples: list[Sample] = []
    timeout = httpx.Timeout(args.timeout_sec)
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=timeout, headers=headers) as client:
        async def _worker() -> None:
            async with limits:
                samples.append(await _one_request(client, payload))

        tasks = [asyncio.create_task(_worker()) for _ in range(max(1, args.requests))]
        await asyncio.gather(*tasks)

    latencies = sorted(s.latency_ms for s in samples)
    status_buckets: dict[str, int] = {}
    for s in samples:
        key = str(s.status_code)
        status_buckets[key] = status_buckets.get(key, 0) + 1

    return {
        "requests": len(samples),
        "concurrency": int(args.concurrency),
        "base_url": args.base_url,
        "spread_code": args.spread_code,
        "success_rate": round(sum(1 for s in samples if s.ok) / max(1, len(samples)), 4),
        "status_codes": status_buckets,
        "latency_ms": {
            "min": round(latencies[0], 2) if latencies else 0.0,
            "p50": round(_percentile(latencies, 0.50), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "p99": round(_percentile(latencies, 0.99), 2),
            "max": round(latencies[-1], 2) if latencies else 0.0,
            "avg": round(sum(latencies) / max(1, len(latencies)), 2),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load test /api/tarot/draw-batch")
    parser.add_argument("--base-url", default=os.getenv("LOAD_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--init-data", default=os.getenv("LOAD_INIT_DATA", ""))
    parser.add_argument("--requests", type=int, default=int(os.getenv("LOAD_REQUESTS", "50")))
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("LOAD_CONCURRENCY", "10")))
    parser.add_argument("--spread-code", default=os.getenv("LOAD_SPREAD_CODE", "single"))
    parser.add_argument("--question", default=os.getenv("LOAD_QUESTION", "Тест скорости"))
    parser.add_argument("--deck", default=os.getenv("LOAD_DECK", "classic"))
    parser.add_argument("--allow-reversed", action="store_true")
    parser.add_argument("--timeout-sec", type=float, default=float(os.getenv("LOAD_TIMEOUT_SEC", "30")))
    parser.add_argument(
        "--cards",
        type=json.loads,
        default=[],
        help='JSON list for explicit cards, e.g. \'[{"card_id":"The Fool","position":0,"position_name":"Сегодня","is_reversed":false,"card_name":"The Fool","image":""}]\'',
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(run_load(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
