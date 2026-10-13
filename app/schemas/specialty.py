from pydantic import BaseModel


class SpecialtyPublic(BaseModel):
    # No label field, deliberately — see app/specialties.py's docstring.
    # The client localises slug -> display text itself.
    slug: str
    categories: list[str]
