# Alluora Platform Architecture

## The shape of the system

Three pieces, each owning a clear slice of the product:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Flutter app  ─────────────────►  WordPress + alluora-app-bridge       │
│  (iOS/Android)   auth / orders        (auth, customers, products,       │
│                  /products             orders — owned by Woo)           │
│                                                                         │
│        │                                  ▲                             │
│        │                                  │ /auth/me check              │
│        │                                  │                             │
│        │  content / videos /              │                             │
│        ▼  rewards / quiz                  │                             │
│                                                                         │
│   Django + custom dashboard ──────────────┘                             │
│   (Railway: web + Postgres + volume)                                    │
│   • content, articles                                                   │
│   • Bunny.net Stream videos                                             │
│   • rewards ledger + badges                                             │
│   • skin quiz                                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

WordPress is the **system of record for commerce**. Django is the **system of record for content & engagement**. The Flutter app talks to both. There is no replication of customer or order data — the Django side mirrors a thin user record (the `AppUser` table) keyed on `wp_user_id`, populated lazily on first contact.

## How auth flows

Customer accounts live in WordPress. The mobile app logs in via the `alluora-app-bridge` plugin (`POST /wp-json/alluora/v1/auth/login`) which sets standard WordPress session cookies on the response. The plugin returns a REST nonce in the response body which the app must echo back as `X-WP-Nonce` on every protected call.

Django doesn't issue its own tokens. When the app calls Django, it carries the WordPress cookie and nonce. Django's `WordPressCookieAuthentication` class forwards them to WordPress's `/auth/me` endpoint (with a 60-second result cache to avoid hammering it), trusts the response, and creates or updates an `AppUser` row keyed on `wp_user_id`. From there, every Django ORM call can use `request.user` normally.

The dashboard at `/dashboard/` uses regular Django session auth — completely separate from the mobile-app auth. The two never overlap. The bootstrap admin command (`python manage.py create_admin`) reads `BOOTSTRAP_ADMIN_*` env vars on every deploy and idempotently creates or updates the dashboard admin user.

## The Flutter app's two API clients

Two `Dio` clients with separate cookie jars, but the Django one **borrows the WP cookies and nonce on every request** by reaching into the WordPress client's jar. This is the cleanest way to keep auth in one place: the user only types their password into the WP login screen, and Django gets identity for free.

```
WordPressApi.instance  ─────►  https://staging.alluora.com/wp-json/alluora/v1
   ▲ owns the cookie jar
   │
   │ DjangoApi pulls cookies + nonce
   │
DjangoApi.instance     ─────►  https://staging-api.alluora.com/api/v1
```

The Shop tab is a webview pointing at `/shop` on `staging.alluora.com`. Cookies are synced from the `dio` jar into the webview cookie store before the page loads, so the user lands on the storefront already signed in. Checkout happens in the webview — payment, tax, shipping, coupons all stay inside Woo where they belong.

## The Bunny upload flow

Uploads are direct from the dashboard browser to Bunny's TUS endpoint. Django never proxies bytes. The flow is:

1. Dashboard calls `POST /api/v1/videos/admin/create/` with title + collection. Django calls Bunny's "Create Video" endpoint and gets back a video GUID. It writes a `Video` row with `status=created`.
2. Dashboard calls `POST /api/v1/videos/admin/{id}/presign/`. Django generates a SHA-256 signature `(library_id + api_key + expiration + video_id)` and returns the headers the TUS client needs.
3. Dashboard's JS uses `tus-js-client` to upload directly to `https://video.bunnycdn.com/tusupload` with those headers. Resumable, chunked, doesn't touch our Railway bandwidth.
4. Dashboard polls `POST /api/v1/videos/admin/{id}/sync/` — Django queries Bunny for the latest status and updates the row.
5. When `status=ready`, the dashboard flips `is_published=true` and the video appears in the app's `/api/v1/videos/` list.

## Data ownership matrix

| Domain | System | Reason |
|---|---|---|
| User credentials & passwords | WordPress | Already owns them; not duplicating. |
| Products, prices, stock, variants | WooCommerce | The whole point of Woo. |
| Orders, payments, refunds | WooCommerce | Tax/shipping/payment-gateway pipeline. |
| Customer billing/shipping addresses | WooCommerce | Tied to checkout. |
| Articles, editorial content | Django | New feature, no Woo overlap. |
| Videos (metadata) | Django | Bunny stores bytes; Django stores titles/collections/featured. |
| Videos (bytes + transcoding + HLS) | Bunny.net | Their core competency. |
| Reward points ledger | Django | New currency we control. |
| Badges | Django | Same. |
| Skin quiz results | Django | New. |
| Push notification tokens | Django (future) | Will register tokens on first launch. |

## Deployment shape on Railway

Two services:

1. **alluora-backend** — the Django app. Public domain. Connected to:
   - Postgres service (provides `DATABASE_URL`)
   - Volume mounted at `/data` for media uploads (`MEDIA_ROOT=/data/media`)
2. **alluora-postgres** — managed Postgres add-on.

WordPress (staging.alluora.com) lives wherever it lives now — it's not on Railway. Django talks to it over public HTTPS.

## What this architecture deliberately doesn't do

- **No JWT.** Customer auth is WordPress cookies. Django piggybacks. No token refresh, no rotating secrets, no `wp-config.php` edits.
- **No native checkout in the Flutter app.** Webview into Woo. We considered this and rejected it; reimplementing Woo's checkout pipeline in Flutter is a 4-6 week project all by itself with high failure modes (tax zones, payment intents, coupon stacking, stock holds, etc.).
- **No content duplication.** If WordPress already has a blog, we don't sync it. The Django `Article` model is for app-specific editorial content the website doesn't show.
- **No Bunny library API exposed to the mobile app.** The app only sees finished, published videos via the public `/api/v1/videos/` endpoint. All admin-side Bunny operations are gated behind `IsDashboardAdmin`.

## Where to extend it

- **Push notifications:** add `apps/notifications/` with a `DeviceToken` model (FK to `AppUser`), a `POST /api/v1/notifications/register-token/` endpoint, and a Django management command that talks to FCM/APNs.
- **In-app chat / DM with brand:** add `apps/messaging/` with `Conversation`/`Message` models. Real-time would need Channels + Redis on Railway.
- **Native checkout:** when revenue justifies it, build it as a Phase 3 — talk directly to the Stripe SDK in-app, then `POST /orders` to Woo with the payment intent ID.
