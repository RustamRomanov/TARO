"""Support: send feedback (complaint/suggestion)."""
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_telegram_user_id_from_init_data
from app.core.uploads_dir import get_uploads_root
from app.db.models import Feedback, FeedbackAttachment
from app.db.session import get_db

router = APIRouter(prefix="/support", tags=["support"])
_MAX_IMAGE_SIZE = 2 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}


def _guess_extension(content_type: str, filename: str) -> str:
    if content_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    lowered = (filename or "").lower()
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        return ".jpg"
    if lowered.endswith(".png"):
        return ".png"
    if lowered.endswith(".webp"):
        return ".webp"
    return ".img"


async def _save_feedback_image(feedback_id: int, image: UploadFile) -> str:
    content_type = (image.content_type or "").lower()
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Допустимы только JPG/PNG/WEBP изображения.")
    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Файл изображения пустой.")
    if len(payload) > _MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Размер изображения не должен превышать 2 МБ.")

    ext = _guess_extension(content_type, image.filename or "")
    upload_dir = get_uploads_root() / "support" / str(feedback_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"user_{uuid4().hex}{ext}"
    file_path = upload_dir / file_name
    file_path.write_bytes(payload)
    return f"/uploads/support/{feedback_id}/{file_name}"


class SendFeedbackRequest(BaseModel):
    init_data: str = ""
    message: str = ""


class SendFeedbackResponse(BaseModel):
    detail: str
    feedback_id: int | None = None


@router.post("/send", response_model=SendFeedbackResponse)
async def send_feedback(
    payload: SendFeedbackRequest,
    db: AsyncSession = Depends(get_db),
) -> SendFeedbackResponse:
    """Save user feedback (message) to the Feedback table. Requires valid init_data."""
    telegram_id = get_telegram_user_id_from_init_data(payload.init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")

    text = (payload.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is required.")

    feedback = Feedback(user_id=telegram_id, message=text, status="unread_unresolved")
    db.add(feedback)
    await db.flush()
    return SendFeedbackResponse(detail="Сообщение отправлено.", feedback_id=feedback.id)


@router.post("/send-form", response_model=SendFeedbackResponse)
async def send_feedback_form(
    init_data: str = Form(""),
    message: str = Form(""),
    image: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
) -> SendFeedbackResponse:
    """Save user feedback with optional image attachment."""
    telegram_id = get_telegram_user_id_from_init_data(init_data)
    if not telegram_id:
        raise HTTPException(status_code=401, detail="Invalid or missing init_data.")
    text = (message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is required.")

    feedback = Feedback(user_id=telegram_id, message=text, status="unread_unresolved")
    db.add(feedback)
    await db.flush()

    if image is not None:
        image_path = await _save_feedback_image(feedback.id, image)
        db.add(FeedbackAttachment(feedback_id=feedback.id, role="user", image_path=image_path))

    return SendFeedbackResponse(detail="Обращение отправлено.", feedback_id=feedback.id)
