# API Reference — Alluora Platform

The Flutter app calls **two** APIs. Use this as the contract while building screens.

| Concern | Owner | Base URL |
|---|---|---|
| Auth, products, orders, customer profile | WordPress (alluora-app-bridge plugin) | `https://staging.alluora.com/wp-json/alluora/v1` |
| Content, videos, rewards, quiz | Django (this repo) | `https://staging-api.alluora.com/api/v1` |

Both APIs use **WordPress cookies + `X-WP-Nonce`** for auth. The WordPress side issues them; the Django side validates them by forwarding to WordPress's `/auth/me`.

---

## WordPress endpoints (alluora-app-bridge)

All endpoints under `/wp-json/alluora/v1/`.

### `POST /auth/login`

Sets WP session cookies on the response. Returns user + nonce.

**Body**
```json
{ "username_or_email": "jane@example.com", "password": "...", "remember": true }
```

**Response (200)**
```json
{
  "success": true,
  "data": {
    "user": { "id": 42, "email": "jane@example.com", "first_name": "Jane", "last_name": "Tan", "billing": {...}, "shipping": {...} },
    "nonce": "abc123..."
  }
}
```

### `POST /auth/register`

**Body**
```json
{ "email": "...", "password": "...", "first_name": "...", "last_name": "...", "phone": "..." }
```

Creates a Woo `customer` role user, syncs billing fields, fires `woocommerce_created_customer`, sets cookies, returns user + nonce.

### `GET /auth/me` *(cookie + nonce)*

Returns current user + a fresh nonce. Use this to refresh the nonce before it expires (WP defaults to 12-24h).

### `POST /auth/logout` *(cookie + nonce)*

Clears the auth cookies. Idempotent.

### `POST /auth/forgot-password`

```json
{ "email": "..." }
```

Always returns 200 to prevent email enumeration.

### `POST /auth/change-password` *(cookie + nonce)*

```json
{ "current_password": "...", "new_password": "..." }
```

### `GET /customer/profile` *(cookie + nonce)* / `PATCH /customer/profile`

```json
// PATCH body — any subset
{ "first_name": "...", "last_name": "...", "display_name": "...", "phone": "..." }
```

### `PUT /customer/addresses/{billing|shipping}` *(cookie + nonce)*

Full address object body — `first_name`, `last_name`, `company`, `address_1`, `address_2`, `city`, `state`, `postcode`, `country`, plus `email`/`phone` for billing or `phone` for shipping.

### `GET /orders` *(cookie + nonce)*

Query: `?per_page=10&page=1&status=any|processing|completed|...`

```json
{
  "success": true,
  "data": {
    "orders": [ { "id": 123, "number": "AL-123", "status": "processing", "total": "89.50", "currency": "SGD", "date_created": "...", "item_count": 2 } ],
    "total": 47, "total_pages": 5, "page": 1, "per_page": 10
  }
}
```

### `GET /orders/{id}` *(cookie + nonce)*

Same shape but with `items[]`, `billing_address`, `shipping_address` populated. Returns 404 if the order doesn't belong to the calling user (no enumeration possible).

### `GET /products` *(public)*

Query: `?per_page=20&page=1&category=skincare&search=serum&on_sale=1`

```json
{
  "data": {
    "products": [ { "id": 5, "name": "...", "price": "39.00", "regular_price": "49.00", "sale_price": "39.00", "on_sale": true, "image": "https://...", "permalink": "https://..." } ],
    "total": 47, "total_pages": 3, "page": 1, "per_page": 20
  }
}
```

### `GET /products/{id}` *(public)*

Detail view — adds `description`, `gallery[]`, `stock_status`, `attributes[]`.

### `GET /products/categories` *(public)*

```json
[ { "id": 12, "name": "Cleansers", "slug": "cleansers", "count": 8, "image": "..." } ]
```

---

## Django endpoints

All endpoints under `/api/v1/`. Pagination follows DRF's `PageNumberPagination` — responses are wrapped:

```json
{ "count": 47, "next": "...?page=2", "previous": null, "results": [ ... ] }
```

### Accounts

#### `GET /accounts/me/` *(cookie + nonce)*

```json
{ "id": 1, "wp_user_id": 42, "email": "...", "first_name": "...", "display_name": "...", "phone": "...", "avatar_url": "...", "reward_points": 240, "last_synced_at": "..." }
```

### Content

#### `GET /content/articles/` *(public)*

Query: `?category=4&is_featured=true&search=serum&page=1`

```json
{ "results": [ { "id": 1, "slug": "the-ritual-of-cleansing", "title": "...", "summary": "...", "cover": "...", "category": 4, "category_name": "Tips", "author_name": "...", "is_featured": true, "published_at": "..." } ] }
```

