import structlog
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User

logger = structlog.get_logger()
router = APIRouter(prefix="/gallery", tags=["gallery"])

_GIPHY_BASE = "https://api.giphy.com/v1"


def _stable_url(raw: str) -> str:
    """Strip expiring session params (?cid=...&rid=...) from Giphy CDN URLs."""
    return raw.split("?")[0] if "?" in raw else raw


def _map(items: list) -> list:
    results = []
    for item in items:
        media_id = item.get("id", "")
        if not media_id:
            continue
        images = item.get("images", {})
        original = images.get("original", {})
        preview  = images.get("fixed_height_downsampled", images.get("downsized", original))
        raw_url     = original.get("url", "")
        raw_preview = preview.get("url", raw_url)
        if not raw_url:
            continue
        results.append({
            "id":          media_id,
            "title":       item.get("title", ""),
            "url":         _stable_url(raw_url),
            "preview_url": _stable_url(raw_preview),
            "width":       int(original.get("width", 300)),
            "height":      int(original.get("height", 300)),
        })
    return results


async def _giphy_get(path: str, params: dict) -> list:
    if not settings.GIPHY_API_KEY:
        logger.warning("giphy_key_missing", hint="Set GIPHY_API_KEY in .env and restart")
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{_GIPHY_BASE}{path}", params={"api_key": settings.GIPHY_API_KEY, **params})
            r.raise_for_status()
        data = r.json().get("data", [])
        logger.info("giphy_ok", path=path, count=len(data))
        return data
    except httpx.HTTPStatusError as exc:
        logger.error("giphy_http_error", status=exc.response.status_code, body=exc.response.text[:200])
        raise HTTPException(status_code=502, detail=f"Giphy error {exc.response.status_code}")
    except Exception as exc:
        logger.error("giphy_request_failed", error=str(exc))
        raise HTTPException(status_code=502, detail="No se pudo conectar a Giphy")


# ── Stickers ──────────────────────────────────────────────────────────────────

@router.get("/stickers/trending")
async def trending_stickers(limit: int = Query(25, ge=1, le=50), _: User = Depends(get_current_user)):
    return {"results": _map(await _giphy_get("/stickers/trending", {"limit": limit, "rating": "g"}))}


@router.get("/stickers/search")
async def search_stickers(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=50), _: User = Depends(get_current_user)):
    return {"results": _map(await _giphy_get("/stickers/search", {"q": q, "limit": limit, "rating": "g"}))}


# ── GIFs ──────────────────────────────────────────────────────────────────────

@router.get("/gifs/trending")
async def trending_gifs(limit: int = Query(25, ge=1, le=50), _: User = Depends(get_current_user)):
    return {"results": _map(await _giphy_get("/gifs/trending", {"limit": limit, "rating": "g"}))}


@router.get("/gifs/search")
async def search_gifs(q: str = Query(..., min_length=1), limit: int = Query(25, ge=1, le=50), _: User = Depends(get_current_user)):
    return {"results": _map(await _giphy_get("/gifs/search", {"q": q, "limit": limit, "rating": "g"}))}
