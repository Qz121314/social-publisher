from fastapi import APIRouter

from app.services.ixbrowser import IXBrowserService

router = APIRouter()


@router.get("/status")
def status() -> dict[str, object]:
    ix = IXBrowserService()
    return {
        "app": "ok",
        "ixbrowser": ix.connection_status(),
    }


@router.get("/ixbrowser/profiles")
def ixbrowser_profiles() -> dict[str, object]:
    ix = IXBrowserService()
    profiles = ix.get_profiles()
    return {"items": profiles, "count": len(profiles)}
