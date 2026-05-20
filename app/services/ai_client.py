"""AI client: OpenAI primary (если задан), иначе AI_*; DeepSeek - запасной текст; GPT - запасной vision."""
import asyncio
import base64
import json
import logging
import time
from typing import Any, Dict, Optional

from openai import AsyncOpenAI, BadRequestError

from app.core.config import get_settings
from app.services.token_usage_service import schedule_save_token_usage

logger = logging.getLogger(__name__)

OPENAI_BASE = "https://api.openai.com/v1"


def _openai_completion_limit_kwargs(model: str, max_tokens: int) -> dict[str, int]:
    """Новые модели OpenAI требуют max_completion_tokens вместо max_tokens."""
    m = (model or "").lower()
    if "gpt-5" in m or m.startswith("o1") or m.startswith("o3") or "o4-mini" in m:
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _normalize_base_url(url: str, default: str) -> str:
    """Ensure base_url has http(s) scheme so httpx doesn't raise UnsupportedProtocol."""
    u = (url or "").strip()
    if not u:
        return default
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return f"https://{u}"


class AIServiceClient:
    """OpenAI основной (если OPENAI_API_KEY задан); иначе AI_*; DeepSeek - fallback текст; GPT - fallback vision."""

    def __init__(self) -> None:
        settings = get_settings()
        openai_key = (settings.OPENAI_API_KEY or "").strip()
        ai_key = (settings.AI_API_KEY or "").strip()

        self._client: Optional[AsyncOpenAI] = None
        self._text_model = ""
        self._vision_model = ""
        self._vision_fallback_client: Optional[AsyncOpenAI] = None
        self._vision_fallback_model = ""

        gpt_vision_key = getattr(settings, "OPENAI_GPT_API_KEY", "") or ""
        gpt_vision_key = gpt_vision_key.strip() if isinstance(gpt_vision_key, str) else ""

        use_openai_primary = bool(openai_key)
        self._primary_provider = "openai"
        if use_openai_primary:
            self._client = AsyncOpenAI(api_key=openai_key, base_url=OPENAI_BASE)
            self._text_model = (settings.AI_TEXT_MODEL or "").strip() or "gpt-4o-mini"
            self._vision_model = (settings.AI_VISION_MODEL or "").strip() or "gpt-4o"
            logger.info("OpenAI primary (text=%s, vision=%s)", self._text_model, self._vision_model)
        if ai_key and (settings.AI_BASE_URL or settings.AI_TEXT_MODEL or settings.AI_VISION_MODEL) and not use_openai_primary:
            self._client = AsyncOpenAI(
                api_key=ai_key,
                base_url=_normalize_base_url(settings.AI_BASE_URL, OPENAI_BASE),
            )
            self._text_model = (settings.AI_TEXT_MODEL or "").strip() or "gpt-4o-mini"
            self._vision_model = (settings.AI_VISION_MODEL or settings.AI_TEXT_MODEL or "").strip() or self._text_model
            base = (settings.AI_BASE_URL or "").lower()
            self._primary_provider = "vsegpt" if "vsegpt" in base else "openai"
        if gpt_vision_key:
            self._vision_fallback_client = AsyncOpenAI(api_key=gpt_vision_key, base_url=OPENAI_BASE)
            self._vision_fallback_model = "gpt-4o"
            logger.info("Vision fallback: OPENAI_GPT_API_KEY (gpt-4o)")

        # Запасной текст: DeepSeek
        self._fallback_client: Optional[AsyncOpenAI] = None
        self._fallback_text_model = ""
        deepseek_key = getattr(settings, "DEEPSEEK_API_KEY", "") or ""
        if deepseek_key:
            self._fallback_client = AsyncOpenAI(
                api_key=deepseek_key,
                base_url=_normalize_base_url(getattr(settings, "DEEPSEEK_BASE_URL", "") or "", "https://api.deepseek.com"),
            )
            self._fallback_text_model = getattr(settings, "DEEPSEEK_TEXT_MODEL", "") or "deepseek-chat"
            logger.info("DeepSeek fallback (text only, model=%s)", self._fallback_text_model)

    def _usage_from_response(self, response: Any) -> tuple[int, int, int, int]:
        """(prompt_tokens, completion_tokens, total_tokens, cached_tokens)."""
        u = getattr(response, "usage", None)
        if not u:
            return 0, 0, 0, 0
        pt = getattr(u, "prompt_tokens", None) or 0
        ct = getattr(u, "completion_tokens", None) or 0
        tt = getattr(u, "total_tokens", None) or (pt + ct)
        cached = 0
        details = getattr(u, "prompt_tokens_details", None)
        if details and getattr(details, "cached_tokens", None) is not None:
            cached = int(details.cached_tokens)
        return pt, ct, tt, cached

    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 280,
        user_id: Optional[int] = None,
        profile_id: Optional[int] = None,
        feature_type: str = "unknown",
        model_override: Optional[str] = None,
    ) -> str:
        """Generate text response. Tries primary, then DeepSeek fallback. Records usage when user_id set."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        last_error: Optional[Exception] = None
        primary_model = (model_override or "").strip() or self._text_model
        if self._client and primary_model:
            for attempt in range(2):
                try:
                    t0 = time.perf_counter()
                    token_kw = _openai_completion_limit_kwargs(primary_model, max_tokens)
                    try:
                        response = await self._client.chat.completions.create(
                            model=primary_model,
                            messages=messages,
                            **token_kw,
                        )
                    except BadRequestError as exc0:
                        err_txt = str(getattr(exc0, "body", None) or exc0)
                        if (
                            "max_completion_tokens" in err_txt
                            and "max_tokens" in err_txt.lower()
                            and "max_completion_tokens" not in token_kw
                        ):
                            response = await self._client.chat.completions.create(
                                model=primary_model,
                                messages=messages,
                                max_completion_tokens=max_tokens,
                            )
                        else:
                            raise exc0
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    pt, ct, tt, cached = self._usage_from_response(response)
                    schedule_save_token_usage(
                        user_id=user_id,
                        feature_type=feature_type,
                        provider=self._primary_provider,
                        model=primary_model,
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        total_tokens=tt,
                        cached_tokens=cached,
                        latency_ms=latency_ms,
                        profile_id=profile_id,
                    )
                    return response.choices[0].message.content or ""
                except BadRequestError as exc:
                    logger.warning("Primary AI text bad request, trying fallback: %s", getattr(exc, "body", None) or str(exc))
                    last_error = exc
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        logger.warning("Primary AI text failed (attempt %s), retrying then fallback: %s", attempt + 1, exc)
                        await asyncio.sleep(2.0)
                    else:
                        logger.warning("Primary AI text failed after retry, trying DeepSeek fallback: %s", exc)
        if not (self._fallback_client and self._fallback_text_model) and last_error:
            logger.error(
                "Primary AI failed and no DeepSeek fallback configured (set DEEPSEEK_API_KEY for automatic fallback): %s",
                last_error,
            )
        if self._fallback_client and self._fallback_text_model:
            try:
                t0 = time.perf_counter()
                response = await self._fallback_client.chat.completions.create(
                    model=self._fallback_text_model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                pt, ct, tt, cached = self._usage_from_response(response)
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider="deepseek",
                    model=self._fallback_text_model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    cached_tokens=cached,
                    latency_ms=latency_ms,
                    profile_id=profile_id,
                )
                logger.info("DeepSeek fallback used for text")
                return response.choices[0].message.content or ""
            except Exception as exc:
                logger.exception("DeepSeek text fallback failed: %s", exc)
                if last_error is None:
                    last_error = exc
        if last_error:
            if user_id is not None:
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider=self._primary_provider or "openai",
                    model=self._text_model or "unknown",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cached_tokens=0,
                    error=True,
                    profile_id=profile_id,
                )
            raise last_error
        raise RuntimeError("No AI provider configured: set OPENAI_API_KEY, AI_API_KEY or DEEPSEEK_API_KEY")

    async def _vision_create(
        self, client: AsyncOpenAI, model: str, messages: list
    ) -> tuple[str, Any]:
        """Call vision model; returns (content, response) for usage extraction."""
        try:
            vk = _openai_completion_limit_kwargs(model, 1024)
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    **vk,
                )
            except BadRequestError as exc0:
                err_txt = str(getattr(exc0, "body", None) or exc0)
                if "max_completion_tokens" in err_txt and "max_tokens" in err_txt.lower():
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        max_completion_tokens=1024,
                    )
                else:
                    raise exc0
        except BadRequestError:
            vk2 = _openai_completion_limit_kwargs(model, 1024)
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **vk2,
                )
            except BadRequestError as exc1:
                err_txt = str(getattr(exc1, "body", None) or exc1)
                if "max_completion_tokens" in err_txt and "max_tokens" in err_txt.lower():
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=1024,
                    )
                else:
                    raise exc1
        return (response.choices[0].message.content or "{}", response)

    async def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        system_prompt: Optional[str] = None,
        user_id: Optional[int] = None,
        profile_id: Optional[int] = None,
        feature_type: str = "vision",
    ) -> Dict:
        """Analyze image and return JSON. Only primary (DeepSeek API не поддерживает vision)."""
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                    },
                ],
            }
        )
        last_exc: Optional[Exception] = None
        if self._client and self._vision_model:
            try:
                content, response = await self._vision_create(self._client, self._vision_model, messages)
                pt, ct, tt, cached = self._usage_from_response(response)
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider=self._primary_provider,
                    model=self._vision_model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    cached_tokens=cached,
                    profile_id=profile_id,
                )
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            except Exception as exc:
                logger.warning("Primary vision failed, trying GPT fallback: %s", exc)
                last_exc = exc
                if user_id is not None:
                    schedule_save_token_usage(
                        user_id=user_id,
                        feature_type=feature_type,
                        provider=self._primary_provider or "openai",
                        model=self._vision_model or "unknown",
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        cached_tokens=0,
                        error=True,
                        profile_id=profile_id,
                    )
        if self._vision_fallback_client and self._vision_fallback_model:
            try:
                content, response = await self._vision_create(
                    self._vision_fallback_client, self._vision_fallback_model, messages
                )
                pt, ct, tt, cached = self._usage_from_response(response)
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider="openai",
                    model=self._vision_fallback_model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    cached_tokens=cached,
                    profile_id=profile_id,
                )
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            except Exception as exc:
                logger.exception("Vision fallback (GPT) failed: %s", exc)
                if last_exc is None:
                    last_exc = exc
                if user_id is not None:
                    schedule_save_token_usage(
                        user_id=user_id,
                        feature_type=feature_type,
                        provider="openai",
                        model=self._vision_fallback_model or "unknown",
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        cached_tokens=0,
                        error=True,
                        profile_id=profile_id,
                    )
        if last_exc:
            raise last_exc
        raise RuntimeError("No vision provider configured: set OPENAI_API_KEY or AI_API_KEY and AI_VISION_MODEL")

    async def analyze_compatibility(
        self,
        img1: bytes,
        img2: bytes,
        prompt: str,
        system_prompt: Optional[str] = None,
        user_id: Optional[int] = None,
        profile_id: Optional[int] = None,
        feature_type: str = "compatibility",
    ) -> Dict:
        """Analyze compatibility by two images. Only primary (DeepSeek vision не поддерживается)."""
        image1_base64 = base64.b64encode(img1).decode("utf-8")
        image2_base64 = base64.b64encode(img2).decode("utf-8")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image1_base64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image2_base64}"}},
                ],
            }
        )
        last_exc = None
        if self._client and self._vision_model:
            try:
                content, response = await self._vision_create(self._client, self._vision_model, messages)
                pt, ct, tt, cached = self._usage_from_response(response)
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider=self._primary_provider,
                    model=self._vision_model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    cached_tokens=cached,
                    profile_id=profile_id,
                )
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            except Exception as exc:
                logger.warning("Primary vision (compatibility) failed, trying GPT fallback: %s", exc)
                last_exc = exc
                if user_id is not None:
                    schedule_save_token_usage(
                        user_id=user_id,
                        feature_type=feature_type,
                        provider=self._primary_provider or "openai",
                        model=self._vision_model or "unknown",
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        cached_tokens=0,
                        error=True,
                        profile_id=profile_id,
                    )
        if self._vision_fallback_client and self._vision_fallback_model:
            try:
                content, response = await self._vision_create(
                    self._vision_fallback_client, self._vision_fallback_model, messages
                )
                pt, ct, tt, cached = self._usage_from_response(response)
                schedule_save_token_usage(
                    user_id=user_id,
                    feature_type=feature_type,
                    provider="openai",
                    model=self._vision_fallback_model,
                    prompt_tokens=pt,
                    completion_tokens=ct,
                    total_tokens=tt,
                    cached_tokens=cached,
                    profile_id=profile_id,
                )
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"raw": content}
            except Exception as exc:
                logger.exception("Vision fallback (GPT) failed: %s", exc)
                if last_exc is None:
                    last_exc = exc
                if user_id is not None:
                    schedule_save_token_usage(
                        user_id=user_id,
                        feature_type=feature_type,
                        provider="openai",
                        model=self._vision_fallback_model or "unknown",
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        cached_tokens=0,
                        error=True,
                        profile_id=profile_id,
                    )
        if last_exc:
            raise last_exc
        raise RuntimeError("No vision provider configured: set OPENAI_API_KEY or AI_VISION_MODEL")

    async def analyze_palm(
        self,
        image_bytes: bytes,
        user_id: Optional[int] = None,
        profile_id: Optional[int] = None,
        feature_type: str = "palm",
    ) -> Dict:
        """Analyze palm image and return JSON."""
        system_prompt = (
            "Ты профессиональный хиромант. СНАЧАЛА проверь фото:\n"
            "1. Это ЛАДОНЬ ЧЕЛОВЕКА: должна быть видна ладонь с линиями. "
            "Если это кукла, лапа животного (собака и т.п.), не ладонь - верни {\"valid\": false, \"feedback\": \"...\"}. "
            "Примеры feedback: \"На фото не ладонь человека. Сфотографируйте свою ладонь.\".\n"
            "2. Посторонние предметы: перчатки, бинты, пластыри закрывают ладонь - верни valid: false, "
            "feedback: \"Снимите перчатки/бинты для точного анализа ладони.\".\n"
            "3. Если проверка пройдена - найди и интерпретируй: Линию Жизни, Головы, Сердца, Судьбы. "
            "Формат ответа JSON: {\"valid\": true, "
            "\"life_line\": {\"score\": N, \"description\": \"...\"}, "
            "\"head_line\": {\"score\": N, \"description\": \"...\"}, "
            "\"heart_line\": {\"score\": N, \"description\": \"...\"}, "
            "\"fate_line\": {\"score\": N, \"description\": \"...\"}, "
            "\"general_prediction\": \"...\"}. "
            "Отвечай строго на русском."
        )
        prompt = "Проверь: это ладонь человека, без перчаток/бинтов. Если ок - проанализируй и верни JSON."
        return await self.analyze_image(
            image_bytes, prompt, system_prompt,
            user_id=user_id,
            profile_id=profile_id,
            feature_type=feature_type,
        )

