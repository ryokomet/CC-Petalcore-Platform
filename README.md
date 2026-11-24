# Petalcore Platform

Petalcore Platform brings the three Petalcore sites together under one website. The home page links to Index, ID, and Select.

## How it works

The Platform serves the three website pages and a shared FastAPI service. Each site uses its own API key when it requests data. Index searches the plant catalog, ID sends a photo to Pl@ntNet and displays possible matches, and Select compares a user's preferences with the catalog. The private Pl@ntNet key stays on the server.

## How to use it

Open the Petalcore Platform home page and choose a site:

- **Index** (`/index/`): search or browse the plant library, then open a plant to read more.
- **ID** (`/id/`): upload a JPG or PNG photo, choose a plant part, and view possible matches.
- **Select** (`/select/`): choose details about your space and preferences, then view suggested plants.

The photo results and Select recommendations are suggestions to help with plant discovery. They should not be treated as a certain identification or guarantee.

## Plant API

The shared plant catalog is stored in the PostgreSQL `plants` table. The API reads the current database contents for browsing, detail, search, and Select recommendations.

Open `/admin/` for a visual catalog workspace. It provides list, search, detail, create, edit, and delete controls, supports adding up to 10 plants in one batch, and shows the latest API request and response. Every new plant needs a JPG or PNG image. Editing can replace an image or update only selected plant fields. Enter the admin key when unlocking; the page keeps it in memory only and clears it when locked or reloaded.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/plants` | List plants ordered by ID. |
| `GET` | `/api/v1/plants/{plant_id}` | Read one plant. |
| `GET` | `/api/v1/plants/search?q=rose` | Search common and scientific names. |
| `GET` | `/api/v1/plants/{plant_id}/image` | Read the plant's uploaded image. |
| `POST` | `/api/v1/plants` | Create a plant and upload its required image. |
| `POST` | `/api/v1/plants/bulk` | Create up to 10 plants with one image per plant. |
| `PUT` | `/api/v1/plants/{plant_id}` | Replace all editable fields. |
| `PATCH` | `/api/v1/plants/{plant_id}` | Update only the submitted fields. |
| `PUT` | `/api/v1/plants/{plant_id}/image` | Replace a plant's uploaded image. |
| `DELETE` | `/api/v1/plants/{plant_id}` | Delete a plant. |

Read requests continue to use the Index or Select client API key. Write requests require the separate `PETALCORE_ADMIN_API_KEY` environment variable. Configure it alongside `DATABASE_URL` in the API deployment environment and redeploy. Keep the admin key on the server or in a trusted administrative client; do not put it in a website's JavaScript or expose it through a public config endpoint. Without this setting, write requests return `503`.

Plant creation uses `multipart/form-data`: include the complete plant JSON in the `plant` field and attach its required JPG or PNG in the `image` field. Bulk creation uses a JSON array in `plants` and repeats the `images` field in the same order, with at most 10 plants per request. The admin page resizes images for upload. Image data is stored in PostgreSQL's `plant_images` table, which is created automatically on the first image write; previously seeded entries without an uploaded image continue to use the site's catalog images. Image uploads are limited to 4 MB each by the API.

Create and full-replacement requests require these fields (without `id`): `image_slug`, `common_name`, `scientific_name`, `family`, `genus`, `plant_type`, `origin`, `habitat`, `lifespan`, `height_m`, `spread_m`, `sunlight`, `water_requirement`, `soil_type`, `flower_color`, `flowering_season`, `uses`, `toxicity`, and `description`. Partial updates accept any nonempty subset of those fields. Invalid values return `422`; a missing plant returns `404`; a conflicting database value returns `409`.

Send the admin key in the `X-API-Key` header. For example, a partial update can change only the common name while leaving every other field untouched:

```http
PATCH /api/v1/plants/1
X-API-Key: <PETALCORE_ADMIN_API_KEY>
Content-Type: application/json

{"common_name": "Garden Rose"}
```

## Phase 6: validation, errors, and security

Plant create and replacement requests use strict Pydantic validation. Text fields must be nonblank, `image_slug` must be lowercase letters/numbers separated by single hyphens, measurements must be finite positive numbers, and sunlight and water requirements must use the listed options. The API checks `common_name`, `scientific_name`, and `image_slug` against both the current catalog and the other entries in a bulk request, case-insensitively. PostgreSQL unique-constraint failures are also translated to `409` responses as a final safeguard.

Invalid or incomplete input returns `422`; unsupported image types return `415`; oversized uploads return `413`; missing records return `404`; duplicate catalog values return `409`; database connection/query failures return `503`; and unexpected failures return a generic server error. Error responses do not include database URLs, credentials, SQL, or stack traces. Pl@ntNet provider failures are converted to safe client messages.

Catalog list, detail, and search requests require an Index or Select client key. These client keys are intentionally public because browser clients receive them from `/config`; they are read-only and do not authorize catalog writes. Create, update, delete, image replacement, and the database diagnostic routes require `PETALCORE_ADMIN_API_KEY`. Missing admin configuration returns `503`, while a missing or incorrect key returns `401`. The admin page keeps the key in memory and never fetches it from a public config route. The health and client configuration routes, plus plant images used by the public library, remain public by design.

`DATABASE_URL`, `PETALCORE_ADMIN_API_KEY`, and `PLANTNET_API_KEY` are read from environment variables. Keep local values in `.env` (ignored by Git) and configure deployment values in the hosting platform's environment settings. The database connection uses TLS for remote PostgreSQL hosts unless `DATABASE_URL` already specifies an SSL mode; localhost connections remain usable for development. Do not use a database password as the API admin key.
