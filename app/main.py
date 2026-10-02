"""FastAPI application entrypoint and route definitions."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import get_user_context
from app.config import PortalConfig, find_config_file, load_config
from app.network import get_client_ip, resolve_location
from app.service_loader import get_accessible_services

app_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(app_dir / "templates"))

# Global config container
config: PortalConfig = PortalConfig()


def reload_configuration() -> PortalConfig:
    """Reload configuration from disk."""
    global config
    config = load_config()
    return config


# Initial load
reload_configuration()

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

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "config": config,
            "user": user,
            "location": location,
            "categories": categories,
        },
    )


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> Dict[str, str]:
    """Readiness probe."""
    return {"status": "ready"}


@app.get("/api/context")
async def api_context(request: Request) -> Dict[str, Any]:
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
async def api_services(request: Request) -> Dict[str, Any]:
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
