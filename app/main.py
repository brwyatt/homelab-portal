"""FastAPI application entrypoint and route definitions."""
from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import get_user_context, resolve_auth_url
from app.config import PortalConfig, load_config
from app.network import get_client_ip, resolve_location
from app.service_loader import get_accessible_services
from app.services.icon_service import IconService

app_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(app_dir / "templates"))

# Global config container
config: PortalConfig = PortalConfig()
icon_service: IconService = IconService()


def reload_configuration() -> PortalConfig:
    """Reload configuration from disk."""
    global config
    config = load_config()
    return config


# Initial load
_ = reload_configuration()

app = FastAPI(
    title=config.ui.title,
    description="A lightweight, secure, and fast homelab landing page",
    version="0.1.0",
)

# Mount static files
app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")


@app.get("/theme.css", response_class=Response)
async def serve_theme() -> Response:
    """Dynamically serve theme CSS based on configuration.
    Checks custom_themes_dir first, then built-in themes, falling back to default.css.
    """
    theme_name = config.ui.theme.strip() or "default"
    custom_dir = config.ui.custom_themes_dir

    css_path: Path | None = None

    # Check custom themes directory if configured
    if custom_dir:
        cand = Path(custom_dir) / f"{theme_name}.css"
        if cand.is_file():
            css_path = cand

    # Check built-in static themes
    if not css_path:
        cand = app_dir / "static" / "themes" / f"{theme_name}.css"
        if cand.is_file():
            css_path = cand

    # Fallback to default theme
    if not css_path:
        cand = app_dir / "static" / "themes" / "default.css"
        if cand.is_file():
            css_path = cand

    if not css_path or not css_path.is_file():
        raise HTTPException(status_code=404, detail="Theme stylesheet not found")

    content = css_path.read_text(encoding="utf-8")
    return Response(content=content, media_type="text/css")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Main dashboard rendering service cards filtered by network location and user groups."""
    client_ip = get_client_ip(request, config.network)
    location = resolve_location(client_ip, config)
    user = get_user_context(request, config.auth)
    categories = get_accessible_services(config, user, location)
    login_url = resolve_auth_url(config.auth.login_url, request) if config.auth.enabled else None
    logout_url = resolve_auth_url(config.auth.logout_url, request) if config.auth.enabled else None

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "config": config,
            "user": user,
            "location": location,
            "categories": categories,
            "login_url": login_url,
            "logout_url": logout_url,
        },
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    """Readiness probe."""
    return {"status": "ready"}


@app.get("/api/context")
async def api_context(request: Request) -> dict[str, object]:
    """Return JSON debugging/status info about the current client context."""
    client_ip = get_client_ip(request, config.network)
    location = resolve_location(client_ip, config)
    user = get_user_context(request, config.auth)

    return {
        "client_ip": client_ip,
        "location": {
            "network_class": location.network_class,
            "network_class_name": location.network_class_name,
            "subnet_cidr": location.subnet_cidr,
            "subnet_name": location.subnet_name,
        },
        "user": {
            "authenticated": user.authenticated,
            "username": user.username,
            "display_name": user.display_name,
            "groups": user.groups,
        },
    }


@app.get("/api/services")
async def api_services(request: Request) -> dict[str, object]:
    """Return JSON representation of accessible categories and services for client."""
    client_ip = get_client_ip(request, config.network)
    location = resolve_location(client_ip, config)
    user = get_user_context(request, config.auth)
    categories = get_accessible_services(config, user, location)

    return {
        "location": location.network_class,
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "order": c.order,
                "services": [
                    {
                        "name": s.name,
                        "url": s.url,
                        "description": s.description,
                        "icon": s.icon,
                        "target": s.target,
                        "public": s.public,
                    }
                    for s in c.services
                ],
            }
            for c in categories
        ],
    }


@app.api_route("/api/services/{service_id}/icon", methods=["GET", "HEAD"])
async def get_service_icon(service_id: str, request: Request) -> Response:
    """Fetch or serve cached favicon/icon for a service."""
    service = config.get_service_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    cached_icon = await icon_service.get_icon(service)
    if not cached_icon:
        raise HTTPException(status_code=404, detail="Icon not found")

    # ETag / 304 handling
    client_etag = request.headers.get("if-none-match")
    if client_etag and client_etag.strip('"') == cached_icon.etag:
        return Response(status_code=304, headers={"ETag": f'"{cached_icon.etag}"'})

    return Response(
        content=cached_icon.content,
        media_type=cached_icon.media_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{cached_icon.etag}"',
        },
    )
