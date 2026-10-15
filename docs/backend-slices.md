# Backend build plan: every gap, in dependency order

Nothing is deferred. The order is by dependency, not importance: later slices need the models earlier ones create. Paste the **common preamble** first in each new session, then one slice at a time.

## Common preamble (paste at the start of every slice)

```
Backend work, one slice at a time. Rules: stop after each numbered step for review; never commit; report anything surprising and any assumption you made. Read CLAUDE.md and docs/frontend-brief.md first. Money is minor units plus currency, times are UTC, user-facing text goes through i18n keys. Never add race, ethnicity or gender fields or proxies. New tables get migrations and tests. Every endpoint is covered in the regenerated OpenAPI. If a step conflicts with the codebase, say so and propose the smallest alternative before building. At the end of the slice: ruff, mypy and the full suite green, a CHANGELOG entry, and a short list of front-end-visible changes so the brief can be updated.
```

## Decisions that change the code (defaults apply if you don't choose)

| Decision | Default                                                                                                                                                                                            |
| --- |----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Live-location transport | Server-sent events for viewers, plain POST for the publisher. One instance first, behind an interface so Redis pub/sub can be added                                                                |
| Slot hold length | 10 minutes                                                                                                                                                                                         |
| Fees | 20% on a first booking from a new client (minimum £4 equivalent per currency), 3% on repeat in-app bookings, first three new-client fees waived per new provider; all configurable, none hard-coded |
| Rebook cadence defaults | Barber 28 days, nails 21, colour 56, braids 42; provider-editable                                                                                                                                  |
| Raw location points kept | 24 hours (confirm with counsel)                                                                                                                                                                    |
| Typical-price minimum sample | 10 distinct providers                                                                                                                                                                              |
| Profile listing threshold | Profile strength 60%                                                                                                                                                                               |
| Emergency numbers per market | Config values, marked unverified until checked                                                                                                                                                     |
| Number masking provider | Undecided: interface plus a fake, feature-flagged off                                                                                                                                              |
| Pro plan | Record plan and entitlements now; billing lands in Slice 8, through store in-app purchase plus Stripe on the web                                                                                                                                                   |

## What stays dormant, and why

Built and tested now, switched on later: live Stripe and Flutterwave payments (need your company accounts; sandbox works now), masked calling (needs a telephony provider), French notification copy (needs native review), and CDN delivery of images (needs infrastructure). None of this is a deferral of the build; it's an activation switch.

## Review-time guesses (calibrate after Slice 1)

Slice 1: 6 to 8 hours. Slice 2: 8 to 10. Slice 3: 8 to 10. Slice 4: 6 to 8. Slice 5: 8 to 10. Slice 6: 12 to 16. Slice 7: 6 to 8. These are guesses.

---

## Slice 1: Foundations and the service catalogue

