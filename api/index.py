import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Path as APIPath,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from api.id_feature import (
    MAX_IMAGE_BYTES,
    api_router as id_api_router,
    prepare_image,
)
from api.plant_repository import (
    create_plants_with_images as insert_plants_with_images,
    find_duplicate_plant_fields as find_plant_duplicate_fields,
    find_plant as select_plant,
    get_plant_image,
    list_plants as select_plants,
    remove_plant as delete_plant,
    replace_plant_image,
    replace_plant as update_plant,
    search_plants as search_plant_records,
)
from api.select_feature import create_select_router
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# CONFIGURATION
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
SITES_DIR = PROJECT_DIR / "sites"
load_dotenv(PROJECT_DIR / ".env")

APP_TITLE = "Petalcore Shared API"
API_VERSION = "1.0"
API_PREFIX = "/api/v1"
APP_DESCRIPTION = "A beginner-friendly REST API containing information about plants."

# Browser-facing read keys are public client identifiers, not write credentials.
INDEX_API_KEY = os.getenv("PETALCORE_INDEX_API_KEY", "petalcore-index-public-client")
ID_API_KEY = os.getenv("PETALCORE_ID_API_KEY", "petalcore-id-public-client")
SELECT_API_KEY = os.getenv("PETALCORE_SELECT_API_KEY", "petalcore-select-public-client")
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY", "")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
allow_local_dev = os.getenv(
    "ALLOW_LOCAL_DEV", "false" if os.getenv("VERCEL") else "true"
).lower() == "true"
local_origin_regex = (
    r"http://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]+)?"
    if allow_local_dev
    else None
)

app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=API_VERSION
)

api_router = APIRouter(prefix=API_PREFIX, tags=["Plant Library"])


# REQUEST SIZE LIMIT
class UploadLimitMiddleware:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await self.application(scope, receive, send)

        messages = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 4_200_000:
                response = JSONResponse(
                    {"detail": "Photo is too large. Upload an image under 4 MB."},
                    status_code=413,
                )
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        message_iterator = iter(messages)

        async def replay_request():
            return next(
                message_iterator,
                {"type": "http.request", "body": b"", "more_body": False},
            )

        await self.application(scope, replay_request, send)


app.add_middleware(UploadLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=local_origin_regex,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["x-api-key", "Content-Type"],
)

# DATA MODELS
NonEmptyString = Annotated[str, Field(min_length=1)]
ImageSlug = Annotated[
    str,
    Field(min_length=1, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
]
PositiveMeasurement = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Sunlight = Literal[
    "Full Sun", "Partial Shade", "Full Sun to Partial Shade",
    "Low Light to Full Sun", "Bright Indirect Light"
]
WaterRequirement = Literal[
    "Low", "Moderate", "High", "Low to Moderate", "Moderate to High"
]


class PlantFields(BaseModel):
    """Validated plant fields shared by create and update requests."""

    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    image_slug: ImageSlug
    common_name: NonEmptyString
    scientific_name: NonEmptyString
    family: NonEmptyString
    genus: NonEmptyString
    plant_type: NonEmptyString
    origin: NonEmptyString
    habitat: NonEmptyString
    lifespan: NonEmptyString
    height_m: PositiveMeasurement
    spread_m: PositiveMeasurement
    sunlight: Sunlight
    water_requirement: WaterRequirement
    soil_type: NonEmptyString
    flower_color: NonEmptyString
    flowering_season: NonEmptyString
    uses: NonEmptyString
    toxicity: NonEmptyString
    description: NonEmptyString


class Plant(PlantFields):
    id: int = Field(gt=0)


class PlantCollection(BaseModel):
    count: int
    plants: list[Plant]


class PlantSearchResponse(BaseModel):
    query: str
    count: int
    results: list[Plant]


class PlantCreate(PlantFields):
    """A new plant record; the database assigns its id."""


class PlantUpdate(BaseModel):
    """Partial plant fields. Omitted fields stay unchanged; null is rejected."""

    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    image_slug: Optional[ImageSlug] = None
    common_name: Optional[NonEmptyString] = None
    scientific_name: Optional[NonEmptyString] = None
    family: Optional[NonEmptyString] = None
    genus: Optional[NonEmptyString] = None
    plant_type: Optional[NonEmptyString] = None
    origin: Optional[NonEmptyString] = None
    habitat: Optional[NonEmptyString] = None
    lifespan: Optional[NonEmptyString] = None
    height_m: Optional[PositiveMeasurement] = None
    spread_m: Optional[PositiveMeasurement] = None
    sunlight: Optional[Sunlight] = None
    water_requirement: Optional[WaterRequirement] = None
    soil_type: Optional[NonEmptyString] = None
    flower_color: Optional[NonEmptyString] = None
    flowering_season: Optional[NonEmptyString] = None
    uses: Optional[NonEmptyString] = None
    toxicity: Optional[NonEmptyString] = None
    description: Optional[NonEmptyString] = None

    @model_validator(mode="after")
    def require_non_null_changes(self) -> "PlantUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one plant field must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Plant fields cannot be null.")
        return self


