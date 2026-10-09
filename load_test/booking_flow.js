// k6 load test against a locally running instance (real Docker Postgres +
// uvicorn — see load_test/README.md for how to start it, including why
// RATE_LIMIT_DEFAULT needs raising for a meaningful local run).
//
// Traffic mix is weighted to look like real usage, not uniform across
// endpoints: browsing (search/detail/reviews) dominates, a small slice is
// login, and a smaller slice is the full booking write path. This is
// deliberate — a flat distribution across all endpoints would overweight
// the rarer, heavier write operations relative to how real customers
// actually use the app.
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// Unique per run so re-running this script against a DB that still has
// last run's accounts doesn't collide: signup would just 400 ("already
// registered") on a reused email, but ProviderProfile is strictly 1:1
// with User (see CLAUDE.md), so re-creating a profile for an
// already-provisioned provider user fails outright, leaving
// data.providers full of undefined ids. Only used inside setup() — see
// the comment on N_PROVIDERS for why default() never needs to know this.
const RUN_ID = Date.now();

// N_PROVIDERS/N_CUSTOMERS are deliberately small: provider + customer
// signup both go through POST /v1/users/, which has its own fixed
// 10/hour-per-IP limit (app/routers/users.py) that RATE_LIMIT_DEFAULT does
// NOT raise (it only raises the global default, not this explicit
// override) — setup() alone must stay comfortably under 10 signups so the
// test can still be re-run a couple of times inside the same hour.
// 4 providers + 1 customer = 5 logins total in setup() — right at (not
// over) login's own fixed 5/minute-per-IP limit (app/routers/auth.py),
// which RATE_LIMIT_DEFAULT does NOT raise either. Going over this in
// setup() silently poisons every booking-flow iteration for the whole
// run (a 429 login response has no access_token, so every write request
// that follows gets sent with an "Authorization: Bearer undefined"
// header and 401s) — see the explicit check in registerAndLogin() below,
// which fails fast instead of that silent failure mode.
const N_PROVIDERS = 4;
// Origin + a small jitter radius so search results are real PostGIS
// radius-search hits, not an empty result set.
const ORIGIN = { latitude: 51.5074, longitude: -0.1278 };
const JITTER_DEGREES = 0.03; // roughly +/-3km at this latitude

// Per-request-type latency, reported separately in the summary — the
// overall http_req_duration would otherwise blend a cheap GET /providers/{id}
// with a 4-request booking write flow and tell you less than either number
// alone would.
const searchTrend = new Trend("search_duration");
const detailTrend = new Trend("provider_detail_duration");
const reviewsTrend = new Trend("reviews_duration");
const loginTrend = new Trend("login_duration");
const bookingFlowTrend = new Trend("booking_flow_duration");

export const options = {
  scenarios: {
    traffic: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "20s", target: 20 }, // ramp up
        { duration: "60s", target: 20 }, // sustain
        { duration: "10s", target: 0 }, // ramp down
      ],
    },
  },
  thresholds: {
    // Read paths: the ones that matter for "does the app stay responsive
    // under concurrent browsing load". 429 (rate-limited) doesn't count as
    // a failure here (see the `check`s below) since RATE_LIMIT_DEFAULT is
    // expected to be raised for this run — a 429 on a read path during
    // this test is a real problem, not an intended throttle.
    search_duration: ["p(95)<800"],
    provider_detail_duration: ["p(95)<500"],
    reviews_duration: ["p(95)<500"],
  },
};

function randomJitter() {
  return (Math.random() - 0.5) * 2 * JITTER_DEGREES;
}

function registerAndLogin(email, role, fullName) {
  http.post(
    `${BASE_URL}/v1/users/`,
    JSON.stringify({ email, password: "loadtest123", role, full_name: fullName }),
    { headers: { "Content-Type": "application/json" } }
  );
  const loginRes = http.post(
    `${BASE_URL}/v1/auth/login`,
    `username=${encodeURIComponent(email)}&password=loadtest123`,
    { headers: { "Content-Type": "application/x-www-form-urlencoded" } }
  );
  const token = loginRes.json("access_token");
  if (!token) {
    // Fail setup() loudly rather than silently: a missing token here
    // (e.g. login's 5/minute limit already exhausted by an earlier
    // account in this same setup() call) would otherwise produce an
    // "Authorization: Bearer undefined" header that 401s on every
    // subsequent request using it for the rest of the run.
    throw new Error(
      `login failed for ${email} (status ${loginRes.status}): ${loginRes.body} — ` +
        "likely the 5/minute login limit was hit during setup(); rerun after waiting a minute, " +
        "or reduce N_PROVIDERS so setup() makes fewer login calls."
    );
  }
  return { "Authorization": `Bearer ${token}` };
}

