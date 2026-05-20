"""
Загрузка текстов из app/data/tarot_books/ для контекста ИИ-таролога.
PDF, DOCX, TXT, MD - извлекается текст и отдаётся блоком в system prompt.
"""
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
_BOOKS_DIR = _DATA_ROOT / "tarot_books"

# Макс символов на один файл и общий лимит блока (чтобы влезать в контекст модели)
_MAX_CHARS_PER_FILE = 9_000
_MAX_TOTAL_CHARS = 22_000

_KNOWLEDGE_CACHE: str | None = None


def _extract_pdf(path: Path, max_chars: int) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed, skipping PDF %s", path.name)
        return ""
    out: list[str] = []
    total = 0
    try:
        reader = PdfReader(path)
        for page in reader.pages:
            if total >= max_chars:
                break
            text = page.extract_text()
            if text:
                cleaned = re.sub(r"\s+", " ", text).strip()
                if cleaned:
                    out.append(cleaned)
                    total += len(cleaned)
    except Exception as e:
        logger.warning("PDF %s: %s", path.name, e)
    return " ".join(out)[:max_chars]


def _extract_docx(path: Path, max_chars: int) -> str:
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx not installed, skipping DOCX %s", path.name)
        return ""
    out: list[str] = []
    try:
        doc = Document(path)
        for para in doc.paragraphs:
            if para.text:
                out.append(para.text.strip())
        text = " ".join(out)
        return re.sub(r"\s+", " ", text).strip()[:max_chars]
    except Exception as e:
        logger.warning("DOCX %s: %s", path.name, e)
        return ""


def _extract_plain(path: Path, max_chars: int) -> str:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return re.sub(r"\s+", " ", raw).strip()[:max_chars]
    except Exception as e:
        logger.warning("Plain %s: %s", path.name, e)
        return ""


def _load_file(path: Path, max_per_file: int) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        return _extract_pdf(path, max_per_file)
    if suf == ".docx":
        return _extract_docx(path, max_per_file)
    if suf in (".txt", ".md"):
        return _extract_plain(path, max_per_file)
    return ""


def load_tarot_knowledge() -> str:
    """
    Загружает текст из всех поддерживаемых файлов в tarot_books/,
    объединяет с лимитом по размеру. Результат кэшируется.
    """
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is not None:
        return _KNOWLEDGE_CACHE

    if not _BOOKS_DIR.exists() or not _BOOKS_DIR.is_dir():
        _KNOWLEDGE_CACHE = ""
        return ""

    parts: list[str] = []
    total = 0
    max_per_file = _MAX_CHARS_PER_FILE
    files = sorted(_BOOKS_DIR.iterdir())

    for path in files:
        if total >= _MAX_TOTAL_CHARS:
            break
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix.lower() not in (".pdf", ".docx", ".txt", ".md"):
            continue

        text = _load_file(path, max_per_file)
        if not text.strip():
            continue
        take = min(len(text), _MAX_TOTAL_CHARS - total)
        if take <= 0:
            break
        parts.append(f"[{path.stem}]\n{text[:take]}")
        total += take

    _KNOWLEDGE_CACHE = "\n\n---\n\n".join(parts)[:_MAX_TOTAL_CHARS]
    logger.info("Tarot knowledge loaded: %d chars from %d files", len(_KNOWLEDGE_CACHE), len(parts))
    return _KNOWLEDGE_CACHE


def get_tarot_expert_system_prefix() -> str:
    """
    Возвращает блок для добавления в system prompt таро:
    роль эксперта + контекст из книг (если загружен).
    """
    knowledge = load_tarot_knowledge()
    voice = (
        " Пиши простым разговорным русским, короткими фразами. Без канцелярита и штампов вроде "
        "«поэтапно», «по фактам», «вектор развития», «синергия», «узел выбора», «точка приложения усилий», если можно сказать проще. "
        "При интерпретации каждой карты строго соблюдай тип карты: Старший Аркан толкуй как архетипическую личность, судьбоносный урок или глубинную силу; "
        "Придворный Аркан (Паж, Рыцарь, Король, Королева) толкуй как человека или личностную черту с акцентом на характер, роль, возраст и степень влияния; "
        "Младший Аркан (числовой, от Туза до Десятки) толкуй как ситуацию, процесс, динамику и обстоятельства, не как портрет человека. "
        "Если карта перевёрнутая: для Старших это блокировка, искажение или теневой аспект; для Придворных это негативные черты человека или влияние против пользователя; для Младших это препятствия, задержки и скрытые проблемы. "
        "Пользователь уже видит карту: не перечисляй подряд весь рисунок. "
        "Если в запросе есть описание изображения карты, опирайся на него для образов и смыслов и не добавляй предметы, которых там нет. "
        "Правила по типам карт дополняют анализ изображения, а не заменяют его: во всех раскладах (включая финансовые, любовные и кельтский) обязательно учитывай переданное описание изображения карты. "
        "Если надёжного описания иллюстрации в запросе нет, не придумывай сцену карты (свечи, музыка, танцы, ангел, труба, толпа и т.п.): давай архетип и значение по названию и типу карты. "
        "Учебниковые картинки других колод (в том числе классический Rider-Waite) не подставляй, если они не совпадают с переданным описанием изображения карты. "
        "Каждый ответ делай по-своему, не повторяй одни и те же обороты между раскладами. Отвечай только на русском. "
        "В тексте для пользователя не употребляй слово «визуал»: используй естественные формулировки «на карте изображено» или «по образу карты». "
        "Не используй длинное тире (символ «длинное тире»), вместо него двоеточие, запятая или дефис."
    )
    if not knowledge.strip():
        return (
            "Ты опытный таролог. Тон тёплый, по-человечески, как будто объясняешь другу за чаем."
            + voice
        )
    return (
        "Ты опытный таролог. Ниже - выдержки из книг для опоры на традицию; не копируй дословно и не уходи в академический стиль. "
        "Если в запросе есть подсказка по иллюстрации колоды, используй её для смысла и символики, не для пересказа картинки пользователю.\n\n"
        "--- КОНТЕКСТ ИЗ ИСТОЧНИКОВ ---\n"
        f"{knowledge}\n\n"
        "--- КОНЕЦ КОНТЕКСТА ---\n\n"
        "Тон тёплый, по-человечески."
        + voice
    )
