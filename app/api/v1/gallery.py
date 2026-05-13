import httpx
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/gallery", tags=["gallery"])

_GIPHY_BASE = "https://api.giphy.com/v1"


def _map(items: list) -> list:
    results = []
    for item in items:
        images = item.get("images", {})
        original = images.get("original", {})
        preview = images.get("fixed_height_downsampled", images.get("downsized", original))
        url = original.get("url", "")
        if not url:
            continue
        results.append({
            "id": item["id"],
            "title": item.get("title", ""),
            "url": url,
            "preview_url": preview.get("url", url),
            "width": int(original.get("width", 300)),
            "height": int(original.get("height", 300)),
        })
    return results


@router.get("/stickers/trending")
async def trending_stickers(
    limit: int = Query(25, ge=1, le=50),
    _: User = Depends(get_current_user),
):
    if not settings.GIPHY_API_KEY:
        return {"results": []}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_GIPHY_BASE}/stickers/trending",
            params={"api_key": settings.GIPHY_API_KEY, "limit": limit, "rating": "g"},
        )
        r.raise_for_status()
    return {"results": _map(r.json()["data"])}


@router.get("/stickers/search")
async def search_stickers(
    q: str = Query(..., min_length=1),
    limit: int = Query(25, ge=1, le=50),
    _: User = Depends(get_current_user),
):
    if not settings.GIPHY_API_KEY:
        return {"results": []}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{_GIPHY_BASE}/stickers/search",
            params={"api_key": settings.GIPHY_API_KEY, "q": q, "limit": limit, "rating": "g"},
        )
        r.raise_for_status()
    return {"results": _map(r.json()["data"])}
