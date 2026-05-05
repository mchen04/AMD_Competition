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

    template_path = _resolve_template_path(config_path, template_ref)
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


def _resolve_template_path(config_path: str | Path, template_ref: str) -> Path:
    template_path = Path(template_ref).expanduser()
    if template_path.is_absolute():
        return template_path.resolve()

    config_dir = Path(config_path).resolve().parent
    project_root = Path(__file__).resolve().parents[1]
    candidates = [
        config_dir / template_path,
        project_root / template_path,
    ]

    parts = template_path.parts
    if "templates" in parts:
        template_tail = Path(*parts[parts.index("templates") :])
        candidates.extend(
            [
                project_root / template_tail,
            ]
        )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return (config_dir / template_path).resolve()
