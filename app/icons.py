"""Feather icon utilities, aliases, and normalization."""
from __future__ import annotations

import re

# Common synonym aliases to Feather icon names
ICON_ALIASES: dict[str, str] = {
    "house": "home",
    "network": "share-2",
    "dashboard": "layout",
    "metrics": "activity",
    "stats": "bar-chart-2",
    "auth": "lock",
    "identity": "user-check",
    "security": "shield",
    "storage": "hard-drive",
    "dns": "globe",
    "gear": "settings",
    "gears": "settings",
    "terminal": "terminal",
    "console": "terminal",
    "log": "file-text",
    "logs": "file-text",
}


def normalize_icon_name(name: str | None) -> str:
    """Normalize an icon name:
    - Strips whitespace and lowercases.
    - Strips 'feather:' or 'feather-' prefixes.
    - Strips '.svg' suffix.
    - Replaces underscores with dashes.
    - Resolves alias mapping.
    """
    if not name:
        return ""

    raw = str(name).strip().lower()
    raw = re.sub(r"^(feather[:\-_]|lucide[:\-_])", "", raw)
    if raw.endswith(".svg"):
        raw = raw[:-4]

    raw = re.sub(r"[\s_]+", "-", raw)
    raw = re.sub(r"[^a-z0-9\-]", "", raw)
    raw = raw.strip("-")

    return ICON_ALIASES.get(raw, raw)
