"""
Raw-SQL database triggers that enforce an invariant at the DB level
because no application code sits in the loop to check it otherwise —
see each trigger's own docstring for why.

These are NOT represented in SQLAlchemy's ORM metadata (triggers and
functions aren't modeled by Base.metadata), so
`Base.metadata.create_all()` — what builds the test DB, see
tests/conftest.py — never creates them on its own. The SQL here is
the single source of truth, executed by BOTH the Alembic migration
that creates it for real and tests/conftest.py's schema setup, so the
two can never drift out of sync. Written as CREATE OR REPLACE /
DROP IF EXISTS specifically so it's safe to run unconditionally and
repeatedly (every test session), not just once like a normal
migration.
"""

# Admin and provider are mutually exclusive (see CLAUDE.md's Roles
# convention). The OTHER direction (creating a ProviderProfile for an
# admin) already goes through the app and is refused there
# (app/routers/providers.py) — no trigger needed for it. THIS
# direction is different: admin is provisioned by a direct DB UPDATE
# (no API path grants it — see the existing gotcha), which bypasses
# the application entirely. A DB-level trigger is the only place left
# to enforce it.
ADMIN_PROVIDER_EXCLUSIVITY_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION prevent_admin_with_provider_profile() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.role = 'admin' AND EXISTS (
        SELECT 1 FROM provider_profiles WHERE provider_profiles.user_id = NEW.id
    ) THEN
        RAISE EXCEPTION
            'cannot set role=admin: user % already has a provider profile', NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Two separate statements, not one multi-statement string — asyncpg's
# extended query protocol rejects "cannot insert multiple commands
# into a prepared statement" if DROP and CREATE are combined into one
# execute() call.
ADMIN_PROVIDER_EXCLUSIVITY_DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_prevent_admin_with_provider_profile ON users;
"""

ADMIN_PROVIDER_EXCLUSIVITY_TRIGGER_SQL = """
CREATE TRIGGER trg_prevent_admin_with_provider_profile
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION prevent_admin_with_provider_profile();
"""