def _plant_response(row):
    """Return only the public plant fields with API-friendly numeric types."""
    values = {field: row[field] for field in Plant.model_fields}
    values["height_m"] = float(values["height_m"])
    values["spread_m"] = float(values["spread_m"])
    return Plant.model_validate(values)


def _load_plant_catalog():
    try:
        return [_plant_response(row).model_dump() for row in select_plants()]
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="The plant database is unavailable.",
        ) from None


select_api_router = create_select_router(_load_plant_catalog)
# API KEY AUTHENTICATION
def verify_api_key(x_api_key: Optional[str] = Header(default=None)):
    # Index and Select may read shared catalog routes using their own client keys.
    valid_keys = (INDEX_API_KEY, SELECT_API_KEY)
    if not x_api_key or not any(
        key and hmac.compare_digest(x_api_key.encode(), key.encode())
        for key in valid_keys
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key."
        )
    return True


def verify_admin_api_key(x_api_key: Optional[str] = Header(default=None)):
    """Protect catalog writes with a secret that is never sent to site clients."""
    expected_key = os.getenv("PETALCORE_ADMIN_API_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Plant management is not configured.",
        )
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode(), expected_key.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin API key.",
        )
    return True


@api_router.get(
    "/admin/session",
    include_in_schema=False,
    dependencies=[Depends(verify_admin_api_key)],
)
def check_admin_session():
    return {"authenticated": True}


def _integrity_conflict_detail(exc: IntegrityError) -> str:
    """Translate common PostgreSQL constraint failures without exposing internals."""
    original = getattr(exc, "orig", None)
    sqlstate = (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )
    diagnostic = getattr(original, "diag", None)
    constraint = (getattr(diagnostic, "constraint_name", None) or "").lower()
    column = (getattr(diagnostic, "column_name", None) or "").lower()

    if sqlstate == "23505":
        field_labels = {
            "common_name": "common name",
            "scientific_name": "scientific name",
            "image_slug": "image slug",
        }
        for field, label in field_labels.items():
            if column == field or field in constraint:
                return f"A plant with that {label} already exists. Choose a different value."

        if constraint.endswith("plants_pkey") or "plants_id_key" in constraint:
            return "The database generated an ID that is already in use. The plant ID sequence needs repair."

        return (
            "A value that must be unique is already in use. Check the common name, "
            "scientific name, and image slug."
        )

    return "The plant conflicts with an existing database record."


def _database_call(operation):
    """Translate database failures into safe API responses."""
    try:
        return operation()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=_integrity_conflict_detail(exc),
        ) from None
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="The plant database could not complete the request.",
        ) from None
    except KeyError as exc:
        if exc.args == ("DATABASE_URL",):
            raise HTTPException(
                status_code=503,
                detail="The plant database is not configured.",
            ) from None
        raise HTTPException(
            status_code=500,
            detail="The request could not be completed.",
        ) from None
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="The request could not be completed.",
        ) from None


def _validate_plant_uniqueness(
    records: list[dict],
    exclude_plant_id: int | None = None,
) -> None:
    """Reject duplicate catalog names/slugs before an insert consumes an ID."""
    labels = {
        "common_name": "common name",
        "scientific_name": "scientific name",
        "image_slug": "image slug",
    }
    seen: dict[tuple[str, str], int] = {}
    for index, record in enumerate(records, start=1):
        for field, label in labels.items():
            value = record.get(field)
            if value is None:
                continue
            key = (field, str(value).strip().casefold())
            previous_index = seen.get(key)
            if previous_index is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Entries {previous_index} and {index} use the same {label}.",
                )
            seen[key] = index

    duplicate_fields = _database_call(
        lambda: find_plant_duplicate_fields(records, exclude_plant_id)
    )
    for field, label in labels.items():
        if field in duplicate_fields:
            raise HTTPException(
                status_code=409,
                detail=f"A plant with that {label} already exists. Choose a different value.",
            )
def _parse_plant_json(payload: str) -> PlantCreate:
    try:
        return PlantCreate.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=exc.errors(include_url=False),
        ) from None


async def _prepare_uploaded_plant_image(image: UploadFile) -> bytes:
    try:
        if image.content_type not in {"image/jpeg", "image/png"}:
            raise HTTPException(415, "Choose a JPG or PNG image.")

        content = await image.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Each image must be under 4 MB.")
        if not content:
            raise HTTPException(422, "The selected image is empty.")
        return await run_in_threadpool(prepare_image, content)
    finally:
        await image.close()


