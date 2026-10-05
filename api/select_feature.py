"""Recommendation API for Petalcore Select."""

import os
from collections.abc import Callable, Sequence
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SettingPreference = Literal["indoors", "outdoors", "either"]
LightPreference = Literal["bright", "partial", "low", "any"]
CarePreference = Literal["occasional", "steady", "attentive", "any"]
PlantInterest = Literal["flowers", "foliage", "herbs", "surprise"]


class SelectPreferences(BaseModel):
    """Validated preferences submitted by the Petalcore Select client."""

    model_config = ConfigDict(extra="forbid")

    setting: SettingPreference = "either"
    light: LightPreference = "any"
    care: CarePreference = "any"
    interests: list[PlantInterest] = Field(default_factory=list, max_length=4)

    @field_validator("interests")
    @classmethod
    def interests_must_be_unique(cls, interests: list[PlantInterest]) -> list[PlantInterest]:
        if len(interests) != len(set(interests)):
            raise ValueError("Choose each plant interest only once.")
        return interests

    @model_validator(mode="after")
    def require_at_least_one_preference(self) -> "SelectPreferences":
        has_filter = (
            self.setting != "either"
            or self.light != "any"
            or self.care != "any"
            or bool(self.interests)
        )
        if not has_filter:
            raise ValueError("Choose at least one preference or select “Surprise me.”")
        return self


def verify_select_api_key(
    x_api_key: Optional[str] = Header(default=None),
) -> bool:
    """Allow the recommendation route to be called only with Select's client key."""
    expected_key = os.getenv(
        "PETALCORE_SELECT_API_KEY",
        "petalcore-select-public-client",
    )
    if not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Petalcore Select is not configured.",
        )
    if not x_api_key or x_api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing Petalcore Select API key.",
        )
    return True


_LIGHT_SCORES = {
    "bright": {
        "Full Sun": 1.0,
        "Full Sun to Partial Shade": 0.9,
        "Bright Indirect Light": 0.85,
        "Low Light to Full Sun": 0.8,
        "Partial Shade": 0.55,
    },
    "partial": {
        "Partial Shade": 1.0,
        "Full Sun to Partial Shade": 0.95,
        "Bright Indirect Light": 0.9,
        "Low Light to Full Sun": 0.85,
        "Full Sun": 0.55,
    },
    "low": {
        "Low Light to Full Sun": 1.0,
        "Bright Indirect Light": 0.8,
        "Partial Shade": 0.7,
        "Full Sun to Partial Shade": 0.5,
        "Full Sun": 0.25,
    },
}

_WATER_SCORES = {
    "occasional": {
        "Low": 1.0,
        "Low to Moderate": 0.9,
        "Moderate": 0.6,
        "Moderate to High": 0.35,
        "High": 0.2,
    },
    "steady": {
        "Moderate": 1.0,
        "Low to Moderate": 0.9,
        "Moderate to High": 0.85,
        "Low": 0.7,
        "High": 0.6,
    },
    "attentive": {
        "High": 1.0,
        "Moderate to High": 0.95,
        "Moderate": 0.75,
        "Low to Moderate": 0.55,
        "Low": 0.35,
    },
}

_INTEREST_LABELS = {
    "flowers": "flowering plants",
    "foliage": "leafy plants",
    "herbs": "herbs and edible plants",
}


def _setting_score(plant: dict[str, Any], setting: SettingPreference) -> float:
    """Estimate setting fit from catalog traits; the source data has no setting field."""
    plant_type = str(plant.get("plant_type", "")).lower()
    habitat = str(plant.get("habitat", "")).lower()
    sunlight = str(plant.get("sunlight", ""))
    height = float(plant.get("height_m", 0) or 0)

    if setting == "indoors":
        score = 0.55
        if any(term in plant_type for term in ("succulent", "orchid", "herbaceous", "carnivorous")):
            score += 0.2
        if "Indirect Light" in sunlight or "Low Light" in sunlight:
            score += 0.2
        if height <= 2.5:
            score += 0.05
        if any(term in plant_type for term in ("tree", "palm", "grass")):
            score -= 0.35
        return max(0.1, min(score, 1.0))

    cultivated_habitat_terms = (
        "garden", "field", "farm", "cultivated", "plantation",
        "grassland", "rocky slope", "coastal",
    )
    score = 0.6
    if any(term in habitat for term in cultivated_habitat_terms):
        score = 0.9
    if any(term in plant_type for term in ("tree", "palm", "grass", "annual herb")):
        score = max(score, 0.82)
    if "Bright Indirect Light" in sunlight:
        score -= 0.12
    return max(0.2, min(score, 1.0))


