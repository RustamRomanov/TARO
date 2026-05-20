import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any as TypingAny

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _load_module(module_name: str, relative_path: str):
    file_path = Path(__file__).resolve().parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payment_routes = _load_module("payment_routes_stage4", "app/api/payment_routes.py")
tarot_routes = _load_module("tarot_routes_stage4", "app/api/tarot_routes.py")
tarot_routes.DrawBatchRequest.model_rebuild(_types_namespace={"BatchCard": tarot_routes.BatchCard})
tarot_routes.DrawBatchResponse.model_rebuild(
    _types_namespace={"Any": TypingAny, "CardInterpretation": tarot_routes.CardInterpretation}
)

@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "stage4_integration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(tarot_routes.User.__table__.create, checkfirst=True)
            await conn.run_sync(tarot_routes.Profile.__table__.create, checkfirst=True)
            await conn.run_sync(tarot_routes.TarotReading.__table__.create, checkfirst=True)
        async with session_factory() as session:
            session.add(
                tarot_routes.User(
                    telegram_id=123,
                    status="free",
                    balance_cents=0,
                )
            )
            await session.commit()

    asyncio.run(_init_db())

    async def _get_db_override():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(tarot_routes.router, prefix="/api")
    app.include_router(payment_routes.router, prefix="/api")
    app.dependency_overrides[tarot_routes.get_db] = _get_db_override
    app.dependency_overrides[payment_routes.get_db] = _get_db_override

    monkeypatch.setattr(tarot_routes, "get_telegram_user_id_from_init_data", lambda _x: 123)
    monkeypatch.setattr(payment_routes, "get_telegram_user_id_from_init_data", lambda _x: 123)

    async def _check_limits(*_args, **_kwargs):
        return SimpleNamespace(status="free", balance_cents=0)

    async def _resolve_profile(*_args, **_kwargs):
        return None

    async def _welcome_free(*_args, **_kwargs):
        return False

    monkeypatch.setattr(tarot_routes, "check_limits", _check_limits)
    monkeypatch.setattr(tarot_routes, "_resolve_profile", _resolve_profile)
    monkeypatch.setattr(tarot_routes, "_load_tarot_descriptions", lambda: {})
    monkeypatch.setattr(tarot_routes, "has_paid_access", lambda _u: False)
    monkeypatch.setattr(tarot_routes, "has_welcome_free_access", _welcome_free)

    async def _fake_generate_text(prompt: str, *args, **kwargs) -> str:
        if '"response":"..."' in prompt or "updated_advice" in prompt:
            return json.dumps(
                {
                    "response": "Ответ по раскладу: опирайтесь на спокойный темп и факты.",
                    "updated_advice": "Сделайте один понятный шаг и оцените результат.",
                    "new_questions": ["Вам важнее скорость или устойчивость?"],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "cards_interpretations": [
                    {
                        "position": 0,
                        "position_name": "Сегодня",
                        "interpretation": "Карта указывает на спокойный темп, внимательность к деталям и мягкий фокус на главном вопросе.",
                        "card_id": "The Fool",
                        "card_name": "The Fool",
                        "is_reversed": False,
                    }
                ],
                "summary": "Есть потенциал для ясного шага.",
                "overall": "Ситуация просит не торопиться, но двигаться ровно и осознанно.",
                "question_essence": "Нужна ясность и устойчивость.",
                "follow_up_questions": [],
                "advice": "Сделайте один конкретный шаг сегодня.",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(tarot_routes.ai_client, "generate_text", _fake_generate_text)

    client = TestClient(app)
    yield client

    client.close()
    asyncio.run(engine.dispose())


def test_tarot_draw_batch_then_chat_e2e(api_client: TestClient) -> None:
    draw_response = api_client.post(
        "/api/tarot/draw-batch",
        json={
            "init_data": "ok",
            "spread_code": "single",
            "question": "Что важно на сегодня?",
            "cards": [
                {
                    "card_id": "The Fool",
                    "position": 0,
                    "position_name": "Сегодня",
                    "is_reversed": False,
                    "card_name": "The Fool",
                    "image": "",
                }
            ],
            "allow_reversed": False,
            "deck": "classic",
        },
    )
    assert draw_response.status_code == 200
    draw_payload = draw_response.json()
    reading_id = draw_payload.get("reading_id")
    assert isinstance(reading_id, str) and reading_id
    assert draw_payload.get("cards_interpretations")

    chat_response = api_client.post(
        "/api/tarot/chat",
        json={
            "init_data": "ok",
            "reading_id": reading_id,
            "message": "Уточни по рискам.",
        },
    )
    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert "Ответ по раскладу" in chat_payload.get("response", "")
    assert isinstance(chat_payload.get("chat_history"), list)
    assert len(chat_payload.get("chat_history", [])) >= 2


def test_payment_webhook_rejects_without_secret(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        payment_routes,
        "get_settings",
        lambda: SimpleNamespace(YOOKASSA_WEBHOOK_SECRET="secret", DEBUG=False),
    )

    async def _verify_ok(_payload):
        return True

    async def _process_ok(_db, _payload):
        return True

    monkeypatch.setattr(payment_routes, "verify_webhook_payment_payload", _verify_ok)
    monkeypatch.setattr(payment_routes, "process_webhook", _process_ok)

    response = api_client.post("/api/payments/webhook", json={"event": "payment.succeeded", "object": {"id": "x"}})
    assert response.status_code == 403


def test_payment_webhook_accepts_valid_secret_and_payload(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        payment_routes,
        "get_settings",
        lambda: SimpleNamespace(YOOKASSA_WEBHOOK_SECRET="secret", DEBUG=False),
    )

    async def _verify_ok(_payload):
        return True

    async def _process_ok(_db, _payload):
        return True

    monkeypatch.setattr(payment_routes, "verify_webhook_payment_payload", _verify_ok)
    monkeypatch.setattr(payment_routes, "process_webhook", _process_ok)

    response = api_client.post(
        "/api/payments/webhook",
        headers={"X-YooKassa-Webhook-Secret": "secret"},
        json={"event": "payment.succeeded", "object": {"id": "x"}},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
