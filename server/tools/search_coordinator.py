"""Coordinate Yelp and Google Maps tools for venue search."""
from __future__ import annotations

from typing import List, Sequence

from server.state.models import LocationConstraint, SearchResult
from server.tools.maps_tool import validate_and_rank_venues
from server.tools.yelp_tool import search_yelp_candidates


def _normalize_constraints(
    constraints: Sequence[LocationConstraint | dict],
) -> List[LocationConstraint]:
    normalized: List[LocationConstraint] = []
    for constraint in constraints:
        if isinstance(constraint, LocationConstraint):
            normalized.append(constraint)
            continue
        member = constraint.get("member")
        location = constraint.get("location")
        max_distance = constraint.get("max_distance_mins", 30)
        if not member or not location:
            continue
        normalized.append(
            LocationConstraint(
                member=member,
                location=location,
                max_distance_mins=int(max_distance),
            )
        )
    return normalized


async def find_venues(
    cuisine: str,
    location_constraints: Sequence[LocationConstraint | dict],
    dietary_filters: List[str],
) -> SearchResult:
    """Search Yelp and validate against Google Maps constraints."""

    normalized_constraints = _normalize_constraints(location_constraints)
    if not normalized_constraints:
        return SearchResult(venues=[], constraints_met=False, conflict_reason="No location constraints provided")

    anchor_location = normalized_constraints[0].location
    candidates = await search_yelp_candidates(cuisine, anchor_location, dietary_filters, limit=20)
    if not candidates:
        cuisine_label = cuisine or ""
        cuisine_phrase = f"{cuisine_label} " if cuisine_label else ""
        reason = f"No {cuisine_phrase.strip() or 'restaurant'} restaurants found in {anchor_location}"
        return SearchResult(venues=[], constraints_met=False, conflict_reason=reason)

    result = await validate_and_rank_venues(candidates, normalized_constraints)
    if len(result.venues) > 5:
        result.venues = result.venues[:5]
    return result