```
Slice 1. Stop after each step.

1) Error codes. Every error response, including framework-generated ones (422 validation, unknown routes, 405, built-in 401s, 429 rate limits), uses one envelope: `error_code` (stable enum), `detail` (a human-readable English string, unchanged, used for logs and dev builds), optional `params` (safe values for placeholders such as a status), optional `fields` (for validation errors: field, code, message), and `request_id`. Add request-ID middleware that echoes X-Request-ID, and put request_id, user id and error_code on every structured log line. Define the codes in one enum module and migrate existing HTTPExceptions. Include at least: unauthenticated, invalid_credentials, invalid_code, token_invalid_or_expired, account_deactivated, forbidden, cannot_target_self, not_found, duplicate_resource, validation_failed, invalid_state, payload_too_large, rate_limited, not_implemented, provider_profile_required, slot_unavailable, outside_service_area, idempotency_conflict. Show me the envelope before changing call sites.

2) Idempotency. Add an Idempotency-Key dependency for money-relevant writes, starting with POST /v1/bookings/. Same key and payload returns the original response; same key with a different payload returns idempotency_conflict. Add a nullable idempotency_key column to Payment (no logic yet). Note a cleanup plan for old keys.

3) Age confirmation. UserCreate requires confirms_18_plus=true; store the confirmation timestamp, not a birthdate.

4) Services. New models: Service (provider_profile_id, category, name, duration_minutes, price_minor, currency copied from the profile, is_active, sort_order, offers_shop, offers_home) and ServiceAddOn (service_id, name, duration_minutes, price_minor, is_active). CRUD under /v1/providers/me/services with the provider gate; public read on the provider page. No packages yet. Report how this interacts with any existing provider price-range fields.

5) Booking and service, server-computed price. Booking creation takes service_id and chosen add-on ids. The SERVER computes service price, add-ons and total from the catalogue; the client no longer sends price or transport_fee (transport_fee is 0 until Slice 6). Snapshot service name, duration, price and add-ons onto the booking. service_id stays nullable only for legacy rows. Tests: a tampered client price is rejected or ignored.

6) Specialties and languages. Do the specialties change as agreed (allowlist with category mapping, attached to ProviderProfile, GET /v1/specialties returns slugs with categories) if not already done, and add `languages` on ProviderProfile with an allowlist of codes (start with en, fr, yo, ig, ha, wo, pcm).

7) Search upgrade. Add params: specialty (any-of), min_rating, min_price and max_price (against each provider's lowest active service price), available_on (date), and sort (best_match default, nearest, rating, price_low). Add response fields: from_price_minor with currency, next_available_at (from ProviderAvailability in the provider's timezone, excluding existing bookings; no holds yet), is_verified, languages, rating_avg, rating_count. Review the query plan with EXPLAIN and report any N+1 risk.

8) Verified flag. is_verified is derived from an approved IdentityVerification and exposed on the public profile and search results. Keep the derivation in one function, because the ID-verification approach may change to a vendor.
```

## Slice 2: Booking mechanics and discovery

```
Slice 2. Stop after each step.

1) Service kinds and packages. Add `kind` to Service from an allowlist of neutral slugs (for example short_cut, long_cut, fade, gel_manicure; no gendered names). Add ServicePackage (provider_profile_id, name, tier good|better|best, included services and add-ons, price_minor). The server validates that a package price is no more than the sum of its parts, and any "saving" is computed, never client-supplied. Bookings can reference a package; the server computes the total and snapshots it.

2) Overlap prevention. Durations now exist. Compute each booking's end time and add a Postgres exclusion constraint on tstzrange per provider for active statuses, so double-booking is impossible even under concurrency. Map violations to slot_unavailable. Add a concurrency test.

3) Slot holds. SlotHold (provider_profile_id, customer_id, start, end, expires_at, status). POST creates a hold with a 10-minute TTL (configurable) that respects the overlap constraint; booking creation can consume a hold; expired holds release lazily and via a job. Rate-limit creation. Tests for races and expiry.

4) Reschedule. POST /v1/bookings/{id}/reschedule: new time via a hold or directly, allowed by status and notice rules, writes a history row, notifies the other party with the right audience, and is idempotent.

5) Rebook and cadence. Category cadence defaults in config, provider-editable per service. GET /v1/bookings/{id}/rebook returns the prefilled provider, service and add-ons plus the next three slots matching the usual weekday and time. Add a customer endpoint listing providers due for rebooking, and per-client next-due for providers.

6) Public location fuzzing at write time. Add public_location (fuzzed for home-based providers; exact for shops) and keep the exact location private. Backfill existing rows. Search and responses use public_location only. Test that exact coordinates never appear in any response.

7) Map search. GET /v1/providers/map with a bounding box and a light payload: id, public_location, from_price_minor, currency, category, is_verified. Limit about 200 with a clustering hint. Same filters as search.

8) Typical-price statistics. Nightly aggregation per (service kind, area_key, currency) returning p25 to p75 only when at least 10 distinct providers contribute; otherwise omit. Never expose individual prices. Report whether ProviderProfile has a coarse area or city; if not, propose area_key derivation.
```