# HOME
@app.get("/")
def home():
    return FileResponse(SITES_DIR / "home.html")


@app.get("/auth-config", include_in_schema=False)
def auth_client_config():
    """Expose only the Supabase project URL and public anon key to the browser."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not supabase_url or not supabase_anon_key:
        raise HTTPException(status_code=503, detail="Account services are not configured.")
    return JSONResponse(
        {"supabase_url": supabase_url, "supabase_anon_key": supabase_anon_key},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/config", include_in_schema=False)
def id_client_config():
    return JSONResponse(
        {
            "api_url": os.getenv("PUBLIC_API_BASE_URL", API_PREFIX),
            "api_key": ID_API_KEY,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/config/{client}", include_in_schema=False)
def client_config(client: str):
    client_keys = {
        "index": INDEX_API_KEY,
        "id": ID_API_KEY,
        "select": SELECT_API_KEY,
    }
    if client not in client_keys:
        raise HTTPException(status_code=404, detail="Unknown Petalcore client.")

    return JSONResponse(
        {
            "api_url": os.getenv("PUBLIC_API_BASE_URL", API_PREFIX),
            "api_key": client_keys[client],
        },
        headers={"Cache-Control": "no-store"},
    )


# HEALTH CHECK (Public)
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": APP_TITLE,
        "version": API_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "identification_configured": bool(PLANTNET_API_KEY),
    }


# GET ALL PLANTS (Protected)
@api_router.get(
    "/plants",
    response_model=PlantCollection,
    dependencies=[Depends(verify_api_key)],
)
def get_plants():
    plants = _database_call(
        lambda: [_plant_response(row).model_dump() for row in select_plants()]
    )
    return {
        "count": len(plants),
        "plants": plants,
    }

# SEARCH PLANTS (Protected)
@api_router.get(
    "/plants/search",
    response_model=PlantSearchResponse,
    dependencies=[Depends(verify_api_key)],
)
def search_plants(q: str = Query(..., min_length=1, max_length=100)):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=422, detail="Search text cannot be empty.")
    normalized_query = q.lower()
    results = _database_call(
        lambda: [
            _plant_response(row).model_dump()
            for row in search_plant_records(q)
        ]
    )
    return {
        "query": normalized_query,
        "count": len(results),
        "results": results,
    }

# GET ONE PLANT (Protected)
@api_router.get(
    "/plants/{plant_id}",
    response_model=Plant,
    dependencies=[Depends(verify_api_key)],
)
def get_plant(plant_id: int = APIPath(gt=0)):
    row = _database_call(lambda: select_plant(plant_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    return _database_call(lambda: _plant_response(row))


# GET PLANT IMAGE (Public so Index can load it in an img element)
@api_router.get(
    "/plants/{plant_id}/image",
    response_class=Response,
    responses={
        200: {
            "content": {
                "image/jpeg": {
                    "schema": {"type": "string", "format": "binary"},
                }
            }
        },
        404: {"description": "Plant image not found."},
    },
)
def get_plant_image_route(plant_id: int = APIPath(gt=0)):
    image = _database_call(lambda: get_plant_image(plant_id))
    if image is None:
        raise HTTPException(status_code=404, detail="Plant image not found.")
    content, content_type = image
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


# CREATE PLANT (Admin protected)
@api_router.post(
    "/plants",
    status_code=201,
    response_model=Plant,
    dependencies=[Depends(verify_admin_api_key)],
)
async def create_plant(plant: str = Form(...), image: UploadFile = File(...)):
    try:
        record = _parse_plant_json(plant)
        _validate_plant_uniqueness([record.model_dump()])
        image_data = await _prepare_uploaded_plant_image(image)
        rows = _database_call(
            lambda: insert_plants_with_images([(record.model_dump(), image_data)])
        )
        return _database_call(lambda: _plant_response(rows[0]))
    finally:
        await image.close()


# CREATE MULTIPLE PLANTS (Admin protected)
@api_router.post(
    "/plants/bulk",
    status_code=201,
    response_model=PlantCollection,
    dependencies=[Depends(verify_admin_api_key)],
)
async def create_plants_bulk(plants: str = Form(...), images: list[UploadFile] = File(...)):
    try:
        try:
            submitted_plants = json.loads(plants)
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=422, detail="Plant entries must be a JSON array.") from None

        if not isinstance(submitted_plants, list) or not submitted_plants:
            raise HTTPException(status_code=422, detail="Add at least one plant entry.")
        if len(submitted_plants) > 10:
            raise HTTPException(status_code=422, detail="Add no more than 10 plants per batch.")
        if len(images) != len(submitted_plants):
            raise HTTPException(
                status_code=422,
                detail="Choose exactly one image for each plant, in the same order.",
            )

        try:
            records = [PlantCreate.model_validate(item) for item in submitted_plants]
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=exc.errors(include_url=False),
            ) from None

        _validate_plant_uniqueness([record.model_dump() for record in records])

        prepared_records = []
        for record, image in zip(records, images):
            image_data = await _prepare_uploaded_plant_image(image)
            prepared_records.append((record.model_dump(), image_data))

        rows = _database_call(lambda: insert_plants_with_images(prepared_records))
        response_plants = _database_call(
            lambda: [_plant_response(row).model_dump() for row in rows]
        )
        return {"count": len(response_plants), "plants": response_plants}
    finally:
        for image in images:
            await image.close()


# REPLACE A PLANT IMAGE (Admin protected)
@api_router.put(
    "/plants/{plant_id}/image",
    dependencies=[Depends(verify_admin_api_key)],
)
async def put_plant_image(plant_id: int = APIPath(gt=0), image: UploadFile = File(...)):
    try:
        image_data = await _prepare_uploaded_plant_image(image)
        updated = _database_call(lambda: replace_plant_image(plant_id, image_data))
        if not updated:
            raise HTTPException(status_code=404, detail="Plant not found.")
        return {"image_updated": True, "plant_id": plant_id}
    finally:
        await image.close()


# REPLACE PLANT (Admin protected)
@api_router.put(
    "/plants/{plant_id}",
    response_model=Plant,
    dependencies=[Depends(verify_admin_api_key)],
)
def put_plant(plant_id: Annotated[int, APIPath(gt=0)], plant: PlantCreate):
    if _database_call(lambda: select_plant(plant_id)) is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    _validate_plant_uniqueness([plant.model_dump()], exclude_plant_id=plant_id)
    row = _database_call(lambda: update_plant(plant_id, plant.model_dump()))
    if row is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    return _database_call(lambda: _plant_response(row))


# PARTIALLY UPDATE PLANT (Admin protected)
@api_router.patch(
    "/plants/{plant_id}",
    response_model=Plant,
    dependencies=[Depends(verify_admin_api_key)],
)
def patch_plant(plant_id: Annotated[int, APIPath(gt=0)], plant: PlantUpdate):
    if _database_call(lambda: select_plant(plant_id)) is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    changes = plant.model_dump(exclude_unset=True)
    _validate_plant_uniqueness([changes], exclude_plant_id=plant_id)
    row = _database_call(lambda: update_plant(plant_id, changes))
    if row is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    return _database_call(lambda: _plant_response(row))


# DELETE PLANT (Admin protected)
@api_router.delete(
    "/plants/{plant_id}",
    dependencies=[Depends(verify_admin_api_key)],
)
def remove_plant(plant_id: Annotated[int, APIPath(gt=0)]):
    deleted_id = _database_call(lambda: delete_plant(plant_id))
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Plant not found.")
    return {"deleted": True, "id": deleted_id}


app.include_router(api_router)
app.include_router(id_api_router)
app.include_router(select_api_router)

# FRONTEND SITES
app.mount(
    "/index",
    StaticFiles(directory=SITES_DIR / "index", html=True),
    name="petalcore-index",
)
app.mount(
    "/id",
    StaticFiles(directory=SITES_DIR / "id", html=True),
    name="petalcore-id",
)
app.mount(
    "/select",
    StaticFiles(directory=SITES_DIR / "select", html=True),
    name="petalcore-select",
)
app.mount(
    "/account",
    StaticFiles(directory=SITES_DIR / "account", html=True),
    name="petalcore-account",
)
app.mount(
    "/admin",
    StaticFiles(directory=SITES_DIR / "admin", html=True),
    name="petalcore-admin",
)

# DATABASE CONNECTIVITY CHECK (Phase 4, step 6-7)
@app.get(
    "/db-test",
    include_in_schema=False,
    dependencies=[Depends(verify_admin_api_key)],
)
def db_test():
    try:
        from api.database import engine

        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar_one()
        return {"database": "connected", "result": result}
    except Exception as exc:
        # Only the exception class is returned, never the URL or password.
        return JSONResponse(
            {"database": "error", "error_type": type(exc).__name__},
            status_code=503,
        )


# INITIAL DATA RETRIEVAL (Phase 4, step 8)
@app.get(
    "/db-plants",
    include_in_schema=False,
    dependencies=[Depends(verify_admin_api_key)],
)
def db_plants():
    try:
        from api.database import engine

        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id, common_name, scientific_name FROM plants ORDER BY id LIMIT 5")
            ).mappings().all()
        return {"count": len(rows), "plants": [dict(r) for r in rows]}
    except Exception as exc:
        return JSONResponse(
            {"database": "error", "error_type": type(exc).__name__},
            status_code=503,
        )
