"""Card data utilities — serialization for the bridge protocol."""

from typing import Any


ATTRIBUTE_MAP: dict[str, int] = {
    "earth": 1, "water": 2, "fire": 4, "wind": 8,
    "light": 16, "dark": 32, "divine": 64,
}
ATTRIBUTE_NAMES: dict[int, str] = {v: k for k, v in ATTRIBUTE_MAP.items()}

RACE_MAP: dict[str, int] = {
    "warrior": 1, "spellcaster": 2, "fairy": 4, "fiend": 8, "zombie": 16,
    "machine": 32, "aqua": 64, "pyro": 128, "rock": 256, "wingedbeast": 512,
    "plant": 1024, "insect": 2048, "thunder": 4096, "dragon": 8192,
    "beast": 16384, "beastwarrior": 32768, "dinosaur": 65536,
    "fish": 131072, "seaserpent": 262144, "reptile": 524288,
    "psychic": 1048576, "divinebeast": 2097152, "creatorgod": 4194304,
    "wyrm": 8388608, "cyberse": 16777216, "illusion": 33554432,
}
RACE_NAMES: dict[int, str] = {v: k for k, v in RACE_MAP.items()}

SUBTYPE_MAP: dict[str, int] = {
    "normal": 0x10, "effect": 0x20, "fusion": 0x40, "ritual": 0x80,
    "spirit": 0x200, "union": 0x400, "gemini": 0x800, "tuner": 0x1000,
    "synchro": 0x2000, "token": 0x4000, "quickplay": 0x10000,
    "continuous": 0x20000, "equip": 0x40000, "field": 0x80000,
    "counter": 0x100000, "flip": 0x200000, "toon": 0x400000,
    "xyz": 0x800000, "pendulum": 0x1000000, "spssummon": 0x2000000,
    "link": 0x4000000, "ritual_spell": 0x8000000,
}

MAIN_TYPE_MAP: dict[str, int] = {"monster": 0x1, "spell": 0x2, "trap": 0x4}

LINK_MARKER_MAP: dict[str, int] = {
    "downleft": 1, "down": 2, "downright": 4,
    "left": 8, "right": 32,
    "upleft": 64, "up": 128, "upright": 256,
}


def card_to_bridge_format(card: dict[str, Any]) -> dict[str, Any]:
    """Convert a CDB card dict to the bridge protocol format (snake_case)."""
    return {
        "code": int(card.get("code", 0)),
        "alias": int(card.get("alias", 0)),
        "name": str(card.get("name", "")),
        "desc": str(card.get("desc", "")),
        "ot": int(card.get("ot", 0)),
        "type": int(card.get("type", 0)),
        "attribute": int(card.get("attribute", 0)),
        "race": int(card.get("race", 0)),
        "attack": int(card.get("attack", 0)),
        "defense": int(card.get("defense", 0)),
        "level": int(card.get("level", 0)),
        "lscale": int(card.get("lscale", 0)),
        "rscale": int(card.get("rscale", 0)),
        "linkMarker": int(card.get("linkMarker", 0)),
        "setcode": list(card.get("setcode", [0, 0, 0, 0])),
        "category": int(card.get("category", 0)),
        "strings": list(card.get("strings", [])),
    }


def build_card_from_args(
    name: str | None = None,
    desc: str | None = None,
    type_: int | None = None,
    main_type: str | None = None,
    subtypes: tuple[str, ...] | None = None,
    attribute: str | None = None,
    race: str | None = None,
    level: int | None = None,
    atk: int | None = None,
    def_: int | None = None,
    lscale: int | None = None,
    rscale: int | None = None,
    link_markers: tuple[str, ...] | None = None,
    setcode: tuple[str, ...] | None = None,
    code: int = 0,
    alias: int = 0,
    ot: int = 0,
) -> dict[str, Any]:
    """Build a card dict from CLI arguments."""
    card: dict[str, Any] = {
        "code": code, "alias": alias, "name": name or "", "desc": desc or "",
        "ot": ot, "type": type_ or 0, "attribute": 0, "race": 0,
        "attack": atk or 0, "defense": def_ or 0, "level": level or 0,
        "lscale": lscale or 0, "rscale": rscale or 0,
        "linkMarker": 0, "setcode": [0, 0, 0, 0], "category": 0, "strings": [],
    }

    # Resolve main_type + subtypes → type bitmask
    if main_type and type_ is None:
        bits = MAIN_TYPE_MAP.get(main_type.lower(), 0)
        for sub in (subtypes or []):
            bits |= SUBTYPE_MAP.get(sub.lower().replace("-", "").replace(" ", ""), 0)
        if bits:
            card["type"] = bits

    # Resolve string attribute → number
    if attribute:
        card["attribute"] = ATTRIBUTE_MAP.get(attribute.lower().replace(" ", ""), 0)

    # Resolve string race → number
    if race:
        card["race"] = RACE_MAP.get(race.lower().replace(" ", ""), 0)

    # Resolve link markers
    if link_markers:
        card["linkMarker"] = sum(
            LINK_MARKER_MAP.get(m.lower(), 0) for m in link_markers
        )

    # Resolve setcodes (hex strings like "0x00a1")
    if setcode:
        codes = []
        for s in setcode[:4]:
            try:
                codes.append(int(s, 16) if s.startswith("0x") else int(s))
            except ValueError:
                codes.append(0)
        card["setcode"] = codes + [0] * (4 - len(codes))

    return card


def format_diagnostics(diagnostics: list[dict]) -> str:
    """Format diagnostics for terminal output."""
    if not diagnostics:
        return "No issues found."

    lines = []
    for d in diagnostics:
        icon = "❌" if d.get("severity") == "error" else "⚠️"
        loc = f"L{d.get('startLineNumber', '?')}:{d.get('startColumn', '?')}"
        lines.append(f"  {icon} [{d.get('severity', '?').upper()}] {loc}  {d.get('message', '')}")
    return "\n".join(lines)


def format_card_brief(card: dict[str, Any]) -> str:
    """Format a card as a one-line summary."""
    code = card.get("code", 0)
    name = card.get("name", "Unknown")
    atk = card.get("attack", 0)
    def_ = card.get("defense", 0)
    level = card.get("level", 0)
    attr = ATTRIBUTE_NAMES.get(card.get("attribute", 0), "?")
    race = RACE_NAMES.get(card.get("race", 0), "?")
    return f"[{code}] {name} | {attr}/{race} | Lv{level} | ATK {atk} / DEF {def_}"
