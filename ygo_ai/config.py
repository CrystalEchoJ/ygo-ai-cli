"""Configuration management for ygo-ai CLI.

Priority: CLI args > environment variables > config file (config.jsonc)
"""

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class YGOProPaths:
    default_db_path: str = ""
    default_script_dir: str = ""
    default_pics_dir: str = ""


def _strip_jsonc_comments(text: str) -> str:
    """Strip // line comments and /* block comments */ from JSONC text."""
    # Remove block comments first
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Remove line comments (but not inside strings)
    lines = []
    for line in text.split("\n"):
        in_string = False
        result = []
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == '"' and (i == 0 or line[i-1] != "\\"):
                in_string = not in_string
                result.append(ch)
            elif ch == "/" and i + 1 < len(line) and line[i+1] == "/" and not in_string:
                break  # rest of line is comment
            else:
                result.append(ch)
            i += 1
        lines.append("".join(result))
    return "\n".join(lines)


def _default_config_path() -> Path:
    """Return the project-root config.jsonc path."""
    return Path(__file__).parent.parent / "config.jsonc"


def _load_jsonc(path: Path) -> dict:
    """Load and parse a JSONC file, returning dict. Returns {} on any error."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    clean = _strip_jsonc_comments(raw)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {}


def _user_config_path() -> Path:
    """Return the user-level config path (~/.ygo-ai/config.jsonc)."""
    return Path.home() / ".ygo-ai" / "config.jsonc"


def load_paths(path: Path | None = None) -> YGOProPaths:
    """Load YGOPro paths with three-tier priority:

    1. Environment variables (highest)
    2. ~/.ygo-ai/config.jsonc (user-level)
    3. <package>/config.jsonc (shipped default)

    Paths containing ~ are expanded to the user's home directory.
    """
    paths = YGOProPaths()
    p = path or _default_config_path()
    data = _load_jsonc(p)

    # Merge user-level config on top of defaults
    user_config = _load_jsonc(_user_config_path())
    for key in ("default_db_path", "default_script_dir", "default_pics_dir"):
        if key in user_config:
            data[key] = user_config[key]

    if "default_db_path" in data:
        paths.default_db_path = os.path.expanduser(data["default_db_path"])
    if "default_script_dir" in data:
        paths.default_script_dir = os.path.expanduser(data["default_script_dir"])
    if "default_pics_dir" in data:
        paths.default_pics_dir = os.path.expanduser(data["default_pics_dir"])

    if os.environ.get("YGO_AI_DB_PATH"):
        paths.default_db_path = os.path.expanduser(os.environ["YGO_AI_DB_PATH"])
    if os.environ.get("YGO_AI_SCRIPT_DIR"):
        paths.default_script_dir = os.path.expanduser(os.environ["YGO_AI_SCRIPT_DIR"])
    if os.environ.get("YGO_AI_PICS_DIR"):
        paths.default_pics_dir = os.path.expanduser(os.environ["YGO_AI_PICS_DIR"])

    return paths


def save_config(paths: YGOProPaths, path: Path | None = None) -> None:
    """Save paths config to file."""
    path = path or _default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "default_db_path": paths.default_db_path,
        "default_script_dir": paths.default_script_dir,
        "default_pics_dir": paths.default_pics_dir,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
