"""API endpoints."""
from fastapi import APIRouter

from app.api.routes import router as predict_router
from app.api.support_routes import router as support_router
from app.api.tarot_routes import router as tarot_router
from app.api.user_routes import router as user_router
from app.api.payment_routes import router as payment_router
from app.api.tts_routes import router as tts_router

router = APIRouter()

router.include_router(predict_router, tags=["predict"])
router.include_router(tarot_router)
router.include_router(user_router)
router.include_router(payment_router)
router.include_router(tts_router)
router.include_router(support_router)
