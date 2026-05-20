import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any as TypingAny

import pytest
from fastapi import HTTPException


def _load_module(module_name: str, relative_path: str):
    file_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tarot_routes = _load_module("tarot_routes_stage6", "app/api/tarot_routes.py")
tarot_routes.DrawBatchRequest.model_rebuild(_types_namespace={"BatchCard": tarot_routes.BatchCard})
tarot_routes.DrawBatchResponse.model_rebuild(
    _types_namespace={"Any": TypingAny, "CardInterpretation": tarot_routes.CardInterpretation}
)


class _FakeResult:
    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return 0


class _FakeDB:
    async def execute(self, _stmt):
        return _FakeResult()

    def add(self, _obj):
        return None

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


def test_draw_batch_returns_429_when_distributed_lock_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        db = _FakeDB()
        payload = tarot_routes.DrawBatchRequest(
            init_data="ok",
            spread_code="single",
            question="test",
            cards=[],
            allow_reversed=False,
            deck="classic",
        )

        monkeypatch.setattr(tarot_routes, "get_telegram_user_id_from_init_data", lambda _x: 123)

        async def _check_limits(*_args, **_kwargs):
            return SimpleNamespace(status="free", balance_cents=0)

        async def _resolve_profile(*_args, **_kwargs):
            return None

        async def _acquire_lock(*_args, **_kwargs):
            return None

        monkeypatch.setattr(tarot_routes, "check_limits", _check_limits)
        monkeypatch.setattr(tarot_routes, "_resolve_profile", _resolve_profile)
        monkeypatch.setattr(tarot_routes, "cache_acquire_lock", _acquire_lock)

        with pytest.raises(HTTPException) as exc:
            await tarot_routes.tarot_draw_batch(payload, db)
        assert exc.value.status_code == 429

    asyncio.run(_run())
