"""HTTP API contract — TypedDict request/response shapes plus JSON Schema export.

The single source of truth lives in ``schemas.py``. The frontend consumes
``schema.json`` (committed alongside, regenerated via ``schemas.write_schema_json``)
to codegen TypeScript types so request/response shapes stay aligned.
"""

from .schemas import (
    API_REQUEST_SCHEMAS,
    API_RESPONSE_SCHEMAS,
    SSE_EVENTS,
    build_schema_document,
    write_schema_json,
)

__all__ = [
    "API_REQUEST_SCHEMAS",
    "API_RESPONSE_SCHEMAS",
    "SSE_EVENTS",
    "build_schema_document",
    "write_schema_json",
]
