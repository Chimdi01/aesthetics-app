"""
Regression guard for the scariest bug from setting up Alembic: without
this filter, `alembic revision --autogenerate` compares our two app
tables against the ENTIRE database and proposes DROPping every table
PostGIS's extensions created (~70 of them). include_object is what
alembic/env.py uses to prevent that — tested directly here since
importing alembic/env.py itself would try to run a real migration as a
side effect of the import.
"""
from app.alembic_support import include_object


def test_excludes_reflected_table_with_no_model_counterpart():
    # This is the PostGIS-extension-table case: found in the DB
    # (reflected=True), nothing in our SQLAlchemy models to compare
    # against (compare_to=None) -> must NOT be considered for autogenerate.
    assert include_object(None, "spatial_ref_sys", "table", True, None) is False


def test_includes_reflected_table_that_matches_a_model():
    # One of our own tables, already existing in the DB and reflected,
    # but WITH a matching model to diff against -> must stay included so
    # column-level changes still get picked up.
    assert include_object(None, "users", "table", True, object()) is True


def test_includes_non_reflected_table():
    # A table that only exists in our models so far (not yet reflected
    # from the DB) -> normal "new table" case, must stay included.
    assert include_object(None, "provider_profiles", "table", False, None) is True


def test_includes_non_table_objects_regardless():
    # Columns, indexes, etc. are never filtered by this function —
    # only whole reflected-and-unmatched tables are.
    assert include_object(None, "some_column", "column", True, None) is True
