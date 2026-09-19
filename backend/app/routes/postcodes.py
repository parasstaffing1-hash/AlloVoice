import httpx
from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix="/api/postcodes", tags=["postcodes"])

POSTCODES_BASE_URL = "https://api.postcodes.io"


@router.get("/lookup/{postcode}")
async def lookup_postcode(postcode: str):
    """Lookup a UK postcode and get location data"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{POSTCODES_BASE_URL}/postcodes/{postcode.replace(' ', '')}")
        if response.status_code == 200:
            data = response.json()
            result = data.get("result", {})
            return {
                "postcode": result.get("postcode"),
                "latitude": result.get("latitude"),
                "longitude": result.get("longitude"),
                "region": result.get("region"),
                "admin_district": result.get("admin_district"),
                "admin_ward": result.get("admin_ward"),
                "country": result.get("country"),
            }
    return {"error": "Postcode not found"}


@router.get("/validate/{postcode}")
async def validate_postcode(postcode: str):
    """Validate a UK postcode format"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{POSTCODES_BASE_URL}/postcodes/{postcode.replace(' ', '')}/validate")
        if response.status_code == 200:
            return {"valid": response.json().get("result", False)}
    return {"valid": False}


@router.get("/autocomplete/{query}")
async def autocomplete_postcode(query: str):
    """Autocomplete UK postcode"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{POSTCODES_BASE_URL}/postcodes/{query}/autocomplete")
        if response.status_code == 200:
            return {"suggestions": response.json().get("result", [])}
    return {"suggestions": []}


@router.get("/nearest")
async def nearest_postcodes(
    latitude: float = Query(...),
    longitude: float = Query(...),
    limit: int = Query(5, ge=1, le=10)
):
    """Find nearest postcodes to a location"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POSTCODES_BASE_URL}/postcodes",
            params={"latitudes": [latitude], "longitudes": [longitude], "limit": limit}
        )
        if response.status_code == 200:
            results = response.json().get("result", [])
            if results and len(results) > 0:
                return {
                    "postcodes": [
                        {
                            "postcode": r.get("postcode"),
                            "distance": r.get("distance"),
                            "latitude": r.get("latitude"),
                            "longitude": r.get("longitude"),
                        }
                        for r in results[0].get("result", [])
                    ]
                }
    return {"postcodes": []}


@router.get("/bulk")
async def bulk_lookup(postcodes: list[str]):
    """Bulk lookup multiple postcodes"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{POSTCODES_BASE_URL}/postcodes",
            json={"postcodes": [p.replace(" ", "") for p in postcodes]}
        )
        if response.status_code == 200:
            results = response.json().get("result", [])
            return {
                "results": [
                    {
                        "query": r.get("query"),
                        "postcode": r.get("result", {}).get("postcode"),
                        "latitude": r.get("result", {}).get("latitude"),
                        "longitude": r.get("result", {}).get("longitude"),
                    }
                    for r in results
                ]
            }
    return {"results": []}
