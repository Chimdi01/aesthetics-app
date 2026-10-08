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
   API tester from your code. Every endpoint is versioned under `/v1`
   (see `app/routers/v1.py`) — `/health` and `/health/ready` are the only
   exceptions, since those are infrastructure checks, not part of the
   API contract. Create a provider user via `POST /v1/users/`
   (`role: provider`), log in via `POST /v1/auth/login`, then use the
   token to create their profile via `POST /v1/providers/`. Create a
   customer user the same way, then book that provider via
   `POST /v1/bookings/`.

## Creating an admin account
There is no API endpoint that grants the admin role — `POST /v1/users/`
rejects `role: admin` outright (see `app/schemas/user.py`), on purpose:
a solo-operator app doesn't need "promote to admin" as attack surface.
Sign up normally as `customer` or `provider`, then promote directly in
Postgres:
```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```
Log in again afterward — admin-only endpoints (`/v1/admin/...`) check
the role on each request, not something baked into the existing token.

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
- `app/routers/` — the endpoints themselves, one module per concern:
  `users`, `auth`, `providers` (profile CRUD + search),
  `provider_availability`, `portfolio`, `bookings` (lifecycle only),
  `reviews`, `messages`, `verification` (self-service ID submission),
  `admin` (ID verification review; the natural home for future
  admin-facing features like reporting/flagging)
- `app/booking_access.py` — shared booking-party authorization, used by
  both `bookings` and `messages` routers
- `app/verification_storage.py` — identity-document storage, deliberately
  separate from `app/storage.py` (private, never resized — see
  `CLAUDE.md`)
- `app/main.py` — wires it all together, what you actually run
- `alembic/` — schema migrations; `alembic/env.py` is async-aware and
  reads its DB URL from `app.config.settings`
- `tests/unit/` — no DB, no HTTP, pure logic
- `tests/regression/` — full endpoint tests against a real test DB

## Next up
Stripe Connect integration, reporting/flagging, AR try-on, mobile/web
frontends.