## Slice 3: The provider side

```
Slice 3. Stop after each step.

1) Handle. ProviderProfile.handle: unique, lowercase slug, reserved-word list, validated. GET /v1/p/{handle} resolves to the public profile. Used for booking links and deep links.

2) Profile strength. GET /v1/providers/me/profile-strength returns a score and the single next step, computed from: at least six portfolio photos, at least one service, availability set, verified, bio, specialties, languages, and payouts connected (stubbed until payments). Use the score as a small boost in best_match and prove it with a test. Apply the 60% listing threshold (configurable) so providers below it are not listed.

3) Portfolio posts. Add to portfolio items: caption, service_id, specialty slugs, alt_text, before/after pairing (pair_id), sort_order, soft delete. "Book this look" resolves a post to its service. Generate sized image variants (320, 640, 1080 WebP plus the existing 1600 JPEG) at upload, with a configurable public base URL so a CDN can be added later.

4) House-call setup. ProviderProfile: offers_house_calls, service_area_radius_km, up to four travel pricing bands (max_km to fee_minor), min_notice_minutes, travel_buffer_before and after minutes. Availability and overlap checks respect buffers around house calls. Validation and tests.

5) House-call eligibility gate. HouseCallEligibility: id_verified (derived), insurance_declared plus an uploaded document reviewed by admin, background_check_status (not_started, pending, clear, failed, not_available_in_market), terms_accepted_at. GET /v1/providers/me/house-call-eligibility lists missing steps. offers_house_calls can only become true when eligible. Admin review endpoints with an audit trail, following the identity-verification pattern.

6) Client notes and client list. ClientNote (provider-private, per customer; edit and delete). GET /v1/providers/me/clients returns last visit, next due, visit count and a notes flag, only for customers who have booked. Notes are deleted or exported with a customer's data request.

7) Review replies and photos. One provider reply per review with an edit window. Review photos with a show_on_profile consent flag. Reporting reuses Report.
```

## Slice 4: The customer side

```
Slice 4. Stop after each step.

1) Favourites. Favourite (user_id, provider_profile_id, unique together) with GET, POST and DELETE.

2) Saved addresses. SavedAddress (label, formatted_address, coordinates kept private, required landmark or directions text when there is no place_id, access_note, is_default), owner-only CRUD. Geocoding goes through a server-side provider interface with caching, a call cap, a fake for tests and a Google implementation behind config. Allowed countries come from market config. A provider receives an address snapshot only for a confirmed booking, inside the booking window.

3) Taste profile. CustomerTasteProfile (texture slugs from the specialties allowlist, interest categories, budget_band). GET, PUT and DELETE. Add search param for_me=true that boosts matching specialties and price band. No gender fields. Document the purpose of each field in the code.

4) Lookbook. LookbookSaved (portfolio post plus a private note) and LookbookPhoto (the customer's own before/after photos; private by default; optional sharing with a provider for one booking, with explicit consent). Export and delete included.

5) Notification extras. Report first what exists. Then ensure: push token registry, quiet hours per user in their timezone (default 21:00 to 08:00), per-category preferences with marketing off by default, and a server-enforced cap of one rebook nudge per week.

6) Market config. GET /v1/markets/{code}: currency, languages, emergency number (config, flagged unverified), rebook cadence defaults, support contacts.
```

## Slice 5: Fees, plans, credits, referrals, loyalty