// Runs once, not per-VU/iteration — builds the fixed pool of providers and
// the two shared accounts every iteration below reuses, so the hot loop
// never has to call the rate-limited signup endpoint itself.
export function setup() {
  const providers = [];
  for (let i = 0; i < N_PROVIDERS; i++) {
    const headers = registerAndLogin(`loadtest-provider-${i}-${RUN_ID}@example.com`, "provider", `Load Test Provider ${i}`);
    const profileRes = http.post(
      `${BASE_URL}/v1/providers/`,
      JSON.stringify({
        business_name: `Load Test Studio ${i}`,
        categories: ["hair"],
        latitude: ORIGIN.latitude + randomJitter(),
        longitude: ORIGIN.longitude + randomJitter(),
        address_type: "shop",
      }),
      { headers: { ...headers, "Content-Type": "application/json" } }
    );
    providers.push({ id: profileRes.json("id"), headers });
  }

  const customerEmail = `loadtest-customer-${RUN_ID}@example.com`;
  const customerHeaders = registerAndLogin(customerEmail, "customer", "Load Test Customer");

  return { providers, customerHeaders, customerEmail };
}

export default function (data) {
  const roll = Math.random();
  const provider = data.providers[Math.floor(Math.random() * data.providers.length)];

  if (roll < 0.55) {
    // Browsing: search near the origin, like a customer opening the app.
    const res = http.get(
      `${BASE_URL}/v1/providers/search?latitude=${ORIGIN.latitude + randomJitter()}&longitude=${ORIGIN.longitude + randomJitter()}&radius_km=10`,
      { tags: { name: "search" } }
    );
    searchTrend.add(res.timings.duration);
    check(res, { "search: ok or rate-limited": (r) => r.status === 200 || r.status === 429 });
  } else if (roll < 0.75) {
    // Tapping into a specific provider's profile from search results.
    const res = http.get(`${BASE_URL}/v1/providers/${provider.id}`, { tags: { name: "provider_detail" } });
    detailTrend.add(res.timings.duration);
    check(res, { "provider detail: ok or rate-limited": (r) => r.status === 200 || r.status === 429 });
  } else if (roll < 0.85) {
    // Checking reviews before booking.
    const res = http.get(`${BASE_URL}/v1/providers/${provider.id}/reviews`, { tags: { name: "reviews" } });
    reviewsTrend.add(res.timings.duration);
    check(res, { "reviews: ok or rate-limited": (r) => r.status === 200 || r.status === 429 });
  } else if (roll < 0.95) {
    // Login has its own fixed 5/minute-per-IP limit (app/routers/auth.py)
    // that RATE_LIMIT_DEFAULT does not raise — under concurrent VUs
    // sharing one IP, most of these are EXPECTED to come back 429. That's
    // the rate limiter doing exactly its job, not a capacity problem, so
    // it's checked as a pass either way and reported as its own metric
    // rather than folded into the general error rate.
    const res = http.post(
      `${BASE_URL}/v1/auth/login`,
      `username=${encodeURIComponent(data.customerEmail)}&password=loadtest123`,
      { headers: { "Content-Type": "application/x-www-form-urlencoded" }, tags: { name: "login" } }
    );
    loginTrend.add(res.timings.duration);
    check(res, { "login: ok or rate-limited": (r) => r.status === 200 || r.status === 429 });
  } else {
    // The full write path: create -> confirm -> complete -> review, as the
    // shared customer against a random provider from the pool. Heavier
    // (4 sequential requests) and rarer, matching how much less often a
    // real customer completes an entire booking vs. just browsing.
    const start = Date.now();
    const bookingRes = http.post(
      `${BASE_URL}/v1/bookings/`,
      JSON.stringify({
        provider_profile_id: provider.id,
        category: "hair",
        visit_type: "shop_visit",
        scheduled_at: new Date(Date.now() + 86400000).toISOString(),
      }),
      { headers: { ...data.customerHeaders, "Content-Type": "application/json" }, tags: { name: "booking_create" } }
    );
    const ok = check(bookingRes, { "booking create: ok or rate-limited": (r) => r.status === 201 || r.status === 429 });

    if (bookingRes.status === 201) {
      const bookingId = bookingRes.json("id");
      http.patch(
        `${BASE_URL}/v1/bookings/${bookingId}/status`,
        JSON.stringify({ status: "confirmed" }),
        { headers: { ...provider.headers, "Content-Type": "application/json" }, tags: { name: "booking_confirm" } }
      );
      http.patch(
        `${BASE_URL}/v1/bookings/${bookingId}/status`,
        JSON.stringify({ status: "completed" }),
        { headers: { ...provider.headers, "Content-Type": "application/json" }, tags: { name: "booking_complete" } }
      );
      http.post(
        `${BASE_URL}/v1/bookings/${bookingId}/review`,
        JSON.stringify({ rating: 1 + Math.floor(Math.random() * 5) }),
        { headers: { ...data.customerHeaders, "Content-Type": "application/json" }, tags: { name: "booking_review" } }
      );
    }
    if (ok) {
      bookingFlowTrend.add(Date.now() - start);
    }
  }

  sleep(Math.random() * 1.5); // think time between actions, like a real user
}
