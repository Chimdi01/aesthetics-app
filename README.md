# Aesthetics App API

## What's here
A FastAPI + async SQLAlchemy + Postgres marketplace API: `User` (customer/
provider/admin), `ProviderProfile` (1:1 with a provider `User`, tagged with
one or more `ServiceCategory` specialties), `Booking` (customer books a
provider for a category, shop-visit or house-call, with a
requested→confirmed→completed/cancelled status flow), JWT auth
(`/auth/login`), and Alembic migrations for schema changes.

## Run it locally

1. Start Postgres (with PostGIS, which we'll need soon for location search):
   ```
   docker compose up -d
   ```

2. Create a virtual environment and install dependencies (use
   `requirements-dev.txt` instead if you also want to run tests):
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy the env file:
   ```
   cp .env.example .env
   ```

4. Bring the database schema up to date:
   ```
   alembic upgrade head
   ```

5. Run the API — use `python -m uvicorn`, not bare `uvicorn`, or it can
   resolve to the wrong (non-venv) Python on some machines:
   ```
   python -m uvicorn app.main:app --reload
   ```

6. Open http://localhost:8000/docs — FastAPI auto-generates an interactive
   API tester from your code. Create a provider user via `POST /users/`
   (`role: provider`), log in via `POST /auth/login`, then use the token to
   create their profile via `POST /providers/`. Create a customer user the
   same way, then book that provider via `POST /bookings/`.

## Run the tests
```
pip install -r requirements-dev.txt
python -m pytest
```
Tests run against a separate `aesthetics_test_db` database on the same
Postgres container — created automatically, never touches your dev data.

## File-by-file, what to actually understand
- `app/config.py` — settings from environment, never hardcoded secrets
- `app/database.py` — the async DB connection + the `get_db` dependency
  pattern FastAPI uses everywhere
- `app/models/` — the actual Postgres table definitions (`User`,
  `ProviderProfile`, `Booking`)
- `app/schemas/` — API input/output shapes, deliberately separate from
  the DB models (so `hashed_password` can never leak into a response)
- `app/security.py` — password hashing + JWT creation/verification +
  the `get_current_user`/`get_current_provider` auth dependencies
- `app/routers/` — the endpoints themselves (`users`, `providers`, `auth`,
  `bookings`)
- `app/main.py` — wires it all together, what you actually run
- `alembic/` — schema migrations; `alembic/env.py` is async-aware and
  reads its DB URL from `app.config.settings`
- `tests/unit/` — no DB, no HTTP, pure logic
- `tests/regression/` — full endpoint tests against a real test DB

## Next up
Geospatial provider search (PostGIS), Stripe Connect integration, AR
try-on, mobile/web frontends.
