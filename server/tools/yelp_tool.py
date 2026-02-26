"""Yelp Fusion search helper for LetsPlanIt."""
from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

YELP_API_KEY = os.getenv("YELP_API_KEY")
YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"


def _build_attributes(dietary_filters: List[str]) -> str:
    mapping: Dict[str, str] = {
        "vegetarian": "vegetarian_friendly",
        "vegan": "vegan_friendly",
        "halal": "halal",
    }
    attrs = {mapping[flt.lower()] for flt in dietary_filters if flt.lower() in mapping}
    return ",".join(sorted(attrs)) if attrs else ""


async def search_yelp_candidates(
    cuisine: str,
    location: str,
    dietary_filters: List[str],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Call Yelp Fusion API and return raw business dictionaries."""

    if not YELP_API_KEY or not location:
        return []

    cuisine_term = (cuisine or "").strip()
    term = f"{cuisine_term} restaurant".strip()
    headers = {"Authorization": f"Bearer {YELP_API_KEY}"}
    params = {"term": term or "restaurant", "location": location, "limit": limit}
    attributes = _build_attributes(dietary_filters)
    if attributes:
        params["attributes"] = attributes

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(YELP_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    businesses = payload.get("businesses")
    if not isinstance(businesses, list):
        return []
    return businesses
