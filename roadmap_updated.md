# Product Roadmap — Beauty/Grooming Discovery & Booking App

## Positioning (context for any AI assistant working in this repo)
A discovery-first booking marketplace for hair, nail, makeup, and beauty providers — both individuals (including casual/side-hustle providers who currently get booked through Instagram DMs) and small businesses. The core differentiator is AR try-on tied to a specific provider's real portfolio work, not a generic filter, and a lower-friction alternative to the subscription-first tools (Fresha, Booksy, GlossGenius) and the curated at-home staffing apps (Ruuby, Blow Ltd). Launch market: London. Customers visiting a provider (shop or the provider's own home/personal space) is in scope from V1 — that's already how this market operates informally via Instagram, so formalizing it with ID verification is a safety improvement, not a new risk. What's staged later is specifically a *provider* traveling to a *customer* (true on-demand dispatch — V2), plus business-tooling features (POS, inventory, staff payroll) which stay out of scope until explicitly promoted into a later version — that's a common feature-creep trap for this project.

---

## V1 — Prove discovery + booking works, one city, one category
**Goal:** Get real providers and real customers using the core loop (browse portfolio → AR preview → book → review) in London, hair only. Covers both directions of "customer visits provider" — a shop/salon address or a provider's own home/personal space — since that's already how this market operates informally via Instagram today; formalizing it with ID verification and reviews is strictly safer than the current all-DM status quo, not riskier, so it doesn't need to be gated behind a trust-building phase. What's excluded is specifically the *provider* traveling to the *customer* — see V2 for why that one's different.

- Provider signup: individual or business, profile (name, bio, location/area, services + rough pricing), address type flagged as shop or home so customers know what they're walking into
- Categories: hair, nails, and makeup (combined from the start rather than staged — hair-only was originally meant to limit build time, not a safety gate, so combine if the AR/catalog work is manageable at your pace)
- Manual photo/video portfolio upload; Instagram "Connect & Import" for providers with a Business/Creator IG account (requires your own Meta developer app + passing App Review — treat as its own workstream with its own timeline, not a blocker for shipping the rest of V1)
- Simple availability ("usual working hours"), not a full staff calendar; provider-side calendar sync (Google Calendar/iCal) to reduce double-booking
- Manual accept/decline booking requests by default; instant-book as an opt-in once a given provider has enough completed bookings/reviews to trust auto-confirmation — this is a per-provider data threshold, not a version gate
- Customer browse/search by location + style (this is the core discovery surface — invest here)
- AR try-on: apply a specific portfolio photo's style to the customer's own photo/camera, book that provider directly from the result
- Basic in-app messaging for booking back-and-forth; push notifications for confirmations, reminders, messages
- In-app payments and deposits
- Post-appointment reviews/ratings
- ID verification at signup (manual review at this scale — this is what makes "go to a stranger's home/shop" safer than the current Instagram-DM norm, and it's also the trust data V2 depends on)
- Manual reporting/flagging + ability for you to deactivate a profile
- Explicitly out of scope: provider traveling to the customer (on-demand dispatch/true house-calls), multi-staff/business tooling

**Success criteria before moving to V2:** a real cohort of providers with completed bookings, reviews, and verified IDs — this is the trust data that makes it responsible to start sending providers to customers' homes, which is a materially different liability position than customers choosing to visit a provider.

---

## V2 — Provider-to-customer visits (true house-calls / on-demand)
**Goal:** Extend into the one direction that genuinely needed V1's trust data first: dispatching a provider to a customer's home. Unlike customer-visits-provider, this is your platform vouching for a stranger entering someone's private space — a new liability position, not a formalization of an existing norm.

- Provider travels to customer's location — gated to providers with a minimum review count/rating and verified-ID history from V1, not open to brand-new signups
- Liability/safety layer specific to this direction: address confirmation, optional insurance guidance or partnership, possibly live location sharing during the appointment
- On-demand/instant dispatch matching (find an available nearby provider now), as opposed to V1's pre-booked model

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
- Shoppable product tagging: providers tag the exact product(s) used to achieve a portfolio look; customer can tap through to buy via an affiliate network (Rakuten Advertising/Awin/ShareASale/Skimlinks rather than integrating individual retailers one by one). Secondary revenue/engagement layer, not a primary revenue driver — affiliate commissions run roughly 1-10% depending on category and retailer, and cookie-based attribution windows are short. Optional companion: let customers tag product preferences (cruelty-free, sulfate-free, allergy-safe) as a filter, separate from the commerce feature.

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

## Monetization strategy (grounded in competitor models)
The core model should be commission-based on new-client bookings, not subscription — mirroring Fresha's approach (one-time ~20% commission on a new client the platform brings a provider, nothing on repeat bookings) rather than Booksy's flat monthly-subscription model. This fits the target audience directly: casual/side-hustle providers doing a few bookings a week won't justify a $15-20/month software subscription the way an established salon will, so a pay-only-when-you-earn model removes the adoption barrier that subscription-first tools create for exactly the segment this app is going after.

Layer in additional revenue only as volume justifies it, roughly in this order:
1. **New-client booking commission** (V1 core) — the primary driver, scales with usage, zero cost to inactive/casual providers.
2. **Payment processing margin** (V1, since in-app payments are now built from the start) — a small cut on top of processor fees, standard practice (Fresha does this too).
3. **Affiliate product commissions** (V3) — the shoppable-product feature above; real but modest, treat as incremental, not foundational.
4. **Optional subscription/premium tier for business accounts** (V3/V4) — once multi-staff business accounts exist and have real booking volume, a Booksy-style subscription with perks (analytics, featured placement, lower commission rate) becomes viable for that segment specifically, without forcing it onto the casual individual providers who are the core differentiator.
5. **Featured/promoted placement in discovery search** (V3/V4, once traffic is real) — providers pay to rank higher; only makes sense once there's enough search volume that placement has real value, so don't build this before V3.
6. **Creator/affiliate referral program** (V3) — two distinct tracks, not one feature: (a) many providers are already content creators on Instagram/TikTok, so richer provider profiles (video content, not just static portfolio photos) largely serve this for free — no separate infrastructure needed beyond what V1/V2 already builds; (b) third-party creators who don't provide services themselves get a referral link/code (reusing the affiliate rails built for shoppable products) to drive bookings or new customer signups for a commission — a growth/acquisition channel as much as a revenue one. Requires UK ASA disclosure-compliance messaging for sponsored/affiliate content before launch. Sequence after V1/V2 prove the core loop — a creator program amplifies an existing working funnel, it doesn't fix a broken one.

---

## Notes for whoever (human or AI) is implementing this
- Backend: Python + FastAPI
- Frontend/mobile: website + Android + iOS planned; builder is a backend developer learning frontend/mobile through this project — prefer incremental, explained changes over large unexplained scaffolding
- Solo builder, ~5–10 hrs/week, split with a second unrelated project — keep each version's scope genuinely minimal; resist adding "just one more feature" to V1
- Target: working prototype/MVP by July 2027, live by December 2027 (open to launching earlier)