```
Slice 5. Stop after each step. Built so payments can switch on later; no live money moves here.

1) Fee policy. Configurable FeePolicy: new-client percentage with a per-currency minimum and cap, repeat percentage, first N new-client fees waived per new provider. Booking gets source (marketplace or provider_link) and, at creation, a snapshot: platform_fee_minor and fee_kind (new_client, repeat, waived, none). New client means no completed booking between this customer and provider. Bookings from the provider's own link carry no fee. Provider earnings responses show a line-by-line fee breakdown. Tests for every case.

2) Plans and entitlements. ProviderPlan (free, pro, shop), trial_ends_at (60 days), an entitlements function (sms_reminders, detailed_analytics, rebook_campaigns), milestone progress toward a free Pro month. No billing yet.

3) Credit ledger. Immutable CreditEntry (user_id, currency, amount_minor, kind: welcome, referral, loyalty, goodwill, spend, expiry, reversal; booking_id nullable; expires_at; funded_by platform; created_by; idempotency_key). Balance is the sum of non-expired entries, spent oldest-expiry first. Credit is applied server-side at booking creation: it lowers what the customer pays, never what the provider earns, and the discount is capped at that booking's platform_fee_minor. Reversal on cancel or refund. Admin adjustments with an audit trail. Per-user monthly cap.

4) Referrals. ReferralCode per user. Referral (referrer, referee, status pending, qualified or rejected). A referral qualifies when the referee's first booking completes and is not refunded, after a hold period (configurable, default 7 days). Rewards go through the ledger; a provider referral grants a free Pro month once the referred provider completes three bookings. Anti-abuse: one reward per referee, no self-referral by user, phone or email, monthly caps, a flagged-for-review queue. A monthly incentive budget with a hard cap that stops new grants when reached, plus a report.

5) Loyalty. Stamps awarded per completed in-app booking, starting with one welcome stamp. At N stamps a credit is granted through the ledger, value in config. Progress endpoint. Idempotent, reversed on refund.
```

## Slice 6: House calls, trips and safety

```
Slice 6. First propose options and trade-offs for the live-location transport and pub/sub, and wait for my decision before step 3. Stop after each step.

1) Quote and service area. POST /v1/bookings/quote returns the full price breakdown including the travel fee from the provider's bands, using Routes distance, or outside_service_area. Routes sits behind an interface with a Google implementation and a fake. Quotes are cached. Booking creation recomputes everything server-side; a quote is only a preview.

2) Trip model. Trip (booking_id unique, traveller_user_id, direction, state: confirmed, on_the_way, arrived, in_progress, completed, cancelled, no_show; timestamps; sharing_started_at; sharing_ended_at; end_reason). Only the traveller can start; either side can stop; an automatic stop runs 30 minutes after the appointment start. Idempotent transitions; notifications with the right audience.

3) Location publishing. POST /v1/trips/{id}/location accepts batched points, is rate-limited, and only accepts them from the traveller inside the window. Store the latest position plus raw points with timestamps for retention. Flag impossible jumps but never block. Never use for ranking or discipline.

4) Live channel. GET /v1/trips/{id}/stream (server-sent events) for the other party, with heartbeats and Last-Event-ID, plus a polling fallback GET /v1/trips/{id}/latest. Responses include ETA and a stale flag when the last point is over two minutes old.

5) ETA. Server-side Routes calls at trip start, then about every three minutes or when the traveller strays more than 300m from the route, with a hard cap per trip (config, default 12). Store eta_seconds and the encoded polyline. Counters for cost monitoring.

6) Retention and sharing log. A job deletes raw points after 24 hours (config) and keeps a minimal trip log. GET /v1/users/me/location-sharing-log. Admin access to raw points only for an incident, with an access log.

7) Trusted-contact link. POST /v1/trips/{id}/share-link returns a signed read-only URL valid until the trip ends. The public endpoint shows position, ETA and the traveller's first name only, is rate-limited and revocable.

8) Get help and incidents. Extend Report with trip_id, kind safety, severity, assigned_to, acknowledged_at, resolved_at. An endpoint records that Get help was tapped (trip, user, time). An admin queue with a named owner from config and notifications to that owner.

9) Masked calling. A TelephonyProvider interface with a fake. Endpoints to request a masked number for a booking window that expires after the appointment. Feature-flagged off in production until a provider is chosen.

10) Privacy plumbing. An audit log for any access to location data, and location-sharing data included in the user data export and deletion.
```

