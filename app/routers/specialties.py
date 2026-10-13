"""
Read-only reference data: the fine-grained specialties taxonomy, each
tagged with the category/categories it belongs to — see
app/specialties.py. Public, no auth — this is static reference data
for a client to build a filter UI from, not anything account-specific.
No labels served — see app/specialties.py's docstring and
CLAUDE.md's Locale convention.
"""
from fastapi import APIRouter

from app.schemas.specialty import SpecialtyPublic
from app.specialties import SPECIALTY_CATEGORIES

router = APIRouter(prefix="/specialties", tags=["specialties"])


@router.get("/", response_model=list[SpecialtyPublic])
async def list_specialties():
    return [
        SpecialtyPublic(slug=slug, categories=sorted(categories))
        for slug, categories in sorted(SPECIALTY_CATEGORIES.items())
    ]
