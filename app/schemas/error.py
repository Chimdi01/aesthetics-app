"""
The error envelope's shape, for OpenAPI documentation only — nothing
in app/main.py constructs these models directly (building a Pydantic
model just to immediately dump it back to a dict would be pure
overhead on every error response); they exist so the generated
OpenAPI schema, and therefore the generated TypeScript client, knows
the shape. Keep this in sync with app/main.py's handlers by hand.
"""
from pydantic import BaseModel


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ErrorResponse(BaseModel):
    error_code: str
    detail: str
    params: dict[str, object] | None = None
    fields: list[FieldError] | None = None
    request_id: str | None = None
