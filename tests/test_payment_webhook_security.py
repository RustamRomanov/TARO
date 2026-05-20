import types
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_payment_routes_module():
    file_path = Path(__file__).resolve().parents[1] / "app" / "api" / "payment_routes.py"
    spec = importlib.util.spec_from_file_location("payment_routes_under_test", file_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payment_routes = _load_payment_routes_module()


class _DummyDB:
    async def commit(self) -> None:
        return None


async def _fake_get_db():
    yield _DummyDB()


def _test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(payment_routes.router, prefix="/api")
    app.dependency_overrides[payment_routes.get_db] = _fake_get_db
    return app


def test_webhook_rejects_without_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_routes,
        "get_settings",
        lambda: types.SimpleNamespace(YOOKASSA_WEBHOOK_SECRET="secret", DEBUG=False),
    )

    async def _verify_ok(_payload):
        return True

    async def _process_ok(_db, _payload):
        return True

    monkeypatch.setattr(payment_routes, "verify_webhook_payment_payload", _verify_ok)
    monkeypatch.setattr(payment_routes, "process_webhook", _process_ok)

    client = TestClient(_test_app())
    response = client.post("/api/payments/webhook", json={"event": "payment.succeeded", "object": {"id": "x"}})
    assert response.status_code == 403


def test_webhook_rejects_unverified_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_routes,
        "get_settings",
        lambda: types.SimpleNamespace(YOOKASSA_WEBHOOK_SECRET="secret", DEBUG=False),
    )

    async def _verify_fail(_payload):
        return False

    async def _process_ok(_db, _payload):
        return True

    monkeypatch.setattr(payment_routes, "verify_webhook_payment_payload", _verify_fail)
    monkeypatch.setattr(payment_routes, "process_webhook", _process_ok)

    client = TestClient(_test_app())
    response = client.post(
        "/api/payments/webhook",
        headers={"X-YooKassa-Webhook-Secret": "secret"},
        json={"event": "payment.succeeded", "object": {"id": "x"}},
    )
    assert response.status_code == 403


def test_webhook_accepts_verified_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        payment_routes,
        "get_settings",
        lambda: types.SimpleNamespace(YOOKASSA_WEBHOOK_SECRET="secret", DEBUG=False),
    )

    async def _verify_ok(_payload):
        return True

    async def _process_ok(_db, _payload):
        return True

    monkeypatch.setattr(payment_routes, "verify_webhook_payment_payload", _verify_ok)
    monkeypatch.setattr(payment_routes, "process_webhook", _process_ok)

    client = TestClient(_test_app())
    response = client.post(
        "/api/payments/webhook",
        headers={"X-YooKassa-Webhook-Secret": "secret"},
        json={"event": "payment.succeeded", "object": {"id": "x"}},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
