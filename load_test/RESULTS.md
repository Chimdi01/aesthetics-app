# Load test results — 2026-10-09

Run against a local machine: real Docker Postgres (`postgis/postgis:16-3.4`,
same image as production), real uvicorn (no reload, single worker,
`RATE_LIMIT_DEFAULT=100000/minute` for this run only — see README.md for
why), 20 concurrent VUs sustained for 60s (20s ramp-up, 10s ramp-down),
~1,900 iterations, ~2,200 HTTP requests.

## Numbers

| Request type | p90 | p95 | max |
|---|---|---|---|
| `GET /providers/search` (PostGIS radius search + ratings subquery) | 30ms | 38ms | 825ms |
| `GET /providers/{id}` | 18ms | 22ms | 594ms |
| `GET /providers/{id}/reviews` | 24ms | 28ms | 270ms |
| `POST /auth/login` | 7ms | 11ms | 629ms |
| Full booking write flow (create → confirm → complete → review, 4 sequential requests) | 116ms | 146ms | 1.16s |

Overall `http_req_duration` p95: 37ms. `checks_succeeded`: 100%.

## Takeaways

- **Read paths have real headroom at this concurrency.** p95 well under
  40ms for search — the heaviest read query (PostGIS `ST_DWithin` +
  outer-joined ratings aggregation) — on a local machine with no tuning
  beyond what's already in the codebase (the composite indexes, the
  GiST spatial index). This doesn't say anything about *production*
  capacity (different hardware, network, concurrency level), but it
  does say the query shape itself isn't the bottleneck at 20 concurrent
  users.
- **The global rate limiter (`200/minute` by default, keyed by client
  IP) is the actual ceiling for a single-IP source** — confirmed by
  running with it raised (`RATE_LIMIT_DEFAULT`) specifically to measure
  app/DB capacity instead of re-confirming something already covered by
  `tests/regression/test_rate_limiting.py`. This is intentional
  behavior, not a finding to fix.
- **Login's fixed `5/minute` limit (not affected by `RATE_LIMIT_DEFAULT`)
  is tight enough that it needs respecting even in test setup** — the
  first run of this script hit it during `setup()` itself (6 login calls
  for 5 provider+customer accounts, one over the limit), which silently
  produced a malformed `Authorization: Bearer undefined` header and a
  100% failure rate on the booking-flow write path for that entire run.
  Fixed by trimming `setup()` to exactly 5 logins and adding a fail-fast
  check if a token is ever missing, rather than let it propagate
  silently — see `booking_flow.js`. Worth remembering if this limit
  itself is ever tightened or loosened: it's not just a login-UX
  parameter, it's a hard ceiling on anything that needs fresh tokens
  for many accounts in a short window (test setup, a bulk admin
  operation, etc.).
- **No 5xx errors, no connection-pool exhaustion, no slow-query
  surprises** at this concurrency/data volume (4 providers, a few dozen
  bookings/reviews created during the run). This is a smoke-level load
  test, not a capacity-planning one — it didn't push toward
  `db_pool_size`'s limit (5 + 10 overflow) or attempt the "millions of
  users" scale the scaling-posture decision (see CHANGELOG.md)
  explicitly deferred tuning for. Re-run with higher `db_pool_size`,
  more VUs, and a bigger seeded dataset if/when real traffic numbers
  (or a pre-launch capacity target) exist to test against.
