from __future__ import annotations

from pathlib import Path
from typing import Any


class TemplateRenderError(RuntimeError):
    pass


def render_template(config_path: str | Path, template_ref: str, context: dict[str, Any]) -> str:
    try:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
    except ImportError as exc:
        raise TemplateRenderError("Jinja2 is required to render configured templates") from exc

    template_path = Path(template_ref)
    if not template_path.is_absolute():
        template_path = Path(config_path).resolve().parent / template_path
    template_path = template_path.resolve()
    if not template_path.exists():
        raise TemplateRenderError(f"template does not exist: {template_path}")
    environment = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        return environment.get_template(template_path.name).render(**context).strip()
    except TemplateError as exc:
        raise TemplateRenderError(f"template render failed for {template_path}: {exc}") from exc
