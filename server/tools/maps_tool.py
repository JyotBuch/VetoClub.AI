"""Google Maps utilities for LetsPlanIt."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from server.state.models import LocationConstraint, SearchResult, VenueOption

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def _format_address(business: Dict[str, Any]) -> str:
    location = business.get("location") or {}
    display = location.get("display_address")
    if isinstance(display, list) and display:
        return ", ".join(display)
    return location.get("address1") or ""


def _extract_coordinates(business: Dict[str, Any]) -> Dict[str, float]:
    coords = business.get("coordinates") or {}
    lat = coords.get("latitude") or coords.get("lat")
    lng = coords.get("longitude") or coords.get("lng")
    if lat is None or lng is None:
        return {}
    try:
        return {"lat": float(lat), "lng": float(lng)}
    except (TypeError, ValueError):
        return {}


def _has_category(business: Dict[str, Any], keyword: str) -> bool:
    categories = business.get("categories") or []
    needle = keyword.lower()
    for category in categories:
        alias = (category.get("alias") or "").lower()
        title = (category.get("title") or "").lower()
        if needle in {alias, title}:
            return True
    return False


async def geocode_location(location: str) -> Optional[Tuple[float, float]]:
    """Convert a location string to (lat, lng)."""

    if not location or not GOOGLE_MAPS_API_KEY:
        return None

    params = {"address": location, "key": GOOGLE_MAPS_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(GEOCODE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    results = payload.get("results") or []
    if not results:
        return None
    geometry = results[0].get("geometry", {}).get("location") or {}
    lat = geometry.get("lat")
    lng = geometry.get("lng")
    if lat is None or lng is None:
        return None
    try:
        return float(lat), float(lng)
    except (TypeError, ValueError):
        return None


async def get_travel_times(
    origin_coords: Tuple[float, float],
    destination_addresses: Sequence[str],
    mode: str = "driving",
) -> List[Optional[int]]:
    """Return list of travel times in minutes for each destination."""

    if not destination_addresses:
        return []
    if not GOOGLE_MAPS_API_KEY:
        return [None for _ in destination_addresses]

    params = {
        "origins": f"{origin_coords[0]},{origin_coords[1]}",
        "destinations": "|".join(destination_addresses),
        "mode": mode,
        "key": GOOGLE_MAPS_API_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(DISTANCE_MATRIX_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return [None for _ in destination_addresses]

    rows = payload.get("rows") or []
    if not rows:
        return [None for _ in destination_addresses]

    elements = rows[0].get("elements") or []
    durations: List[Optional[int]] = []
    for index in range(len(destination_addresses)):
        if index >= len(elements):
            durations.append(None)
            continue
        element = elements[index]
        if element.get("status") != "OK":
            durations.append(None)
            continue
        duration_value = element.get("duration", {}).get("value")
        if duration_value is None:
            durations.append(None)
            continue
        durations.append(int(round(duration_value / 60)))
    return durations


def estimate_uber_fare(
    distance_meters: float,
    duration_mins: float,
    budget_cap: Optional[int] = None,
) -> Dict[str, Optional[bool] | Optional[int] | str]:
    """Estimate Uber fare from Google Maps distance/duration data."""

    distance_miles = distance_meters / 1609.34 if distance_meters else 0.0
    low = round(2.50 + (distance_miles * 1.50) + (duration_mins * 0.25))
    high = round(2.50 + (distance_miles * 1.80) + (duration_mins * 0.35))
    within_budget: Optional[bool] = None
    if budget_cap is not None:
        within_budget = low <= budget_cap

    return {
        "low": low,
        "high": high,
        "currency": "USD",
        "within_budget": within_budget,
        "budget_cap": budget_cap,
        "message": f"~${low}–${high}",
        "note": "Estimate based on distance. Actual fare may vary.",
    }


async def validate_and_rank_venues(
    candidates: List[Dict[str, Any]],
    location_constraints: List[LocationConstraint],
) -> SearchResult:
    """Validate Yelp candidates against all constraints and return top options."""

    if not location_constraints:
        return SearchResult(venues=[], constraints_met=False, conflict_reason="No location constraints provided")

    try:
        constraint_coords: Dict[str, Tuple[float, float]] = {}
        for constraint in location_constraints:
            coords = await geocode_location(constraint.location)
            if coords is None:
                return SearchResult(venues=[], constraints_met=False, conflict_reason="Maps API unavailable")
            constraint_coords[constraint.member] = coords

        if len(location_constraints) > 1:
            for i, first in enumerate(location_constraints):
                first_coords = constraint_coords[first.member]
                for j in range(i + 1, len(location_constraints)):
                    second = location_constraints[j]
                    second_coords = constraint_coords[second.member]
                    durations = await get_travel_times(first_coords, [f"{second_coords[0]},{second_coords[1]}"])
                    minutes = durations[0] if durations else None
                    if minutes and minutes > 45:
                        reason = (
                            f"{first.member}'s location ({first.location}) and {second.member}'s location ({second.location}) "
                            "are too far apart — no venue can satisfy both constraints."
                        )
                        return SearchResult(
                            venues=[],
                            constraints_met=False,
                            conflict_reason=reason,
                            compromised_constraints=[first.member, second.member],
                        )

        if not candidates:
            return SearchResult(venues=[], constraints_met=False, conflict_reason="No candidates to evaluate")

        destination_addresses = [_format_address(candidate) for candidate in candidates]
        constraint_travel_times: Dict[str, List[Optional[int]]] = {}
        for constraint in location_constraints:
            coords = constraint_coords[constraint.member]
            durations = await get_travel_times(coords, destination_addresses)
            if len(durations) != len(destination_addresses):
                return SearchResult(venues=[], constraints_met=False, conflict_reason="Maps API unavailable")
            constraint_travel_times[constraint.member] = durations

        primary_member = location_constraints[0].member

        def _filter_with_limits(limits: Dict[str, int], compromised: Optional[List[str]] = None) -> SearchResult:
            valid: List[VenueOption] = []
            for idx, candidate in enumerate(candidates):
                meets_all = True
                for constraint in location_constraints:
                    duration = constraint_travel_times[constraint.member][idx]
                    if duration is None or duration > limits[constraint.member]:
                        meets_all = False
                        break
                if not meets_all:
                    continue
                distance_primary = constraint_travel_times[primary_member][idx]
                if distance_primary is None:
                    continue
                valid.append(
                    VenueOption(
                        name=candidate.get("name", "Unknown"),
                        address=_format_address(candidate),
                        rating=float(candidate.get("rating") or 0.0),
                        price=candidate.get("price") or "",
                        distance_mins=distance_primary,
                        yelp_url=candidate.get("url") or "",
                        coordinates=_extract_coordinates(candidate),
                        vegetarian_friendly=_has_category(candidate, "vegetarian"),
                        vegan_friendly=_has_category(candidate, "vegan"),
                    )
                )

            valid.sort(key=lambda option: option.rating, reverse=True)
            if not valid:
                return SearchResult(
                    venues=[],
                    constraints_met=False,
                    conflict_reason=None,
                    compromised_constraints=list(compromised or []),
                )
            constraints_met = compromised is None or not compromised
            return SearchResult(
                venues=valid[:5],
                constraints_met=constraints_met,
                compromised_constraints=list(compromised or []),
            )

        base_limits = {constraint.member: constraint.max_distance_mins for constraint in location_constraints}
        result = _filter_with_limits(base_limits)
        if result.venues:
            return result

        # Relax the widest constraint by +10 mins and retry once
        widest = max(location_constraints, key=lambda c: c.max_distance_mins)
        relaxed_limits = base_limits.copy()
        relaxed_limits[widest.member] += 10
        relaxed_result = _filter_with_limits(relaxed_limits, compromised=[widest.member])
        if relaxed_result.venues:
            relaxed_result.constraints_met = False
            return relaxed_result

        relaxed_result.conflict_reason = "No venues satisfied the location constraints."
        return relaxed_result

    except Exception:
        return SearchResult(venues=[], constraints_met=False, conflict_reason="Maps API unavailable")
