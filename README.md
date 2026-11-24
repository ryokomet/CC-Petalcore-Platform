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

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/plants` | List plants ordered by ID. |
| `GET` | `/api/v1/plants/{plant_id}` | Read one plant. |
| `GET` | `/api/v1/plants/search?q=rose` | Search common and scientific names. |
| `POST` | `/api/v1/plants` | Create a plant; the database assigns its ID. |
| `PUT` | `/api/v1/plants/{plant_id}` | Replace all editable fields. |
| `PATCH` | `/api/v1/plants/{plant_id}` | Update only the submitted fields. |
| `DELETE` | `/api/v1/plants/{plant_id}` | Delete a plant. |

Read requests continue to use the Index or Select client API key. Write requests require the separate `PETALCORE_ADMIN_API_KEY` environment variable. Configure it alongside `DATABASE_URL` in the API deployment environment and redeploy. Keep the admin key on the server or in a trusted administrative client; do not put it in a website's JavaScript or expose it through a public config endpoint. Without this setting, write requests return `503`.

Create and full-replacement requests require these fields (without `id`): `image_slug`, `common_name`, `scientific_name`, `family`, `genus`, `plant_type`, `origin`, `habitat`, `lifespan`, `height_m`, `spread_m`, `sunlight`, `water_requirement`, `soil_type`, `flower_color`, `flowering_season`, `uses`, `toxicity`, and `description`. Partial updates accept any nonempty subset of those fields. Invalid values return `422`; a missing plant returns `404`; a conflicting database value returns `409`.

Send the admin key in the `X-API-Key` header. For example, a partial update can change only the common name while leaving every other field untouched:

```http
PATCH /api/v1/plants/1
X-API-Key: <PETALCORE_ADMIN_API_KEY>
Content-Type: application/json

{"common_name": "Garden Rose"}
```
