"""
Pulled out of alembic/env.py so it can be unit-tested directly. env.py
runs migration logic as a side effect of being imported (that's how
Alembic's CLI invokes it), so nothing inside it is safely importable on
its own — anything meant to be tested in isolation has to live here.
"""


def include_object(object, name, type_, reflected, compare_to):
    """Without this, autogenerate diffs our two app tables against the
    ENTIRE database — including every table PostGIS's `postgis`/`tiger`/
    `topology` extensions create (spatial_ref_sys, tiger.addr, and ~70
    others). Since those aren't in our SQLAlchemy metadata, autogenerate
    treats them as "should be dropped". This skips any reflected table
    that has no counterpart in our own models, so migrations only ever
    touch tables we actually defined."""
    return not (type_ == "table" and reflected and compare_to is None)