## Slice 7: Payments in test mode, and the activation switches

```
Slice 7. Stop after each step. Test and sandbox keys only.

1) Stripe Connect Standard in test mode for GBP and EUR: connected-account onboarding links, direct charges with application_fee_amount from the booking's fee snapshot, idempotent webhook handling keyed by event id, refunds, and dispute state recorded. Confirm the dispute fee bills the connected account.

2) Flutterwave sandbox for NGN and XOF: subaccount creation, split payments with automatic settlement, idempotent webhooks, refunds. The platform is merchant of record here: record chargebacks and a payout reserve against the provider. Add a hold-until-completion option behind a flag, pending counsel's view on holding funds.

3) Payment model: link to booking, fee snapshot, applied credit, idempotency_key, provider-agnostic status machine. Customer pays booking total minus credit; provider payout is unaffected by credit.

4) Activation checklist document: what each live key, account and copy deliverable switches on (live payments, telephony, French notification copy, CDN base URL), with the exact config for each.
```

## Slice 8: Subscriptions and entitlements

```
Slice 8: subscriptions. Requires Slice 5 (plans and entitlements). Stop after each step.

Context: store rules decide how we may charge. Anything that unlocks features inside the app (Pro for providers, any customer membership) must be sold through Apple in-app purchase and Google Play billing in most storefronts; bookings and physical products are real-world goods and stay on Stripe and Flutterwave. Verify the current rules and tell me anything that contradicts this before building.

1) Report what Slice 5 built for ProviderPlan and entitlements, and propose the smallest change to support: monthly and yearly terms; a customer membership tier as well as the provider Pro tier; and several purchase channels for the same entitlement.

2) Subscription model: subject (user or provider profile), tier, term (monthly or yearly), status (trialing, active, grace, on_hold, cancelled, expired), current_period_end, cancel_at_period_end, channel (apple, google, stripe, manual), external ids, price_minor and currency as sold, and trial_ends_at. Entitlements are derived from status, never set by hand, and one entitlements function serves every channel. A manual channel lets me grant Pro for support or a referral reward, with an audit trail.

3) Verification: POST /v1/subscriptions/verify takes a store receipt or purchase token, verifies it server-side with Apple or Google, and links it to the signed-in user. Store-to-server notifications (Apple App Store Server Notifications, Google Play Real-time Developer Notifications) update status: renewal, cancellation, billing retry, grace period, refund, upgrade, downgrade. Handle them idempotently by notification id and treat them as the source of truth; a client claim alone never grants an entitlement. Report whether to integrate the stores directly or through a subscription service such as RevenueCat, with the trade-offs.

4) Stripe subscriptions for the web channel, with the same entitlement outcome, so a provider who subscribes on the web is Pro in the app too.

5) Yearly pricing: ten months' price for twelve by default, per currency, in config. Add a note that naira pricing must be reviewed at least yearly because of currency movement. Never hard-code prices.

6) Grace and dunning: on a failed renewal keep entitlements through the store's grace period, notify the subscriber, and downgrade cleanly afterwards. Downgrading never deletes data; it only hides features (a Pro provider's past analytics stay, they just cannot see new reports).

7) Refunds and chargebacks revoke entitlements immediately. Reconciliation job: daily, compare our status with the stores and report drift.

8) Tests: a fake store verifier; every notification type; replayed notifications; a receipt belonging to another user is rejected; grace then expiry; refund revokes; manual grants expire; entitlements identical across channels.

```

## Slice 9: Product marketplace (v1)

