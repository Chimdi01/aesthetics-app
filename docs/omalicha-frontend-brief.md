# Omalicha front-end brief

For the Claude Code instance building the client app. Save this as `docs/frontend-brief.md` in the client repo and put Sections 0 and 1 into that repo's `CLAUDE.md`. Brand assets are in `omalicha-brand/` (copy to `assets/brand/`).

---

## 0. Working agreement

- **Read first:** the backend repo's `CLAUDE.md` and `CHANGELOG.md`, and fetch the running API's `/openapi.json`. Generate a typed client from it. Do not invent endpoints or fields. If this brief assumes something the API lacks, add it to the gaps list (Section 14), stub it behind a clearly named flag, and carry on.
- **The owner reviews and commits every change by hand.** Work in small steps: one concern per change, a two-line summary of what changed and why, then stop. Never commit. Propose any new dependency before adding it.
- **Build in the order in Section 13.** Do not start a phase until the previous one is accepted.
- Explain non-obvious choices briefly. The owner is a backend developer who wants to understand the front end, not just receive it.
- If a request conflicts with a hard rule in Section 1, say so before building.

---

## 1. What this is, and the hard rules

**Product.** Omalicha is a marketplace for beauty and grooming services: hair, barbering, nails, makeup, skincare. Customers browse real portfolios, see the full price, and book in under a minute. Providers get a free booking page and portfolio. **House calls are in v1**: a customer can go to the provider, or the provider can come to the customer, with opt-in live trip sharing. Later: product sales, AR try-on of a *specific provider's* real work. The differentiator is real, bookable portfolios plus expertise in hair texture and technique.

**Markets.** Wave 1: UK and Nigeria (GBP, NGN; English). Wave 2: France, Côte d'Ivoire, Senegal (EUR, XOF; French). A market is configuration, not a code branch.

**Hard rules. These are not style preferences.**

1. **No race, ethnicity or gender fields, filters or proxies, anywhere.** Discovery is by service, hair texture and technique specialty, rating, price, distance and availability. This is legal exposure, not taste.
2. **Nothing is gendered:** colour, copy, imagery, icons, service naming, onboarding. Never ask for gender or pronouns. Service templates are by length and technique ("Short cut", "Long cut", "Fade"), never "Men's" or "Women's".
3. **Honest persuasion only.** No fake scarcity or urgency, no drip pricing, no pre-ticked extras, no guilt-trip copy, no invented discounts. Every claim ("Most booked", "Typical price", "2 slots left", "Next available") must come from real data or be hidden. UK and EU rules target these practices (UK Digital Markets, Competition and Consumers Act 2024). **Verify** specifics with counsel.
4. **Money** is an integer in minor units plus an ISO 4217 currency code. Never floats. XOF has zero decimals.
5. **Time** arrives as UTC. Display in the provider's timezone, and add "your time" when it differs.
6. **Low bandwidth first.** Assume a mid-range Android phone on a slow connection.
7. **Privacy.** Approximate location only until a booking is confirmed. Consent gates before analytics or marketing. Account deletion works in-app.
8. **Every string goes through i18n keys.** English now; French drafts flagged for native-speaker review. Never ship machine translation.
9. **Accessibility:** WCAG 2.2 AA.
10. **Location sharing is opt-in, time-boxed, visible and revocable** (Section 6A). It exists for ETA and safety, never for data collection.

---

## 2. Stack and setup

- **Expo** (current stable SDK), **TypeScript strict**, **Expo Router**, React Native Web. One codebase for iOS, Android and web. SEO-friendly public provider pages will be rebuilt later in Next.js; do not optimise for SEO now.
- **Data:** TanStack Query + a client generated from OpenAPI (`openapi-typescript` + `openapi-fetch`). Forms: React Hook Form + Zod.
- **Local state:** Zustand, tiny. Draft booking, theme, flags only.
- **Lists:** FlashList. **Images:** `expo-image` with ThumbHash placeholders. **Motion:** Reanimated + Gesture Handler. **Vector:** `react-native-svg`.
- **Fonts:** Fraunces and Work Sans via `@expo-google-fonts`. Hold the splash until loaded.
- **i18n:** i18next + expo-localization. Dates and money via `Intl`.
- **Secrets:** tokens in `expo-secure-store`. Never AsyncStorage or localStorage.
- **Maps and location:** `react-native-maps` with `provider={PROVIDER_GOOGLE}` on iOS and Android (keys through its config plugin: `androidGoogleMapsApiKey`, `iosGoogleMapsApiKey`), `@vis.gl/react-google-maps` on web, both behind one `<MapView>` wrapper (`.native.tsx` and `.web.tsx`). `expo-location` and `expo-task-manager` for location. These need a **development build**, not Expo Go.
- **Icons:** one line-icon set (Phosphor Regular or Lucide), 24px, about 1.75px stroke, rounded caps. Pick one and stay with it.
- **No UI kit** (no Paper, NativeBase, Tamagui). Build primitives from the tokens in Section 3. This is how the app avoids a templated look.
- **Tests:** Jest + React Native Testing Library; Maestro for the booking flow; the a11y ESLint plugin; CI runs typecheck, lint and tests.

---

## 3. Design language

### 3.1 Philosophy

Flat, matte, material. Every colour is named after a thing: espresso, sienna clay, emerald, gold, ivory cotton. **Never** use gradients, glassmorphism or blur, glow or neon, decorative blobs, or purple. Surfaces separate by tone and a 1px hairline, not shadows. **Photos are the colour**: the chrome stays quiet so portfolio work does the talking. One gesture, the open stroke from the logo, recurs in the logo, loading, progress and celebration.

**Three themes, one setting.** Settings > Appearance: **Match system**, **Dark** (default), **Light**, **Neutral**.

- **Dark** is the signature: espresso ground.
- **Light** is ivory.
- **Neutral** is a third, mid-tone "stone" theme: softer than Light, lighter than Dark, for people who find either extreme tiring.
- **Match system** maps the OS setting to Dark or Light, never Neutral.

Architecture rules: components read **semantic tokens** from a `ThemeProvider`; there are no hex literals outside `tokens.ts` (add a lint rule). Every theme exposes the same keys. Persist the choice and hydrate it before first render to avoid a wrong-theme flash; hold the splash until hydrated. The status bar, navigation bar, keyboard appearance and **map style** follow the theme. The logo, app icon and splash stay dark. Photos and the solid scrim bar look identical in every theme.

### 3.2 Logo (the agreed mark)

The **Calm Stroke**: an open ring of about 318°, spiralling very slightly inward, with a stroke that tapers gently from 21 to 15 units, round caps, in sienna `#AD5E36`. The two ends stay about 12 units apart in the mark's own grid: close, but never touching, so it reads as a gesture rather than a closed "O". Twelve short segments build the taper; the data lives in `mark-segments.ts`.