#### `GET /content/articles/{slug}/` *(public)*

Same as list shape plus `body` (Markdown).

#### `GET /content/categories/` *(public)*

```json
{ "results": [ { "id": 1, "name": "Tips", "slug": "tips", "sort_order": 0 } ] }
```

### Videos

Public read endpoints + admin-only write endpoints.

#### `GET /videos/` *(public)*

Returns only published, ready videos.

```json
{ "results": [ { "id": 1, "title": "...", "description": "...", "collection": 2, "collection_name": "Tutorials", "duration_seconds": 240, "is_featured": true, "hls_url": "https://.../playlist.m3u8", "thumbnail_url": "https://.../thumbnail.jpg", "created_at": "..." } ] }
```

Use `hls_url` with a Flutter video player that supports HLS (e.g. `video_player` + `chewie`).

#### `GET /videos/{id}/` *(public)*
#### `GET /videos/collections/` *(public)*

#### Admin upload flow *(dashboard auth required)*

```
1. POST /videos/admin/create/        → returns Video record with bunny_video_guid
   { "title": "...", "description": "...", "collection_id": 1 }

2. POST /videos/admin/{id}/presign/  → returns TUS upload headers
   {
     "tus_endpoint": "https://video.bunnycdn.com/tusupload",
     "video_id": "guid", "library_id": "12345",
     "authorization_signature": "sha256...", "authorization_expire": 1746789012,
     "expires_at": 1746789012
   }

3. (browser) tus-js-client uploads bytes directly to Bunny

4. POST /videos/admin/{id}/sync/     → polls Bunny status, updates DB
```

### Rewards

#### `GET /rewards/balance/` *(cookie + nonce)*

```json
{ "balance": 240, "badges": [ { "id": 1, "badge": { "id": 4, "slug": "first-quiz", "name": "First Quiz", "icon": "..." }, "awarded_at": "..." } ] }
```

#### `GET /rewards/history/` *(cookie + nonce)*

Paginated ledger entries:

```json
{ "results": [ { "id": 12, "points": 5, "source": "video", "description": "Watched: Fade dark spots in 28 days", "reference_id": "video:42", "created_at": "..." } ] }
```

### Quiz

#### `GET /quiz/{slug}/` *(public)*

```json
{
  "id": 1, "slug": "skin-type", "name": "Find your skin type", "intro": "...",
  "questions": [
    { "id": 1, "text": "How does your skin feel after cleansing?", "sort_order": 0,
      "options": [ { "id": 1, "text": "Tight and dry", "sort_order": 0 } ] }
  ]
}
```

#### `POST /quiz/{slug}/submit/` *(cookie + nonce)*

```json
{ "answers": [1, 5, 9, 13, 17] }
```

Server computes weighted scores and returns:

```json
{
  "id": 78, "quiz_slug": "skin-type", "quiz_name": "Find your skin type",
  "primary_result": { "id": 2, "slug": "combination", "name": "Combination", "summary": "...", "long_description": "...", "image_url": "..." },
  "score_breakdown": { "oily": 4, "dry": 2, "combination": 7, "sensitive": 1 },
  "submitted_at": "..."
}
```

#### `GET /quiz/submissions/` *(cookie + nonce)*

User's quiz history.

---

## Error shapes

WordPress returns:
```json
{ "code": "invalid_credentials", "message": "Invalid username or password.", "data": { "status": 401 } }
```

Django (DRF) returns:
```json
{ "detail": "Authentication credentials were not provided." }
```

Both clients in `services/wordpress_api.dart` and `services/django_api.dart` already handle this — `_unwrap()` throws `ApiException(message, statusCode)` for non-2xx responses on the WP side, and the Django side returns `null` for 401/403 on safe-to-fail calls.

## Rate limits

WordPress: 5 login + 5 register attempts per IP per 15 minutes (configurable in plugin settings). On exceed: HTTP 429 with `code: rate_limited`.

Django: no per-route limits configured yet. Add `django-ratelimit` if you want them.

## Cookie + nonce lifecycle on the app

```
on app launch
  → WordPressApi.init() loads persisted cookie jar
  → AuthService.bootstrap() calls /auth/me
      → if 200: state = authenticated, nonce stored
      → if 401: state = anonymous, router redirects to /onboarding

on every protected request
  → cookie jar adds Cookie header automatically
  → interceptor adds X-WP-Nonce: <stored nonce>
  → server may return a refreshed nonce in /me responses; we update the stored value

on logout
  → POST /auth/logout (server clears its session)
  → cookie jar emptied
  → nonce cleared
```
