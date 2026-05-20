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


tarot_routes = _load_module("tarot_routes_stage5", "app/api/tarot_routes.py")
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
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.added = []
        self._ids = 0

    async def execute(self, _stmt):
        return _FakeResult()

    def add(self, obj):
        self._ids += 1
        if getattr(obj, "id", None) is None:
            setattr(obj, "id", f"test-reading-{self._ids}")
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def test_single_draw_concurrency_allows_only_one_free_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        db = _FakeDB()
        usage_state = {"daily": 0}

        monkeypatch.setattr(tarot_routes, "get_telegram_user_id_from_init_data", lambda _x: 123)

        async def _check_limits(*_args, **_kwargs):
            return SimpleNamespace(status="free", balance_cents=0)

        async def _resolve_profile(*_args, **_kwargs):
            return None

        welcome_calls = {"n": 0}

        async def _welcome(*_args, **_kwargs):
            # Под lock только один «бесплатный» слот (ознакомительный): второй параллельный запрос уже платный.
            welcome_calls["n"] += 1
            return welcome_calls["n"] == 1

        async def _inc(*_args, **_kwargs):
            usage_state["daily"] += 1

        async def _deduct(*_args, **_kwargs):
            raise HTTPException(status_code=403, detail="Недостаточно средств")

        async def _ai_text(*_args, **_kwargs):
            await asyncio.sleep(0.05)
            return (
                '{"cards_interpretations":[{"position":0,"position_name":"Сегодня","interpretation":"'
                'Карта подсказывает действовать спокойно и смотреть на факты.","card_id":"The Fool","card_name":"The Fool","is_reversed":false}],'
                '"summary":"Короткий вывод.","overall":"Развернутый вывод.","question_essence":"Суть вопроса.","follow_up_questions":[],"advice":"Один шаг сегодня."}'
            )

        monkeypatch.setattr(tarot_routes, "check_limits", _check_limits)
        monkeypatch.setattr(tarot_routes, "_resolve_profile", _resolve_profile)
        monkeypatch.setattr(tarot_routes, "_load_tarot_descriptions", lambda: {})
        monkeypatch.setattr(tarot_routes, "has_welcome_free_access", _welcome)
        monkeypatch.setattr(tarot_routes, "increment_daily", _inc)
        monkeypatch.setattr(tarot_routes, "has_paid_access", lambda _u: False)
        monkeypatch.setattr(tarot_routes, "deduct_balance", _deduct)
        monkeypatch.setattr(tarot_routes.ai_client, "generate_text", _ai_text)

        payload = tarot_routes.DrawBatchRequest(
            init_data="ok",
            spread_code="single",
            question="Что важно сегодня?",
            cards=[
                tarot_routes.BatchCard(
                    card_id="The Fool",
                    position=0,
                    position_name="Сегодня",
                    is_reversed=False,
                    card_name="The Fool",
                )
            ],
            allow_reversed=False,
            deck="classic",
        )

        async def _call_once():
            try:
                result = await tarot_routes.tarot_draw_batch(payload, db)
                return ("ok", result.reading_id)
            except HTTPException as exc:
                return ("err", exc.status_code)

        r1, r2 = await asyncio.gather(_call_once(), _call_once())
        results = [r1, r2]
        ok_count = sum(1 for r in results if r[0] == "ok")
        err_403_count = sum(1 for r in results if r[0] == "err" and r[1] == 403)

        assert ok_count == 1
        assert err_403_count == 1
        assert db.commits == 1
        assert db.rollbacks >= 1

    asyncio.run(_run())