| File | Use |
| --- | --- |
| `omalicha-mark-sienna.svg` | Default mark on espresso or ivory grounds |
| `omalicha-mark-ivory.svg` | On sienna or photographic scrims |
| `omalicha-app-icon.svg` | 1024px app icon: espresso `#221C19` ground, sienna mark at about 57% of the tile |
| `mark-segments.ts` | The mark as data (path segments, widths, viewBox) for the component and the splash animation; the SVGs are generated from the same data |

**Wordmark.** "Omalicha" in Fraunces 600. Lockup: mark left, wordmark right, gap = 0.4 × mark width, wordmark cap height = 0.55 × mark height. The mark never appears alone with a different colour.

**Clear space** = half the mark's height on all sides. **Minimum size:** mark 28px; lockup 96px wide. Below about 24px (browser-tab favicons) the small opening can fill in: check the 32px favicon by eye and accept the filled-in look at 16px.

**Never:** gradient, outline, glow, shadow, rotation, stretching, recolouring outside sienna / ivory / espresso, or placing on a photo without a solid scrim bar.

**Component.** Use this, not an `<Image>`:

```tsx
import Svg, { Path } from 'react-native-svg';
import { MARK_ASPECT, MARK_SEGMENTS, MARK_VIEWBOX } from './mark-segments';

export function OmalichaMark({ size = 48, color = '#AD5E36' }: { size?: number; color?: string }) {
  return (
    <Svg width={size} height={size * MARK_ASPECT} viewBox={MARK_VIEWBOX} accessibilityLabel="Omalicha">
      {MARK_SEGMENTS.map((s) => (
        <Path key={s.d} d={s.d} stroke={color} strokeWidth={s.w} strokeLinecap="round" fill="none" />
      ))}
    </Svg>
  );
}
```

Copy `mark-segments.ts` next to the component (for example `src/components/brand/`). Never hand-edit its path data; if the mark changes, regenerate it with the SVGs.

**Splash.** Espresso ground. The twelve segments draw in order, thick to thin, as one continuous stroke over 900ms total with `cubic-bezier(0.2, 0, 0, 1)`, then the wordmark fades in over 200ms. Measure segment lengths with `svg-path-properties` for the dash animation. Reduced motion: show the static mark. If a parent brand name is configured (`config.parentBrand`), show a small "FROM {name}" line at the bottom; the name is not final, so default it to `null`.

**App icon.** Platforms apply their own corner masks; supply the square. Keep the mark inside the centre 60% for Android adaptive icons.

### 3.3 Colour tokens

Contrast ratios were computed from the hex values. Re-check them with a tool.

**Dark (default)**

| Token | Hex | Use | Notes |
| --- | --- | --- | --- |
| `ground` | `#221C19` | App background | |
| `surface` | `#2B2320` | Cards, rows | |
| `surfaceHigh` | `#362D29` | Inputs, sheets, selected rows | |
| `hairline` | `#4A3F39` | 1px borders and dividers | Decorative |
| `text` | `#FBF4EC` | Primary text | 14:1 on surface |
| `textMuted` | `#CFC3B6` | Secondary text | 8.9:1 |
| `textSubtle` | `#A39688` | Captions, placeholders | 5.3:1 |
| `sienna` | `#AD5E36` | Logo, progress fills, large graphics | **3.2:1 on surface: never small text** |
| `siennaStrong` | `#9E5530` | Button fills carrying ivory text | Ivory on it: 5.1:1 |
| `emerald` | `#2F6F5E` | Success and availability fills | Ivory on it: 5.4:1 |
| `emeraldTint` | `#5FAE97` | Success text and icons on dark | 5.9:1 |
| `gold` | `#C9A24B` | Ratings, rewards, progress rings | 6.4:1 |
| `danger` | `#DB6F63` | Error text and icons | 4.7:1 |

`siennaStrong`, `emeraldTint` and `danger` are derived for accessibility and state; they are not brand colours. Never put text on `emerald` or `sienna` fills in anything but ivory.

**Light (ivory)**

| Token | Hex | Notes |
| --- | --- | --- |
| `ground` | `#FBF4EC` | |
| `surface` | `#FFFFFF` | |
| `surfaceHigh` | `#F3EADF` | Derived |
| `hairline` | `#E4D9CB` | |
| `text` | `#2B2320` | |
| `textMuted` | `#6B6058` | 5.6:1 on ivory |
| `siennaText` | `#9E5530` | Small sienna text: 5.1:1 |
| `emeraldText` | `#2F6F5E` | 5.4:1 |
| `gold` | `#C9A24B` | **Decorative only on light (2.2:1)**: pair with espresso text |
| `goldDeep` | `#9A7A2B` | Stars, rings and other graphics on light: 3.7:1 on ivory |
| `danger` | `#B3423A` | 5.1:1 |

**Neutral (stone)**

A mid-tone theme: warm stone ground, espresso text.

| Token | Hex | Notes |
| --- | --- | --- |
| `ground` | `#D9CFC3` | Espresso text on it: 10:1 |
| `surface` | `#E8E0D6` | Cards and rows |
| `surfaceHigh` | `#F1EAE1` | Inputs and sheets |
| `hairline` | `#BFB3A5` | Decorative |
| `text` | `#2B2320` | |
| `textMuted` | `#5A4F47` | 5.2:1 on ground, 6.1:1 on surface; also used for captions |
| `siennaText` | `#8A4726` | Small sienna text: 4.5:1 on ground, 5.3:1 on surface |
| `emeraldText` | `#25584A` | 5.3:1 on ground |
| `goldDeep` | `#9A7A2B` | Stars and rings on cards: 3.1:1 |
| `danger` | `#9C3029` | 4.8:1 on ground |

Button fills (`siennaStrong`, `emerald`) with ivory text are identical in all three themes. The sienna logo reads at 3.1:1 on the stone ground and 3.6:1 on cards: fine for a graphic, but keep it at least 24px.

**Meaning is fixed.** Sienna = brand and the one primary action. Emerald = confirmed, available, verified. Gold = progress, rating, reward. Danger = error and destructive only. Never use colour alone to carry meaning; pair it with an icon or label.

### 3.4 Typography

| Role | Font | Size / line | Weight |
| --- | --- | --- | --- |
| Display | Fraunces | 34 / 40 | 600 |
| H1 | Fraunces | 28 / 34 | 600 |
| H2 | Fraunces | 22 / 28 | 600 |
| H3 | Work Sans | 18 / 24 | 600 |
| Body | Work Sans | 16 / 24 | 400 |
| Body small | Work Sans | 14 / 20 | 400 |
| Caption | Work Sans | 12 / 16 | 400 (minimum size) |
| Button | Work Sans | 16 / 20 | 600 |

