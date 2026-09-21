# Product Roadmap — Beauty/Grooming Discovery & Booking App

## Positioning (context for any AI assistant working in this repo)
A discovery-first booking marketplace for hair, nail, makeup, and beauty providers — both individuals (including casual/side-hustle providers who currently get booked through Instagram DMs) and small businesses. The core differentiator is AR try-on tied to a specific provider's real portfolio work, not a generic filter, and a lower-friction alternative to the subscription-first tools (Fresha, Booksy, GlossGenius) and the curated at-home staffing apps (Ruuby, Blow Ltd). Launch market: London, hair category only (barbers + hairdressers). Do not build house-calls/on-demand, multi-category support, or business-tooling features (POS, inventory, staff payroll) until explicitly promoted into a later version below — those are common feature-creep traps for this project.

---

## V1 — Prove discovery + booking works, one city, one category
**Goal:** Get real providers and real customers using the core loop (browse portfolio → AR preview → book → review) in London, hair only.

- Provider signup: individual or business, profile (name, bio, location/area, services + rough pricing)
- Manual photo/video portfolio upload (no Instagram auto-import yet — see V2)
- Simple availability ("usual working hours"), not a full staff calendar
- Manual accept/decline booking requests (no instant-book yet)
- Customer browse/search by location + style (this is the core discovery surface — invest here)
- AR try-on: apply a specific portfolio photo's style to the customer's own photo/camera, book that provider directly from the result
- Basic in-app messaging for booking back-and-forth
- Post-appointment reviews/ratings
- ID verification at signup (manual review at this scale — seed of the trust system for V2+)
- Manual reporting/flagging + ability for you to deactivate a profile
- Explicitly out of scope: house-calls, on-demand dispatch, in-app payments beyond an optional deposit, multi-staff/business tooling, categories beyond hair

**Success criteria before moving to V2:** a real cohort of providers with completed bookings and repeat customers, and reviews accumulating — you need this trust data before opening up house-calls.

---

## V2 — Add categories, home visits, and easier provider onboarding
**Goal:** Use the trust signal from V1 (reviews, completed bookings, verified IDs) to safely expand into the higher-risk, higher-differentiation features.

- Expand categories: nails, makeup (in addition to hair)
- House-calls / at-home appointments — gated to providers with a minimum review count/rating from V1, not open to brand-new signups
- Basic liability/safety layer for house-calls: verified ID requirement, address confirmation, optional insurance guidance or partnership
- Instagram "Connect & Import" for providers with a Business/Creator IG account (requires your own Meta developer app + passing App Review — treat as its own workstream, not a blocker for anything else in V2)
- In-app payments and deposits (moving off manual/external payment)
- Instant-book for providers who opt in (once you have enough reliability data to trust auto-confirmation)
- Provider-side calendar sync (Google Calendar / iCal) to reduce double-booking
- Push notifications for booking confirmations, reminders, messages

---

## V3 — Geographic expansion + business-side depth
**Goal:** Scale the model that worked in London to more UK cities, and start giving businesses (not just individuals) reasons to prefer you over Fresha/Booksy.

- Expand to other UK cities (per original target market: London + other UK cities)
- Multi-staff/business accounts: a business can list multiple providers under one profile, each with their own portfolio and availability
- Provider-facing analytics (views, booking conversion, repeat-customer rate) — a lightweight version of what Fresha/Booksy offer business owners
- Referral/growth loops (customer refers a friend, provider refers another provider)
- Improved AR: video try-on or multi-angle preview, not just a single static photo
- Waitlist/instant-availability matching ("notify me if a slot opens today")
- Basic loyalty features (repeat-customer perks, saved favorite providers)

---

## V4 — US expansion + platform maturity
**Goal:** Enter the original long-term target markets (New York, Los Angeles) once the UK model is proven, and harden the platform for scale.

- Expand to New York and Los Angeles
- Full background-check/verification pipeline (replacing the manual V1 process) for house-call providers
- Dynamic/surge-aware pricing exploration for on-demand bookings (optional — evaluate against provider feedback first)
- Deeper business tooling only if demand clearly emerges from V3 business accounts (payroll, inventory) — treat this as a "build only if requested" bucket, not a roadmap default, since matching Fresha/Booksy feature-for-feature here is not the strategy
- Internationalization/localization groundwork if expansion beyond UK/US is considered

---

## Explicit non-goals (revisit only if a version above is fully shipped and validated)
- Becoming a general business-management SaaS (Fresha/Booksy's core business) — that's not the wedge this product is built on
- Competing on payroll/inventory/multi-location enterprise tooling before the discovery/booking core has real traction
- Building a curated/staffed roster (Ruuby/Blow Ltd model) — this product is an open marketplace, not a staffing agency

---

## Notes for whoever (human or AI) is implementing this
- Backend: Python + FastAPI
- Frontend/mobile: website + Android + iOS planned; builder is a backend developer learning frontend/mobile through this project — prefer incremental, explained changes over large unexplained scaffolding
- Solo builder, ~5–10 hrs/week, split with a second unrelated project — keep each version's scope genuinely minimal; resist adding "just one more feature" to V1
- Target: working prototype/MVP by July 2027, live by December 2027 (open to launching earlier)