```
Slice 9: product marketplace. Requires Slice 5 (fees, credits) and ideally Slice 7 (payments). Stop after each step.

v1 boundaries, which I may lift later: physical goods only (digital goods would fall under store in-app purchase rules); seller and buyer in the same market, so no cross-border customs or import VAT yet; one seller per order, because Stripe direct charges settle to a single connected account, so a basket spanning sellers splits into one order per seller.

1) Seller capability. Sellers are providers selling their own products, or brands that do not offer services. Report how to add "seller" to the existing capabilities model without disturbing customer and provider. Brands need a business profile (legal name, registration number, contact, returns address, returns policy text) and the same payout onboarding as providers.

2) Catalogue: Product (seller_id, title, description, category, brand, condition new, status draft/pending_review/active/suspended, hazard and ingredient notes) and ProductVariant (sku, option names such as shade or size, price_minor, currency, stock_quantity, weight_grams, barcode). Images reuse the portfolio pipeline with sized variants. Stock decrements on payment, with a reservation while checkout is in flight, and a concurrency test proving oversell is impossible.

3) Compliance fields, required before a listing goes active (report what each market needs and make it configurable): a cosmetics notification reference or responsible-person details for the UK, a NAFDAC registration number for Nigeria, an ingredient list, and shelf-life or batch where relevant. A prohibited-categories policy enforced in code, with a configurable list: prescription medicines, injectables, unapproved skin-lightening agents (research which are restricted per market and cite sources; do not guess), hazardous aerosols where shipping rules forbid them, counterfeits. Every listing is manually approved before going live, with an admin queue and an audit trail.

4) Orders: Order (buyer, seller, status pending_payment/paid/preparing/shipped/delivered/cancelled/refunded/disputed), OrderItem snapshots (title, variant, unit price, quantity), shipping address snapshot, shipping method and fee, totals, and the platform commission snapshot. Commission is a percentage in config, defaulting to 12%, per category, computed server-side exactly like booking fees. Sellers handle their own shipping: they mark shipped with a carrier and tracking number. Buyers confirm delivery, or it auto-confirms after a configurable window.

5) Payments: reuse the Slice 7 interfaces. Stripe direct charges settle to the seller with our application fee; disputes fall on the seller. On Flutterwave we are merchant of record, so hold the payout until delivery is confirmed or the window passes, and record chargebacks against the seller, subject to counsel confirming we may hold funds. Credit from the ledger can be spent on products, capped at our commission, exactly as for bookings.

6) Returns and refunds: a returns request flow with reasons, a configurable window per market, and an explicit hygiene-seal exemption (opened cosmetics usually cannot be returned; confirm the rule per market and surface the policy before purchase). Partial refunds, restocking, and commission reversal on refund.

7) Product reviews, only from a delivered order; one per item; photos with consent; reuse the existing moderation and reporting.

8) Discovery: GET /v1/products with category, price range, brand, seller, in-stock and sort; products on a provider's page; recommendation hooks ("used in this look") linking a portfolio post to products, so a provider earns a share of our commission, configurable, default a third, paid through the credit ledger.

9) Tests: oversell under concurrency; a listing without compliance fields cannot go active; prohibited categories rejected; commission and credit arithmetic; refund reverses commission; returns window and hygiene exemption; one order per seller when a basket spans sellers; cross-border purchase rejected in v1.

```

## Slice 10: Widget and Live Activity support

```
Slice 10: widget and lock-screen support. Requires the rebook and cadence work. Stop after each step.

1) GET /v1/me/summary, a single small cached payload for widgets: next booking (provider first name, service, start time, visit type), whether rebooking is due with the provider and service to repeat, unread message count, and for providers today's booking count and next client first name. Cache per user, invalidate on booking changes, and keep it under a few kilobytes. No addresses, no surnames, no prices.

2) Push: a silent push on booking changes so widgets refresh promptly instead of polling. Respect quiet hours for visible pushes; silent refreshes are exempt.

3) Live Activity and ongoing notification support for trips: a token registry per trip, plus a server push on each ETA change (rate-limited, say at most one a minute) carrying only first name, ETA and state. Ends when the trip ends. Reuse the Slice 6 trip states.

4) Tests: the summary never leaks an address, surname or price; cache invalidation on booking create, cancel, reschedule and complete; Live Activity pushes stop when a trip ends.

```
