"""TTS (Text-to-Speech) - Inworld API для качественного голоса."""
import base64
import logging
from time import time

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.tts_service import fix_pronunciation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tts", tags=["tts"])

INWORLD_TTS_URL = "https://api.inworld.ai/tts/v1/voice"
INWORLD_VOICES_URL = "https://api.inworld.ai/voices/v1/voices"  # новый API с Nikolai, Dmitry и др.
INWORLD_MAX_TEXT_LENGTH = 2000

_voices_cache: tuple[list, float] = ([], 0)
CACHE_TTL = 300  # 5 мин


async def _resolve_voice_id(api_key: str, name_or_id: str) -> str:
    """Если передан displayName (Nikolai, Dmitry), разрешаем в voiceId формата workspace__voice."""
    if "__" in name_or_id:
        return name_or_id  # уже полный voiceId
    global _voices_cache
    now = time()
    if _voices_cache[0] and now - _voices_cache[1] < CACHE_TTL:
        voices = _voices_cache[0]
    else:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    INWORLD_VOICES_URL,
                    params={"languages": ["RU_RU"]},
                    headers={"Authorization": f"Basic {api_key}", "Content-Type": "application/json"},
                )
            if r.status_code != 200:
                return name_or_id
            voices = (r.json() or {}).get("voices", [])
            _voices_cache = (voices, now)
        except Exception:
            return name_or_id
    want = name_or_id.strip().lower()
    for v in voices:
        if (v.get("displayName") or "").strip().lower() == want:
            return v.get("voiceId") or name_or_id
    return name_or_id


@router.get("/voices")
async def tts_list_voices(language: str = "ru"):
    """
    Список голосов Inworld (Nikolai, Dmitry, Elena, Svetlana для ru).
    voiceId имеет формат {workspace}__{voice} - используйте его для INWORLD_TTS_VOICE_ID.
    """
    settings = get_settings()
    api_key = (settings.INWORLD_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="INWORLD_API_KEY не задан")
    headers = {"Authorization": f"Basic {api_key}", "Content-Type": "application/json"}
    lang = "RU_RU" if language.lower() in ("ru", "rus") else language.upper().replace("-", "_")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                INWORLD_VOICES_URL,
                params={"languages": [lang]},
                headers=headers,
            )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=r.text[:300] or "Ошибка Inworld")
        data = r.json()
        voices = data.get("voices", [])
        # Nikolai, Dmitry - мужские; Elena, Svetlana - женские
        male_names = ("nikolai", "dmitry")
        male = [v for v in voices if (v.get("displayName") or "").lower() in male_names]
        return {"voices": voices, "male_ru": male or voices[:5]}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/available")
def tts_available():
    """Проверка: доступен ли Inworld TTS."""
    settings = get_settings()
    key = (settings.INWORLD_API_KEY or "").strip()
    return {"available": bool(key)}


@router.get("/check")
async def tts_check():
    """
    Диагностика: проверка подключения к Inworld TTS.
    Возвращает {ok, error?} - ok=True если синтез прошёл успешно.
    """
    settings = get_settings()
    api_key = (settings.INWORLD_API_KEY or "").strip()
    if not api_key:
        return {"ok": False, "error": "INWORLD_API_KEY не задан"}

    raw_voice = (settings.INWORLD_TTS_VOICE_ID or "Dennis").strip()
    voice_id = await _resolve_voice_id(api_key, raw_voice)
    model_id = (settings.INWORLD_TTS_MODEL or "inworld-tts-1.5-max").strip()
    payload = {
        "text": "Тест",
        "voiceId": voice_id,
        "modelId": model_id,
    }
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(INWORLD_TTS_URL, json=payload, headers=headers)
        if r.status_code == 200:
            data = r.json()
            if data.get("audioContent") and len(data["audioContent"]) > 50:
                return {"ok": True}
        return {
            "ok": False,
            "error": f"Inworld status={r.status_code}, body={r.text[:300] if r.text else 'empty'}",
        }
    except Exception as e:
        logger.warning("TTS check failed: %s", e)
        return {"ok": False, "error": str(e)}


class TtsRequest(BaseModel):
    """Запрос на синтез речи."""

    text: str = Field(..., max_length=5000, description="Текст для озвучивания")


@router.post("/synthesize")
async def synthesize_speech(req: TtsRequest):
    """
    Синтез речи через Inworld TTS API.
    Если INWORLD_API_KEY не задан - 503.
    """
    settings = get_settings()
    api_key = (settings.INWORLD_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="TTS не настроен (нет API ключа)")

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст пустой")

    text = fix_pronunciation(text)

    # Inworld ограничивает 2000 символов - обрезаем при необходимости
    if len(text) > INWORLD_MAX_TEXT_LENGTH:
        text = text[: INWORLD_MAX_TEXT_LENGTH - 3] + "…"

    raw_voice = (settings.INWORLD_TTS_VOICE_ID or "Dennis").strip()
    voice_id = await _resolve_voice_id(api_key, raw_voice)
    model_id = (settings.INWORLD_TTS_MODEL or "inworld-tts-1.5-max").strip()
    rate = max(0.5, min(1.5, (settings.INWORLD_TTS_SPEAKING_RATE or 0.9)))
    payload = {
        "text": text,
        "voiceId": voice_id,
        "modelId": model_id,
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": rate,
        },
    }
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(INWORLD_TTS_URL, json=payload, headers=headers)
        if r.status_code != 200:
            err_msg = r.text[:500] if r.text else f"status={r.status_code}"
            logger.warning("Inworld TTS error: %s", err_msg)
            raise HTTPException(status_code=502, detail=f"Ошибка TTS: {err_msg}")
        data = r.json()
        audio_b64 = data.get("audioContent")
        if not audio_b64:
            raise HTTPException(status_code=502, detail="Inworld не вернул аудио")
        audio_bytes = base64.b64decode(audio_b64)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except httpx.HTTPError as e:
        logger.warning("Inworld TTS httpx error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))
