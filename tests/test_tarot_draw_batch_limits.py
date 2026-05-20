import asyncio
import importlib.util
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi import HTTPException


def _load_tarot_routes_module():
    file_path = Path(__file__).resolve().parents[1] / "app" / "api" / "tarot_routes.py"
    spec = importlib.util.spec_from_file_location("tarot_routes_under_test", file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tarot_routes = _load_tarot_routes_module()
tarot_routes.DrawBatchRequest.model_rebuild(_types_namespace={"BatchCard": tarot_routes.BatchCard})


class _FakeResult:
    def scalar_one_or_none(self):
        return None

    def scalar(self):
        return 0


class _FakeDB:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.added = []

    async def execute(self, _stmt):
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.parametrize("spread_code", ["single", "three_cards"])
def test_draw_batch_propagates_balance_http_exception(monkeypatch, spread_code: str) -> None:
    async def _run() -> None:
        db = _FakeDB()
        payload = tarot_routes.DrawBatchRequest(
            init_data="ok",
            spread_code=spread_code,
            question="test",
            cards=[
                tarot_routes.BatchCard(
                    card_id="The Fool",
                    position=0,
                    position_name="Сегодня",
                    card_name="The Fool",
                    is_reversed=False,
                )
            ],
            allow_reversed=False,
            deck="classic",
        )

        monkeypatch.setattr(tarot_routes, "get_telegram_user_id_from_init_data", lambda _x: 123)
        async def _check_limits(*_args, **_kwargs):
            return SimpleNamespace(status="free", balance_cents=0)

        monkeypatch.setattr(tarot_routes, "check_limits", _check_limits)

        async def _resolve_profile(*_args, **_kwargs):
            return None

        monkeypatch.setattr(tarot_routes, "_resolve_profile", _resolve_profile)
        monkeypatch.setattr(tarot_routes, "_load_tarot_descriptions", lambda: {})

        async def _ai_fail(*_args, **_kwargs):
            raise RuntimeError("ai down")

        monkeypatch.setattr(tarot_routes.ai_client, "generate_text", _ai_fail)

        async def _welcome(*_args, **_kwargs):
            return False

        async def _inc(*_args, **_kwargs):
            return None

        async def _deduct(*_args, **_kwargs):
            raise HTTPException(status_code=403, detail="Недостаточно средств")

        monkeypatch.setattr(tarot_routes, "has_welcome_free_access", _welcome)
        monkeypatch.setattr(tarot_routes, "increment_daily", _inc)
        monkeypatch.setattr(tarot_routes, "has_paid_access", lambda _u: False)
        monkeypatch.setattr(tarot_routes, "deduct_balance", _deduct)

        with pytest.raises(HTTPException) as exc:
            await tarot_routes.tarot_draw_batch(payload, db)
        assert exc.value.status_code == 403
        assert db.rolled_back is True
        assert db.committed is False

    asyncio.run(_run())
