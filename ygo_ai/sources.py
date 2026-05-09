"""Data source registry for ygo-ai.

Defines default download sources for all 5 data types and supports
per-user overrides via ~/.ygo-ai/sources.json.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImageSource:
    name: str
    url_template: str
    description: str = ""


DEFAULT_SOURCES: dict[str, Any] = {
    "cdb": {
        "url": "https://raw.githubusercontent.com/moecube/ygopro-database/master/locales/zh-CN/cards.cdb",
        "description": "Chinese card database (moecube/ygopro-database)",
    },
    "strings": {
        "url": "https://raw.githubusercontent.com/moecube/ygopro-database/master/locales/zh-CN/strings.conf",
        "description": "Chinese localization strings",
    },
    "banlist": {
        "url": "https://raw.githubusercontent.com/Fluorohydride/ygopro/master/lflist.conf",
        "description": "Forbidden/Limited list (Fluorohydride/ygopro)",
    },
    "scripts": {
        "url": "https://github.com/ProjectIgnis/CardScripts.git",
        "description": "Official card Lua scripts (ProjectIgnis/CardScripts)",
    },
    "images": [
        {
            "name": "momobako",
            "url_template": "https://cdn.233.momobako.com/ygopro/pics/{id}.jpg",
            "description": "Chinese card art (MyCard CDN)",
        },
        {
            "name": "ygoprodeck",
            "url_template": "https://images.ygoprodeck.com/images/cards/{id}.jpg",
            "description": "English card art (YGOPRODECK)",
        },
    ],
}


def get_data_dir() -> Path:
    """Return the ygo-ai data directory (~/.ygo-ai), creating it if needed."""
    data_dir = Path.home() / ".ygo-ai"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_sources_path() -> Path:
    """Return path to sources.json."""
    return get_data_dir() / "sources.json"


def load_sources() -> dict[str, Any]:
    """Load data sources, merging defaults with user overrides from sources.json."""
    sources = DEFAULT_SOURCES.copy()
    sources_path = get_sources_path()
    if sources_path.exists():
        try:
            user_data = json.loads(sources_path.read_text(encoding="utf-8"))
            # Merge user image sources with defaults
            if "images" in user_data:
                sources["images"] = user_data["images"]
            # Allow overriding URLs for cdb/strings/banlist/scripts
            for key in ("cdb", "strings", "banlist", "scripts"):
                if key in user_data:
                    sources[key] = user_data[key]
        except (json.JSONDecodeError, OSError):
            pass
    return sources


def save_sources(sources: dict[str, Any]) -> None:
    """Save data sources to sources.json."""
    sources_path = get_sources_path()
    sources_path.write_text(
        json.dumps(sources, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_image_source(name: str | None = None) -> dict[str, Any]:
    """Get a specific image source by name, or the first one if not specified."""
    sources = load_sources()
    images = sources.get("images", [])
    if not images:
        raise ValueError("No image sources configured")
    if name:
        for src in images:
            if src["name"] == name:
                return src
        raise ValueError(f"Image source '{name}' not found. Available: {[s['name'] for s in images]}")
    return images[0]


def list_image_sources() -> list[dict[str, Any]]:
    """List all configured image sources."""
    sources = load_sources()
    return sources.get("images", [])
