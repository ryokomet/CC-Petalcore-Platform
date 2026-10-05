import hmac
import os
import warnings
from io import BytesIO
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool


# IDENTIFICATION CONFIGURATION
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.getenv("PETALCORE_ID_API_KEY", "petalcore-id-public-client")
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY", "")
PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
MAX_IMAGE_BYTES = 4_000_000
MAX_PIXELS = 25_000_000
Organ = Literal["auto", "leaf", "flower", "fruit", "bark"]

api_router = APIRouter(prefix="/api/v1", tags=["Plant Identification"])


# DATA MODELS
class PlantMatch(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    scientific_name: str = Field(min_length=1)
    common_names: list[str]
    family: str
    genus: str
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class IdentificationResponse(BaseModel):
    results: list[PlantMatch]
    count: int = Field(ge=0)
    organ: Organ
    provider: str = "Pl@ntNet"


# API KEY AUTHENTICATION
def verify_id_api_key(x_api_key: str | None = Header(default=None)):
    if (
        not API_KEY
        or not x_api_key
        or not hmac.compare_digest(x_api_key.encode(), API_KEY.encode())
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# IMAGE VALIDATION AND PREPARATION
def prepare_image(content: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise HTTPException(415, "Please upload a JPG or PNG photo.")
                if source.width * source.height > MAX_PIXELS:
                    raise HTTPException(
                        413,
                        "Photo dimensions are too large. Please resize it first.",
                    )
                source.verify()

            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((2048, 2048))
                output = BytesIO()
                # Re-encoding strips EXIF and GPS metadata before upload to Pl@ntNet.
                image.save(output, format="JPEG", quality=90)
                return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            422,
            "This photo could not be read. Please choose another JPG or PNG.",
        ) from None


# PL@NTNET REQUEST
async def request_identification(content: bytes, organ: Organ) -> dict:
    if not PLANTNET_API_KEY:
        raise HTTPException(
            503,
            "Plant identification is not configured yet. Please contact the site owner.",
        )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(35.0, connect=10.0)
        ) as client:
            response = await client.post(
                PLANTNET_URL,
                params={
                    "api-key": PLANTNET_API_KEY,
                    "lang": "en",
                    "nb-results": 5,
                },
                data={"organs": organ},
                files={"images": ("plant.jpg", content, "image/jpeg")},
            )
    except httpx.TimeoutException:
        raise HTTPException(
            504, "Identification took too long. Please try again."
        ) from None
    except httpx.RequestError:
        raise HTTPException(
            502,
            "The identification service could not be reached. Please try again.",
        ) from None

    if response.status_code == 404:
        return {"results": []}
    if response.status_code == 429:
        raise HTTPException(
            429,
            "The identification limit has been reached. Please try again later.",
        )
    if response.status_code in {401, 403}:
        raise HTTPException(
            503,
            "The identification service key needs attention. Please contact the site owner.",
        )
    if response.status_code in {400, 413, 415, 422}:
        raise HTTPException(
            422,
            "The identification service could not use this photo. Try a clearer JPG or PNG.",
        )
    if not response.is_success:
        raise HTTPException(
            502, "The identification service is temporarily unavailable."
        )

    try:
        return response.json()
    except ValueError:
        raise HTTPException(
            502,
            "The identification service returned an unreadable response.",
        ) from None


# IDENTIFY A PLANT
@api_router.post(
    "/identify",
    response_model=IdentificationResponse,
    dependencies=[Depends(verify_id_api_key)],
)
async def identify_plant(
    image: UploadFile = File(...),
    organ: Organ = Form("auto"),
):
    try:
        if image.content_type not in {"image/jpeg", "image/png"}:
            raise HTTPException(415, "Please upload a JPG or PNG photo.")

        content = await image.read(MAX_IMAGE_BYTES + 1)
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(
                413, "Photo is too large. Upload an image under 4 MB."
            )
        if not content:
            raise HTTPException(422, "The uploaded photo is empty.")

        prepared = await run_in_threadpool(prepare_image, content)
        payload = await request_identification(prepared, organ)

        try:
            matches = []
            for item in payload["results"][:5]:
                species = item["species"]
                matches.append(
                    PlantMatch(
                        scientific_name=species["scientificNameWithoutAuthor"],
                        common_names=species.get("commonNames", []),
                        family=species.get("family", {}).get(
                            "scientificNameWithoutAuthor", ""
                        ),
                        genus=species.get("genus", {}).get(
                            "scientificNameWithoutAuthor", ""
                        ),
                        score=item["score"],
                    )
                )
            matches.sort(key=lambda match: match.score, reverse=True)
        except (KeyError, TypeError, AttributeError, ValidationError):
            raise HTTPException(
                502,
                "The identification service returned incomplete results. Please try again.",
            ) from None

        return IdentificationResponse(
            results=matches,
            count=len(matches),
            organ=organ,
        )
    finally:
        await image.close()