Prices use Work Sans with `tabular-nums`. Support dynamic type to 130% without clipping. Design every label for French, which runs about 30% longer. Fraunces is for voice moments (screen titles, confirmation, big numbers); Work Sans carries the interface.

### 3.5 Space, shape, depth, icons, motion

- **Spacing** on a 4pt grid: 4, 8, 12, 16, 20, 24, 32, 40, 56. Screen gutters 20.
- **Radii:** 10 small (inputs inside cards), 14 controls and buttons, 16 cards, 24 sheet tops, 999 chips and avatars.
- **Depth:** none. No shadows. Sheets use a 60% solid espresso scrim, no blur.
- **Touch targets:** 44px minimum; primary buttons 52px.
- **Motion:** durations 120 / 200 / 320ms; easing `cubic-bezier(0.2, 0, 0, 1)`; sheets use a spring (damping 20, stiffness 220). Press feedback: scale 0.98 and a tone shift in 80ms. Lists stagger at most six items at 30ms. Loading skeletons pulse opacity 0.5 to 1 over 1.2s; **no shimmer gradients**. Totals animate as a number transition. Honour reduced motion everywhere.
- **Haptics:** light on selection, success on booking confirmed. Never on scroll.
- **Signature motion:** the stroke draws itself (splash, success check in emerald, progress completion). Reuse `MARK_SEGMENTS` or a single path.

### 3.6 Imagery

- Portfolio photos lead everywhere: 4:5 on cards, 1:1 in grids.
- **Never put text directly on a photo.** Use a solid espresso bar at 70% opacity beneath the text. No gradient scrims.
- Empty states use single-line drawings built from the stroke motif. No mascots, no illustrated people, no stock imagery in the interface.
- Pre-launch placeholders: `surfaceHigh` tiles with the sienna mark at 30% size.
- Prompt providers for alt text on every upload, with a suggested caption.

### 3.7 Voice and copy

Plain, warm, confident, short sentences. Use "you". Avoid "ladies", "gents", "she/he", "glow up", exclamation marks (except one on the confirmation), and any copy that assumes who the customer is.

| Moment | Copy |
| --- | --- |
| Welcome | Book people who are great at what you want. |
| Search placeholder | Search a service, style or name |
| Location prompt (before the OS dialog) | Share your location to see who is nearby. We show a neighbourhood, never an exact spot. |
| Booking confirmed | You're booked. |
| Cancellation line | Free to cancel until Wed 10:30. After that, you pay 50%. |
| Empty bookings | Nothing booked yet. Find someone whose work you like. |
| Error | That didn't go through. Your details are saved, so try again. |

### 3.8 "Does not look generated" checklist

No gradients, glass, glow or purple. No emoji as icons. No centred hero with three feature cards. No default system component look. No Inter or Roboto. No rounded-card-plus-shadow soup. Real content in every mock. Gesture only where it carries meaning (the stroke, progress, celebration). If a screen could belong to any app, it isn't finished.

---

## 4. Behavioural design: what to apply, where, and the guardrail

These make the app easier to use and help retention and revenue. Every one has a guardrail, because dishonest versions are both disliked and increasingly illegal.

| Principle | Where it appears | Guardrail |
| --- | --- | --- |
| **Smart defaults** | Language, market and currency from device. City from location, falling back to locale. Booking pre-selects the most-booked service, the soonest slot or "your usual", and the last-used payment. Reminders on. "Save my usual" on. Filters and sort remembered. | Marketing consent is **off** by default. Add-ons are never pre-ticked. |
| **Goal gradient and endowed progress** | Booking stepper starts one-third filled. Provider profile ring starts at 20% for what they already did. Loyalty meter starts with one welcome stamp. | Show the next step only. Never show a bar that can't be completed. |
| **Reciprocity** | Give before asking: browse without an account, see full prices and availability, explain what a taste profile unlocks, welcome credit, free booking page for providers, referral rewards both ways. | Say plainly what each ask is used for. |
| **Endowment effect** | Favourites, lookbook (saved looks and your own before/after photos), per-provider notes, saved addresses, wallet credit shown as "yours". Providers: the 60-day Pro trial uses everything, and their page, link and client list are theirs. | Export and delete are always available. |
| **Loss aversion** | Plain cancellation terms. Credit shows its **real** expiry date. Trial end shows what they'd lose (reminders, analytics). | A slot-hold timer only if the server really holds the slot. No countdowns that reset. |
| **Contrast effect** | An ivory summary card on the dark ground pulls the eye to the booking total. Real price anchors ("Typical in London: £45 to £70"). Good-better-best packages with the middle one recommended. Free-versus-Pro table with Pro highlighted. | Anchors only from real local data with a minimum sample. |
| **Social proof** | Rating, review count, completed bookings, "42% of clients rebook" when computed. | Real numbers, from verified bookings only. |
| **Honest scarcity** | "2 slots left today" computed from availability. | Hidden when more than five slots remain. |
| **Peak-end rule** | The confirmation screen and the post-service moment are the designed highlights. | Keep both calm and fast. |
| **Zeigarnik and commitment** | "Continue booking" card for a draft. Small yeses first: save, then book. Guest sign-up appears at the last step, with selections kept. | Drafts expire after 24 hours. |
| **Hick's law** | At most five options per decision. Advanced filters live in a sheet. Policies collapse. | |
| **Habit loop** | Cue: a rebook nudge when the usual gap has passed (defaults: barber 4 weeks, nails 3, colour 8, braids 6; provider-editable). Routine: one-tap rebook. Reward: the confirmation moment and progress. | At most one nudge a week, quiet hours 21:00 to 08:00 local, one-tap opt-out. No streak shaming. |
| **Fewer taps, thumb zone** | Primary actions in the bottom 40% of the screen. Sticky booking bar. Rebook in one tap. | |
| **Optimistic UI** | Saving a favourite, sending a message, toggling a setting update instantly and roll back with a toast on failure. | |
| **Trust signals** | Verified badge explains itself on tap. Real cancellation and refund summary. Report and block everywhere. | |
| **Visibility of status** | Live ETA, clear trip states, "Updated just now", reminders before the visit. Not knowing where someone is drives cancellations and no-shows. | Share location only on opt-in. Never present stale data as live. |

**Revenue-aligned flows** (profit without tricks):

