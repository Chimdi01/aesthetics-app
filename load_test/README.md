# Load testing (k6)

`booking_flow.js` simulates a realistic traffic mix against a locally
running instance (real Docker Postgres + uvicorn, not a mock) — mostly
reads (search, profile detail, reviews — the pages a browsing customer
hits far more often than they write anything), a login, and an
occasional full booking write path (create → confirm → complete →
review).

## Why not just run it against the dev server as-is

The global rate limit (`app/rate_limit.py`, default `200/minute`) is
keyed by client IP. Every k6 VU on your laptop shares the same IP, so a
real multi-concurrent-user test would just measure the rate limiter
rejecting requests with 429s, not the app/DB's actual capacity — those
are two different, both-worth-knowing things, but this script is for
the latter. `rate_limit_default` (`app/config.py`) exists specifically
so you can raise it for a local run only:

```bash
# one-time setup
docker compose up -d                      # Postgres is up
venv/bin/python -m alembic upgrade head

# terminal 1 — the app, with the per-IP cap raised for this run only
RATE_LIMIT_DEFAULT="100000/minute" venv/bin/python -m uvicorn app.main:app

# terminal 2 — the test
k6 run load_test/booking_flow.js
```

Never set `RATE_LIMIT_DEFAULT` this way in a real deployment — it exists
for this diagnostic use only, see the comment on `Settings.rate_limit_default`.

## Reading the results

k6 prints `http_req_duration` percentiles (p90/p95/p99) and
`http_req_failed` at the end. The `checks` block breaks down pass/fail
per request type tagged in the script (`search`, `provider_detail`,
`login`, `booking_flow`, etc.) via k6's `Trend`/`Rate` custom metrics —
look there first if the aggregate number looks bad, since this traffic
mix deliberately isn't uniform (search dominates, matching real usage).