def _interest_score(plant: dict[str, Any], interest: str) -> float:
    plant_type = str(plant.get("plant_type", "")).lower()
    uses = str(plant.get("uses", "")).lower()
    common_name = str(plant.get("common_name", "")).lower()

    if interest == "flowers":
        flower_color = str(plant.get("flower_color", "")).lower()
        flowering_season = str(plant.get("flowering_season", "")).lower()
        has_flower_details = (
            flower_color not in {"", "none", "not applicable"}
            or flowering_season not in {"", "none", "not applicable"}
        )
        return 0.95 if has_flower_details else 0.25

    if interest == "foliage":
        foliage_types = (
            "evergreen", "succulent", "grass", "palm", "orchid",
            "herbaceous", "carnivorous",
        )
        return 0.95 if any(term in plant_type for term in foliage_types) else 0.6

    if interest == "herbs":
        if "herb" in plant_type:
            return 1.0
        if any(term in uses for term in ("culinary", "edible", "spice", "seasoning", "tea")):
            return 0.9
        if any(term in uses or term in common_name for term in ("medicinal", "traditional")):
            return 0.65
        return 0.15

    return 0.0


def _score_plant(
    plant: dict[str, Any],
    preferences: SelectPreferences,
) -> tuple[float, list[str]]:
    weighted_scores: list[tuple[float, float]] = []
    reasons: list[str] = []

    if preferences.setting != "either":
        score = _setting_score(plant, preferences.setting)
        weighted_scores.append((score, 20))
        setting_label = "indoor" if preferences.setting == "indoors" else "outdoor"
        if score >= 0.7:
            reasons.append(f"Catalog traits suggest a good fit for an {setting_label} setting.")
        elif score >= 0.5:
            reasons.append(f"Could suit an {setting_label} setting depending on your conditions.")

    if preferences.light != "any":
        light_score = _LIGHT_SCORES[preferences.light].get(plant["sunlight"], 0.0)
        weighted_scores.append((light_score, 30))
        if light_score >= 0.7:
            reasons.append(f"Light needs: {plant['sunlight']}.")

    if preferences.care != "any":
        water_score = _WATER_SCORES[preferences.care].get(
            plant["water_requirement"],
            0.0,
        )
        weighted_scores.append((water_score, 30))
        if water_score >= 0.7:
            reasons.append(f"Watering needs: {plant['water_requirement']}.")

    selected_interests = [
        interest for interest in preferences.interests if interest != "surprise"
    ]
    if selected_interests:
        interest_scores = [
            (interest, _interest_score(plant, interest))
            for interest in selected_interests
        ]
        best_interest_score = max(score for _, score in interest_scores)
        weighted_scores.append((best_interest_score, 20))
        for interest, score in interest_scores:
            if score >= 0.7:
                reasons.append(f"Matches your interest in {_INTEREST_LABELS[interest]}.")

    if not weighted_scores:
        # "Surprise me" returns a varied starter list with a small preference for
        # plants that need less frequent watering and stay more compact.
        water_score = _WATER_SCORES["occasional"].get(
            plant["water_requirement"],
            0.5,
        )
        height_score = 1.0 if float(plant.get("height_m", 0) or 0) <= 2.5 else 0.55
        weighted_scores = [(water_score * 0.7 + height_score * 0.3, 1)]
        reasons.append("A starter suggestion from the current plant collection.")

    total_weight = sum(weight for _, weight in weighted_scores)
    match_score = sum(score * weight for score, weight in weighted_scores) / total_weight
    if not reasons:
        reasons.append("A possible match from the current plant collection.")

    return round(match_score * 100), reasons


def create_select_router(
    get_plant_catalog: Callable[[], Sequence[dict[str, Any]]],
) -> APIRouter:
    """Create Select routes with access to the shared app's validated catalog."""
    router = APIRouter(prefix="/api/v1", tags=["Petalcore Select"])

    @router.post(
        "/recommendations",
        dependencies=[Depends(verify_select_api_key)],
    )
    def recommend_plants(preferences: SelectPreferences) -> dict[str, Any]:
        ranked_plants = []
        for plant in get_plant_catalog():
            match_score, match_reasons = _score_plant(plant, preferences)
            ranked_plants.append(
                {
                    **plant,
                    "match_score": match_score,
                    "match_reasons": match_reasons,
                }
            )

        ranked_plants.sort(
            key=lambda item: (-item["match_score"], item["common_name"].lower())
        )
        results = ranked_plants[:5]

        return {
            "count": len(results),
            "preferences": preferences.model_dump(),
            "results": results,
            "notes": [
                "Match scores are estimates based on the details in Petalcore's plant catalog.",
                "Indoor and outdoor fit is inferred from plant type, size, habitat, and light; confirm growing needs for your specific space.",
            ],
        }

    return router