- **Keep bookings in the app.** Rebooking is the fastest path; notes, lookbook, loyalty, reviews and tips all work only for in-app bookings. Messaging stays in-app. Show "Keep payments in Omalicha to stay covered" **only** when refund and dispute cover is real.
- **Add-ons and packages** at checkout raise order value. Optional, never pre-ticked, with a running total.
- **Book your next visit** on the confirmation screen (one tap, from the usual cadence).
- **Welcome credit and referrals** follow the incentives rules: funded from Omalicha's fee, paid after a completed booking, capped per person and month, shown as a wallet.

---

## 5. Information architecture

**Customer tabs (bottom, five):** Discover · Saved · Bookings · Messages · You.
**Provider tabs:** Today · Calendar · Clients · Messages · Business.
**One account, additive roles.** Everyone can act as a customer; a user who has a provider profile can also act as a provider. The current-user response carries `capabilities` (for example `["customer"]` or `["customer", "provider"]`), and the client picks the view from that, never from the signup `role` field. A **Switch view** control appears in You only when both capabilities exist; the current view is client-side state, because the API's customer and provider endpoints are already separate. Customers see **Become a provider** in You, which starts the provider onboarding flow (Section 7). Admin is a separate account type and never appears in the app: if the current-user response has an empty `capabilities` (an admin account), show a plain "This account type can't use the app" screen with Sign out.

**Web:** top navigation instead of tabs. Breakpoints: under 600 mobile; 600 to 1023 tablet; 1024 and up desktop with two-pane layouts (search list plus map; provider page with a sticky booking card on the right) and a content max-width of 1200. Keyboard focus rings are 2px ivory. Hover is a subtle tone shift. A cookie banner with equal-weight Accept and Reject.

**Deep links:** `omalicha://p/{handle}` and a web equivalent `/{handle}` (domain in config). The provider's booking link is their Instagram-bio link.

---

## 6. Customer screens

### 6.1 Splash and welcome
- Splash as in 3.2.
- **Welcome (one screen, no tour):** ground, mark 40px top-left. Display title "Book people who are great at what you want." Subtitle "Browse real work, see the full price, book in under a minute." Primary button "Browse near me" (52px, bottom). Secondary text button "Sign in".
- Before the OS location dialog, show a small explainer card (copy in 3.7). If declined, fall back to a city picker prefilled from locale. **No account wall:** guests browse everything. Sign-up never asks whether you are a customer or a provider; everyone starts as a customer and can become a provider later from You.

### 6.2 Taste profile (optional, after the first favourite or first booking)
- Three skippable cards, one per screen, progress dots top. Texture: Straight, Wavy, Curly, Coily, Not sure. Interests (multi-select): Cuts, Colour, Braids and locs, Nails, Makeup, Skin. Budget comfort with local currency amounts, the market median pre-selected.
- Header line on every card: "We use this only to show people who specialise in what you want. Change it anytime." **Never ask gender or pronouns.**

### 6.3 Discover (home)
Top to bottom, 20px gutters:
1. **Header row:** mark 28px, location chip (pin icon, "London", chevron) filling the middle, bell icon right with a dot for unread.
2. **Search field**, 52px, `surfaceHigh`, radius 14, magnifier icon. Opens the search screen with the keyboard up.
3. **Category chips**, horizontal scroll, 40px: Hair, Barber, Nails, Makeup, Skin, Braids and locs. Selected chip = ivory fill, espresso text (contrast against the dark chips).
4. **Continue booking card** (if a draft exists): ivory card, avatar, "Pick up where you left off", service and time, Resume button.
5. **Book again** row (if history): cards with avatar, last service, next slot ("Thu 10:30"), button "Book again". If past the usual cadence, add "Usually every 4 weeks. It's been 5."
6. **Available today near you:** horizontal provider cards, each with a real next-slot chip (emerald fill, ivory text).
7. **Specialists for your hair** (only with a taste profile): ranked by texture and technique match.
8. **New on Omalicha:** new providers, each labelled "New" (boosted placement must be disclosed).
9. **Welcome credit card** if unused: gold outline on `surface`, "£5 is waiting in your wallet. Use it on your first booking."
- Show at most the first four sections on load; lazy-load the rest. Pull to refresh. Skeleton rows while loading.

### 6.4 Search results
- Top bar: query field, filter button showing an active-count badge. Segmented control List / Map. Result count: "42 people near Shoreditch".
- **Filter sheet:** service type; **hair texture and technique** chips (from `GET /v1/specialties`, showing only the chips that belong to the chosen category; labels are localised on the client by slug); price range slider in local currency with a small histogram of result prices behind it; rating 4+; availability (Today, This week, pick a date); sort (Best match default, Nearest, Highest rated, Lowest price). Sticky "Show 42 results" button.
- Defaults: Best match, 5km radius in dense cities and 10km elsewhere, last filters remembered.
- **Provider card (list):** 4:5 portfolio carousel (up to five, swipe, dots), top-left Verified badge, top-right heart (animates on save). Below: name (H3), specialty line ("Fades · Textured hair · Locs"), rating with gold star and count, distance, "From £25" with the real price anchor beneath when data exists, and a next-slot chip. Tapping prefetches the profile and opens it.
- Always the **all-in price**. House-call travel (when it exists) shows as "+ travel £X" before any commitment.
- Empty result: widen-radius suggestion and "Remove filters" button.

### 6.5 Provider page (the provider's "homepage")
- **Hero:** one large portfolio image (4:5) with a 2×2 grid of the next four. Overlaid circular 40px buttons (back, save, share) in solid espresso.
- **Identity block:** avatar 72, name (H1), tagline, Verified badge, rating and count, completed bookings, "Usually replies within an hour", neighbourhood only.
- **Sticky tab bar:** Work (default), Services, Reviews, About.
  - **Work:** 3-column square grid. Tapping opens a post viewer with caption, service tag and **"Book this look"**, which opens the booking flow with that service preselected. (An AR "Try this look" button sits behind a feature flag, off.)
  - **Services:** grouped menu rows with name, duration and price. The most-booked row carries a "Most booked" tag (real data only). Packages show good-better-best with the middle one on an ivory card as "Recommended".
  - **Reviews:** summary bars, filter chips by specialty, review cards with a "Verified booking" label and optional photos.
  - **About:** bio, specialties, **languages spoken** (important for diaspora and French markets), policies (cancellation, lateness), what "Verified" means.
- **Sticky bottom bar** (always visible): left "From £25 · Next: Today 15:30", right primary button "Book".
- Desktop: the bar becomes a sticky ivory booking card in the right column.

### 6.6 Booking flow
A full-screen modal on mobile; two columns on web (steps left, ivory summary card right). **Stepper** at the top: three labels with a 6px bar that starts one-third filled (endowed progress) and a line "Step 1 of 3 · about 40 seconds".

