"""Ответы Jinja2 в стиле Starlette 0.37+: первым аргументом Request (не legacy name, context)."""

from typing import Any, cast

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response


def template_page(
    templates: Jinja2Templates,
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> Response:
    payload = dict(context or ())
    payload.pop("request", None)
    return cast(
        Response,
        templates.TemplateResponse(request, name, payload, status_code=status_code),
    )