- **Step 1, Service.** The most-booked or last-booked service is preselected. Optional add-ons listed below, **never pre-ticked**, with a pinned running total that animates. Packages as three cards with the middle recommended.
- **Where (only if the provider offers house calls).** A control reading "Go to them" or "They come to you", defaulting to the last one used. "They come to you" adds an address step (6A.3) before Step 2, because travel time affects both availability and the travel fee, which is shown before any commitment.
- **Step 2, Time.** A 7-day date strip with dots where slots exist. Time chips three across, 44px. Preselect the soonest slot, or "Your usual: Thu 10:30" if there is history. Show "Times shown in {provider timezone}" when it differs from the device. A "held for you for 10:00" line **only** if the server truly holds it. No slots: "Notify me" (backend permitting).
- **Step 3, Review and pay.** An **ivory summary card** on the dark ground (the contrast moment): service, provider, date and time, address, and a line-by-line price (service, add-ons, any travel, credit applied as "−£5 welcome credit", **total in bold**). Then optional notes, "Save my usual" (on), "Remind me" (on), the payment method (last used, or the platform's wallet pay), and the cancellation sentence in plain words. Button: "Confirm and pay £60" (siennaStrong, 52px, bottom).
- **Guest sign-up** appears here, as a sheet (phone or email code, plus any social sign-in the backend offers). Selections persist through it.
- **Failures:** slot taken, so offer the next three; payment failed, so retry with another method and keep every field. Every payment request carries an idempotency key.

### 6.7 Confirmation
- Emerald band with the stroke drawing a check (320ms), Display "You're booked." Details beneath.
- Actions: Add to calendar, Message, Directions.
- **"Book your next visit"** card: a suggested date from the cadence, one tap.
- Referral prompt: "Give £5, get £5" (shown after the success moment, dismissible once).
- Notification permission pre-explainer if not yet granted: "Reminders 24 hours and 2 hours before."

### 6.8 Bookings tab
- Segmented Upcoming / Past. Cards with provider, service, date and time, status chip (Confirmed emerald, Pending neutral, Completed muted, Cancelled danger).
- Upcoming actions: Reschedule, Cancel (policy shown first), Message, Directions, and **Track** once a trip is live (opens the trip screen, 6A.5). A relative line "in 2 days".
- Past: **Book again** (primary), Leave a review (if not yet), receipt.
- Empty state per 3.7.

### 6.9 Messages
- Thread per booking, with system messages for status changes. Quick replies ("On my way", "Running 10 minutes late"). Image attach. A one-time banner about keeping chats in-app (3.7 rule). Report and block in the thread menu.

### 6.10 Saved
- Two sections: **Favourites** (providers) and **Lookbook** (saved posts and your own before/after photos, each with a private note, such as "Last time: #2 on the sides"). Switching cost comes from this being useful, not from locking anything in.

### 6.11 You
- Wallet (credit with real expiry, history), Referrals (code, share sheet, progress), Loyalty (stamp meter, started with one welcome stamp; reward value must fit the incentive budget), Preferences (language, currency display, Appearance: Match system / Dark / Light / Neutral, hair profile), Payment methods, Notifications (granular; marketing off by default), Privacy and data (export, delete account, a log of when you shared your location and for how long), Help, Legal.

### 6.12 Review flow
- Triggered by a push 2 hours after completion, and an in-app card. One screen: a large star row; after a tap, three optional quick chips and an optional text field and photo ("Show on the provider's page?"). No incentives tied to reviews. Success: gold check, "Thanks. Your review helps others find the right fit."

### 6.13 Notifications
Booking events; reminders 24h and 2h before; rebook nudge (Section 4 limits); marketing only with opt-in. Quiet hours respected. A user with both capabilities receives both kinds; each notification carries an `audience` (customer or provider) so a tap opens the right view, and the copy says which ("As a customer", "As a provider").

---

## 6A. Maps, travel and live location

Maps do three jobs: find someone nearby, enter an address, and reduce anxiety while someone travels. Live location is a safety and convenience feature, never a data-collection feature.

### 6A.1 What ships when

| Capability | Phase | Needs |
| --- | --- | --- |
| Search map view, provider-page map snippet, Directions deep link | F3 | Maps SDK keys |
| Booking choice ("Go to them" or "They come to you"), address entry with autocomplete or pin, travel fee shown before booking | F4 | Places key; server-side geocoding and Routes calculation |
| Provider house-call setup: service area on a map, travel pricing, travel buffers | F5 | Backend service-area and buffer support |
| Live trip tracking and ETA in both directions, trusted-contact link, Get help | F8 | Backend trip states and a location stream; development build; background permissions |

House calls are in v1, so all of this ships before launch. F8 is the last gate before the private beta.

### 6A.2 Map basics

- **One `<MapView>` wrapper.** Native: react-native-maps with the Google provider. Web: `@vis.gl/react-google-maps`. Props: region, markers, route polyline, `onRegionChangeComplete`, theme. No Google-specific code outside the wrapper.
- **Themed maps.** Author three map styles from the tokens, one per theme (JSON `customMapStyle` on native; a styled map ID on web) and swap on theme change. Land = `ground`; roads = `surfaceHigh` with hairline edges; water = a flat, muted grey-green mixed from emerald and ground; parks one step lighter than land; labels in `textMuted`, major roads only; POI icons off except transit. No gradients. A calm map lets provider pins stand out.
- **Markers.** Price pins: a rounded chip reading "From £25"; selected = ivory fill, espresso text; unselected = `surface` with hairline; a tiny emerald dot for verified. The live provider marker is the Omalicha mark (sienna) on a 44px ivory circle. The customer marker is a ringed emerald dot.
- **Behaviour.** Cluster above 40 pins. A "Search this area" button appears after panning (ivory, top centre). The result list sits in a bottom sheet with three snap heights (peek 112, half, full) and stays in sync with the viewport.
- **Privacy.** Home-based providers appear as a server-fuzzed neighbourhood circle, not a pin. The client never receives exact coordinates until a booking is confirmed.
- **Accessibility.** The map is supplementary: every map view has an equivalent list, and selecting a pin announces the result.

### 6A.3 Addresses

- **Autocomplete** through Places (New): session tokens, 300ms debounce, at least three characters, restricted to the active market's country, and only the fields you need (formatted address, coordinates). Send the chosen place to the backend, which geocodes it and decides service-area eligibility and travel fee.
- **Informal addresses.** In Nigeria, Côte d'Ivoire and Senegal, street addresses are often informal or missing from map data (**Verify** with local users). Always offer "Drop a pin" with a draggable pin plus a required "Landmark or directions" field ("Opposite the blue gate, second floor"). Never block checkout because autocomplete finds nothing.
- **Saved addresses** (Home, Work, custom) with an optional access note; the last used is the default. Show the address as a plain sentence; add a map thumbnail only when it helps, because static maps cost money.

### 6A.4 Travel pricing display

- When travel is involved, show service price, travel fee ("Travel £6 · 3.2 km") and total, **before** the Confirm step and, once an address is known, on search cards as "+ travel £X". The backend computes distance and fee; the client never does.
- If the address is outside the provider's area, say so plainly and suggest providers who cover it.
- State who travels in words and an icon: "Comes to you" or "You go to them".

### 6A.5 Live trip tracking

**States** (owned by the server): Confirmed → On the way → Arrived → In progress → Completed (or Cancelled / No-show). "On the way" starts sharing for the traveller; "Arrived" and "Completed" stop it.

**Who shares what**

- **Provider travels to the customer (house calls).** The provider taps "Start trip"; the customer sees live position, route and ETA on the Trip screen. Prompt the provider 60 minutes before the appointment with a one-tap "Start trip". Sharing is per trip and explicit, and the house-call terms say providers will share during trips. Whether sharing can be a *required* condition of offering house calls is a counsel decision (see the business plan), so build it as a setting the backend can enforce either way. The location is used only for ETA and safety, never for ranking, penalties or performance scoring.
- **Customer travels to the provider.** The customer may tap "Share my ETA"; the provider sees ETA and live position until arrival. This is **optional and off by default**, one tap, offered once per booking, because it lowers no-shows without being forced.
- **Both directions get identical controls:** a visible indicator, one-tap stop, automatic end, and no history.

**Rules (non-negotiable)**

- Opt-in, per booking, started by an explicit tap. Never silent, never outside a booking window.
- The window runs from the tap until arrival, completion or cancellation, and hard-stops 30 minutes after the appointment start if still running (configurable).
- Always visible: a persistent in-app banner, the Android foreground-service notification, and the iOS system location indicator. A one-tap "Stop sharing" everywhere.
- The other party sees live position only: no history, no breadcrumb trail.
- Within about 100m of the destination, prompt "Arrived?" rather than auto-completing.
- If permission is denied or signal drops, fall back to ETA text and manual status taps. The feature degrades; the booking never breaks.
- Customers use "While using the app" permission. Providers on house calls need background location while driving, requested at onboarding for that trip purpose only.

**Trip screen, customer view.** Top 60%: the map (provider marker, route polyline in sienna at 4px, destination pin). Bottom: an ivory card (the contrast moment) with a status line in Fraunces H2 ("Ade is 8 minutes away"), a progress bar across the states, avatar and name, and buttons: Message (primary), Call (secondary; masked number if the backend provides one), Share trip (a read-only link for a trusted contact that expires with the trip), Get help, Report. Numbers animate on change; a caption reads "Updated just now", turning to "Last updated 3 min ago" if stale beyond two minutes. Reduced motion: the marker jumps instead of gliding. **Get help** opens the phone dialler with the local emergency number for the market (kept in config; **Verify** each number) and offers to report to Omalicha. It must never imply that Omalicha is monitoring the trip.

**Trip screen, provider view.** The map with the destination and ETA, a prominent "Open in Google Maps" deep link for turn-by-turn (do not build navigation), "I've arrived", "Running late" (sends a message and updates the ETA), "Stop trip", and the same Share trip and Get help controls.

### 6A.6 Location technology and cost control

- **Publishing position.** `expo-location` in the foreground. For house-call providers, a background task with `expo-task-manager` (`startLocationUpdatesAsync`, balanced accuracy, 50m distance interval, 10s time interval). Request foreground permission first, then background, each after a plain-language pre-explainer. On iOS this needs the "Always" permission and the `location` background mode; on Android, foreground and background permissions plus a foreground service with a visible notification ("Sharing your location until you arrive"). Handle "Allow once". All of this needs a development build.
- **Transport.** Batch updates to the backend (about every 10s while moving, 30s when still) over the existing API or a WebSocket or SSE channel; the backend relays them to the other party.
- **ETA is computed on the server**, never by calling Google from the device. Call the Routes API once at trip start (traffic-aware), then refresh only about every 3 minutes or when the traveller strays more than about 300m from the route, with a hard cap per trip. Per search summaries of Google's 2026 pricing, Routes Essentials is about $5 per 1,000 calls with 10,000 free a month, and traffic-aware Pro about $10 per 1,000 with 5,000 free. At roughly 12 calls per trip, 1,000 trips a month costs about $10 to $70 after the free allowances. **Verify** current prices.
- **Map display.** The mobile Maps SDKs are free per the same summaries; web map loads are billed after a free allowance. Keep heavy map use in the apps; on web, lead with the list and load the map on tap.
- **Autocomplete.** Session tokens, minimum characters, debounce. Restrict each API key (iOS bundle ID, Android package and SHA-1, web referrers), use separate keys per platform and environment, set daily quotas and billing alerts in Google Cloud before launch, and never commit keys.
- **Static map images** are billed separately: use sparingly and cache.

### 6A.7 Retention and privacy

- Keep only what is needed: the latest position for an active trip, discarded when the trip ends, plus a minimal trip log (start and end times, arrival flag, route distance) for disputes and safety. Delete raw location points within a short, fixed period (24 hours is a sensible starting proposal; longer only for a reported incident). **Verify** retention and consent with counsel (UK GDPR, Nigeria's NDPA, and the French-speaking markets' declaration and transfer rules).
- Run a data protection impact assessment before launch. Permission copy in plain words: "We use your location only to show {name} how close you are, and only until you arrive."
- Never use trip location for advertising, profiling, ranking or analytics. Never sell or share it.
- **You > Privacy** shows a log of when you shared location and for how long. This is cheap and builds trust.

---

## 7. Provider screens

Providers are the supply. Make them successful in their first ten minutes. Existing customers arrive through **Become a provider** in You; they keep their customer history, which never appears on their public provider page.

- **Onboarding:** a gold **profile-strength ring** (starts at 20%). Checklist with the next step only: add six photos, add services, set availability, verify ID, connect payouts. Each step says why. The page goes live at 60%. (The backend must actually use completeness in ranking before the UI claims it.)
- **Today:** next appointment on an ivory card; this week's earnings as a Fraunces number; quick actions: Share my booking link (copy, QR, Instagram-bio instructions), Add a post.
- **Calendar:** day and week views; long-press to block time; availability editor with templates and "copy last week"; timezone shown.
- **Bookings:** confirm or decline (if approval mode), reschedule, mark complete (this releases payout in escrow flows), client notes, history.
- **Clients:** list with last visit and **next due** (from cadence), notes, "Send rebook link". Import is allowed with a clear consent reminder that they must have permission to message those people.
- **Portfolio manager:** multi-select upload, client-side resize and compress, caption, tag service and specialty, reorder, before/after pairing, alt text prompt.
- **Services and pricing:** templates by technique and length (neutral names), duration, price (within the price range they accept), add-ons, packages with good-better-best guidance, buffer times.
- **House calls:** a map with a service-area circle (radius slider; polygons later), travel pricing (flat bands or per distance, shown to customers before booking), minimum notice, and **travel buffers** that block time between a house call and the next booking. Providers choose which services they offer at home. Turning house calls on requires the verification and insurance steps listed in the business plan, and the screen shows which are still missing.
- **Earnings:** balance, upcoming payouts, and a **line-by-line fee breakdown** ("Omalicha fee £12, new client") so nothing is hidden. Payout setup state (Stripe or Flutterwave hosted flow in a webview or browser). Disputes list.
- **Plans:** an honest Free versus Pro table. Pro adds SMS and WhatsApp reminders, detailed analytics and rebooking campaigns, at the same fees. Trial status and "what you'd keep" at the end. ID verification stays free. No pressure banners.
- **Insights:** views to bookings, repeat rate, top services (basic free, detailed Pro).
- **Reviews:** reply publicly, report abuse.
- **Milestones:** "7 of 10 bookings to a free Pro month" (goal gradient, real).

---

## 8. Components to build first

Build each from tokens, with all states, in a `/dev/gallery` route.

| Component | Spec |
| --- | --- |
| Button | Primary: `siennaStrong` fill, ivory 16/600, 52px, radius 14. Secondary: `surfaceHigh` + hairline. Tertiary: text only. Destructive: danger outline. Loading: spinner arc in ivory. Disabled at 40% opacity with a reason where possible. |
| Chip | 40px, radius 999. Selected = ivory fill, espresso text. |
| Input | 52px, `surfaceHigh`, 1px hairline, focus ring 2px ivory, label above, error text with icon. |
| Card | `surface`, radius 16, 1px hairline, padding 16. |
| Sheet | `surface`, radius 24 top, 60% scrim, drag handle, spring. |
| Avatar | Circle; initials fallback on `surfaceHigh`. |
| RatingStars | Gold, 16px, with numeric value and count. |
| Badge | Verified: emerald fill, ivory 12/600 text, check icon. |
| Progress bar / ring | 6px bar, sienna fill on `surfaceHigh` track; ring in gold. |
| Stepper | Three labels over the progress bar. |
| SlotChip | 44px; selected = `siennaStrong` fill, ivory text. |
| PriceText | Tabular numerals; takes minor units and currency. |
| Toast | `surfaceHigh`, hairline, top safe area; no shadow. |
| Skeleton | Opacity pulse. |
| EmptyState | Stroke drawing, one line, one action. |
| ProviderCard, PortfolioGrid, ListRow, Segmented, Divider, MarkSpinner | Per Section 6. |

Tokens file (create `src/theme/tokens.ts`):

```ts
export const dark = {
  ground: '#221C19', surface: '#2B2320', surfaceHigh: '#362D29', hairline: '#4A3F39',
  text: '#FBF4EC', textMuted: '#CFC3B6', textSubtle: '#A39688',
  sienna: '#AD5E36', siennaStrong: '#9E5530', emerald: '#2F6F5E', emeraldTint: '#5FAE97',
  gold: '#C9A24B', goldDeep: '#C9A24B', danger: '#DB6F63',
  siennaText: '#FBF4EC', emeraldText: '#5FAE97', // never use sienna for small text on dark
} as const;

export const light = {
  ground: '#FBF4EC', surface: '#FFFFFF', surfaceHigh: '#F3EADF', hairline: '#E4D9CB',
  text: '#2B2320', textMuted: '#6B6058', textSubtle: '#6B6058',
  sienna: '#AD5E36', siennaStrong: '#9E5530', emerald: '#2F6F5E', emeraldTint: '#2F6F5E',
  gold: '#C9A24B', goldDeep: '#9A7A2B', danger: '#B3423A',
  siennaText: '#9E5530', emeraldText: '#2F6F5E',
} as const;

export const neutral = {
  ground: '#D9CFC3', surface: '#E8E0D6', surfaceHigh: '#F1EAE1', hairline: '#BFB3A5',
  text: '#2B2320', textMuted: '#5A4F47', textSubtle: '#5A4F47',
  sienna: '#AD5E36', siennaStrong: '#9E5530', emerald: '#2F6F5E', emeraldTint: '#25584A',
  gold: '#C9A24B', goldDeep: '#9A7A2B', danger: '#9C3029',
  siennaText: '#8A4726', emeraldText: '#25584A',
} as const;

export type Palette = { [K in keyof typeof dark]: string };
export type Appearance = 'system' | 'dark' | 'light' | 'neutral';
export const palettes: Record<'dark' | 'light' | 'neutral', Palette> = { dark, light, neutral };

export function resolvePalette(a: Appearance, system: 'light' | 'dark' | null | undefined): Palette {
  const key = a === 'system' ? (system === 'light' ? 'light' : 'dark') : a;
  return palettes[key];
}

export const space = [0, 4, 8, 12, 16, 20, 24, 32, 40, 56] as const;
export const radius = { sm: 10, md: 14, lg: 16, sheet: 24, pill: 999 } as const;
```

Money and time helpers (create `src/lib/format.ts`):

```ts
const EXP: Record<string, number> = { GBP: 2, EUR: 2, NGN: 2, KES: 2, ZAR: 2, GHS: 2, XOF: 0 };

export function formatMoney(minor: number, currency: string, locale: string) {
  const exp = EXP[currency] ?? 2;
  return new Intl.NumberFormat(locale, {
    style: 'currency', currency, minimumFractionDigits: 0, maximumFractionDigits: exp,
  }).format(minor / 10 ** exp); // display only: never do arithmetic on this value
}

export function formatSlot(utcIso: string, providerTz: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    timeZone: providerTz, weekday: 'short', hour: '2-digit', minute: '2-digit',
  }).format(new Date(utcIso));
}
```

---

## 9. States, offline and performance

- **Every screen has loading (skeleton), empty, error (with retry and kept input), and offline states.**
- **Budgets:** first useful content in under 2.5s on a mid-range Android over slow 4G; list scrolling at 60fps; initial JS bundle kept lean (report its size each phase).
- **Images:** request sized variants (about 320 / 640 / 1080px wide) with WebP or AVIF from the media CDN; ThumbHash placeholders; cards load thumbnails only; **no video autoplay on cellular**, poster until tapped.
- **Uploads:** resize client-side to 1600px on the long edge at about 0.8 quality; queue with resumable retries; show per-file progress; survive app backgrounding.
- **Offline:** cache the user's upcoming bookings, favourites and last search; queue message sends; show an "Offline" strip, never a blocking error.
- **Errors:** friendly, specific, never blaming. Map API 422 field errors onto form fields. Retry with backoff on idempotent calls only.

---

## 10. i18n, accessibility, compliance hooks

- **i18n:** EN and FR keys from day one, ICU plurals, locale-aware dates and money, layouts that tolerate 30% longer text. French drafts carry `// TODO native review`. Category and specialty labels are i18n keys by slug (`specialty.fade`), never served by the API.
- **Accessibility:** labels on every control and image, logical focus order, 44px targets, visible focus, dynamic type, reduced motion, captions for video, errors never colour-only, screen-reader tested booking flow.
- **Compliance hooks:** location pre-explainers, a visible sharing indicator and one-tap stop (Section 6A); privacy notice and consent screens; age confirmation (18+) at signup; cookie banner on web with equal-weight Accept and Reject; marketing opt-in unticked; "How ranking works" link beside sort; sponsored or boosted placement labelled; review authenticity (only verified bookings); report and block everywhere; in-app account deletion and data export; cancellation and refund summary before payment.

---

## 11. Data layer

- Typed client from OpenAPI; one `api` module; a query-key factory per resource.
- Optimistic updates for favourites, messages, toggles. Prefetch a provider page on card press-in.
- `Idempotency-Key` on booking and payment writes (confirm backend support; Section 14).
- Auth: tokens in SecureStore; refresh on 401 once, then sign out cleanly.
- **Provider routes return 404, not 403, when the user has no provider profile.** Gate provider screens on `capabilities`, never call provider routes without it, and treat a 404 from a provider route as "no provider profile yet" (send the user to Become a provider), not as a missing page. Every API error carries `error_code`, `detail`, optional `params` and `fields`, and `request_id`. Map `error_code` to an i18n message key (the app never shows `detail` outside dev builds, because it is English only), use `params` for placeholders, map `fields` onto form inputs, and show the `request_id` as a small reference on error screens so support can find the log entry.
- Feature flags in a local config for now (AR try-on off, product marketplace off, slot hold off until the backend supports it).

---

## 12. Analytics and experiments

Privacy-first: no events before consent; no PII in properties. Core events: `search_performed`, `provider_viewed`, `post_viewed`, `book_started`, `booking_step_completed`, `booking_confirmed`, `booking_abandoned` (with step), `rebook_tapped`, `review_submitted`, `referral_shared`, `provider_activated` (first booking within 14 days), `map_viewed`, `address_entered` (method: autocomplete or pin), `trip_started`, `trip_sharing_stopped` (reason: arrived, manual, timeout). Dashboard metrics: search to profile to booking conversion, time to book, rebook within cadence, in-app repeat rate (leakage), review rate, provider activation. Run experiments on defaults and copy only once traffic can detect an effect.

---

## 13. Build order and acceptance

| Phase | Build | Accepted when |
| --- | --- | --- |
| F0 | Expo project, tokens, fonts, i18n, OpenAPI client, auth storage, error boundary, CI | App boots on iOS, Android and web; typecheck, lint, tests green; splash with the mark shows |
| F1 | Component gallery (`/dev/gallery`) with every primitive in dark, light and neutral | Every component and state visible in all three themes; Appearance setting switches live and persists without a flash; contrast table verified |
| F2 | Welcome, sign-in, location, taste profile | A guest can browse; sign-in works; no gender or race fields exist |
| F3 | Discover, search and filters (list and themed map views), provider page (read-only) | Real API data; skeletons, empty and error states; texture and technique filters work; the map matches all three themes |
| F4 | Booking flow including the house-call choice, address entry and travel fee, confirmation, Bookings tab, messages (payment stubbed) | A shop booking and a house-call booking both complete end to end in Maestro; defaults and stepper behave as in 6.6 |
| F5 | Provider side: onboarding ring, calendar, portfolio upload, services, house-call setup, bookings | A new provider reaches "live" in under ten minutes; enabling house calls shows the verification steps still required |
| F6 | Reviews, favourites and lookbook, wallet, referrals, loyalty, notifications | Credits show real expiry; no dark patterns present |
| F7 | Stripe (UK) and Flutterwave (NG) payment UI, French localisation, accessibility pass, performance pass | Budgets in Section 9 met; screen-reader run-through passes |
| F8 | Live trip tracking, trusted-contact link, Get help, themed map styles (house-call address entry and travel fees land in F4 and F5) | Both parties can start and stop sharing; it degrades cleanly with permission denied or no signal; tested on low-end Android phones; API cost caps verified; **required before the private beta** |

After each phase: screenshots of every new screen in dark, light and neutral, the bundle size, and a list of anything you deliberately did not do.

---

## 14. Backend gaps to raise (do not assume these exist)

**Already shipped:** `capabilities` on the current-user response and `audience` on notifications. **Audit first:** whether services (with duration, price, add-ons and packages) exist in the data model at all; Sections 6.5, 6.6 and 7 assume they do.

Slot holds with a server-side expiry · categories and specialties endpoints (specialties returned as slugs with the categories they belong to; labels localised on the client) · "next available" on search results · typical-price statistics per service and city with a minimum sample · favourites, lookbook and private notes · credit wallet ledger with expiry and platform-funded credits · referral codes and attribution · loyalty stamps · rebook endpoint and per-category cadence settings · profile-completeness score used in ranking · idempotency keys on writes · sized image variants from a media CDN · push-notification tokens and quiet-hours preferences · cursor pagination on lists · French translations for server-rendered messages · a trip state machine and a live-location channel (WebSocket or SSE) · server-side Routes calls for ETA and travel fee with per-trip call caps · service areas and travel pricing rules per provider · fuzzed public coordinates for home-based providers, with exact address released only after booking · location retention and deletion jobs plus a sharing-log endpoint · masked phone numbers for calls · house-call booking with service-area eligibility and travel buffers in availability · a travel-fee quote endpoint · read-only trusted-contact trip links · an incident-report flow with a named owner · provider handles for booking links and deep links · saved addresses with a landmark and access note · a market-config endpoint (currency, languages, emergency number, rebook cadence defaults) · a fee policy with a snapshot on each booking · provider plans and entitlements · a lightweight map-search endpoint · portfolio post tags and before/after pairs · provider replies and consented photos on reviews.

---

## 15. Review checklist for every screen (owner's gate)

1. Would this look the same for anyone, regardless of gender or background?
2. Does any text sit directly on a photo, or any gradient, glow, blur or shadow appear?
3. Is every claim backed by real data?
4. Are small texts at least 4.5:1 contrast, and meaning not colour-only?
5. Does the primary action sit in the thumb zone, one per screen?
6. Does it work with slow data, offline and French?
7. Could a person finish the task without an account, until the last step?
