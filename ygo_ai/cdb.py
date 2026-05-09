"""CDB file reader/writer using Python sqlite3 stdlib.

CDB format (SQLite):
  datas(id, ot, alias, setcode, type, atk, def, level, race, attribute, category)
  texts(id, name, desc, str1..str16)
"""

import sqlite3
from pathlib import Path
from typing import Any


def _connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"CDB file not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def read_card(db_path: str | Path, code: int) -> dict[str, Any] | None:
    """Read a single card by password/code."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT d.*, t.name, t.desc, "
            "t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8, "
            "t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16 "
            "FROM datas d LEFT JOIN texts t ON d.id = t.id WHERE d.id = ?",
            (code,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_card(row)
    finally:
        conn.close()


def search_cards(db_path: str | Path, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search cards by keyword in name or description."""
    conn = _connect(db_path)
    try:
        pattern = f"%{keyword}%"
        rows = conn.execute(
            "SELECT d.*, t.name, t.desc, "
            "t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8, "
            "t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16 "
            "FROM datas d LEFT JOIN texts t ON d.id = t.id "
            "WHERE t.name LIKE ? OR t.desc LIKE ? "
            "ORDER BY d.id LIMIT ?",
            (pattern, pattern, limit)
        ).fetchall()
        return [_row_to_card(r) for r in rows]
    finally:
        conn.close()


def get_all_cards(db_path: str | Path) -> list[dict[str, Any]]:
    """Get all cards from a CDB file."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT d.*, t.name, t.desc, "
            "t.str1, t.str2, t.str3, t.str4, t.str5, t.str6, t.str7, t.str8, "
            "t.str9, t.str10, t.str11, t.str12, t.str13, t.str14, t.str15, t.str16 "
            "FROM datas d LEFT JOIN texts t ON d.id = t.id "
            "ORDER BY d.id"
        ).fetchall()
        return [_row_to_card(r) for r in rows]
    finally:
        conn.close()


def write_card(db_path: str | Path, card: dict[str, Any]) -> None:
    """Write or update a card in the CDB file."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO datas(id, ot, alias, setcode, type, atk, def, level, race, attribute, category) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card["code"], card.get("ot", 0), card.get("alias", 0),
                _pack_setcode(card.get("setcode", [0, 0, 0, 0])),
                card.get("type", 0), card.get("attack", 0), card.get("defense", 0),
                card.get("level", 0), card.get("race", 0), card.get("attribute", 0),
                card.get("category", 0),
            )
        )
        conn.execute(
            "INSERT OR REPLACE INTO texts(id, name, desc, str1, str2, str3, str4, str5, str6, str7, str8, "
            "str9, str10, str11, str12, str13, str14, str15, str16) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                card["code"], card.get("name", ""), card.get("desc", ""),
                *_pack_strings(card.get("strings", [])),
            )
        )
        conn.commit()
    finally:
        conn.close()


def delete_card(db_path: str | Path, code: int) -> bool:
    """Delete a card by code. Returns True if deleted."""
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM datas WHERE id = ?", (code,))
        conn.execute("DELETE FROM texts WHERE id = ?", (code,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def count_cards(db_path: str | Path) -> int:
    """Count total cards in CDB."""
    conn = _connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM datas").fetchone()[0]
    finally:
        conn.close()


def find_reference_scripts(
    db_path: str | Path, card: dict[str, Any], script_dir: str | None = None
) -> list[dict[str, Any]]:
    """Find reference Lua scripts for similar cards in the same CDB.

    Strategy:
    1. Search by card name keywords
    2. Search by effect description keywords
    3. Read script/c{code}.lua files
    """
    results: list[dict] = []
    seen_codes: set[int] = set()
    current_code = int(card.get("code", 0))
    if current_code > 0:
        seen_codes.add(current_code)

    db_dir = Path(db_path).parent
    script_dir_path = Path(script_dir) if script_dir else db_dir / "script"

    # Strategy 1: name keyword search
    name = str(card.get("name", "")).strip()
    if name:
        keywords = [w for w in name.replace("・", " ").replace("／", " ").split() if len(w) >= 2]
        search_term = keywords[0] if keywords else name[:4]
        for c in search_cards(db_path, search_term, limit=6):
            code = int(c.get("code", 0))
            if code <= 0 or code in seen_codes:
                continue
            if not c.get("desc"):
                continue
            seen_codes.add(code)
            script = _read_script_file(script_dir_path, code)
            if script:
                results.append({"code": code, "name": c["name"], "script": script})
            if len(results) >= 2:
                break

    # Strategy 2: effect keyword search
    if len(results) < 2:
        desc = str(card.get("desc", "")).strip()
        import re
        effect_kw = re.search(
            r"(特殊召喚|破壊|除外|墓地|ドロー|無効|Special Summon|destroy|negate|draw|banish)",
            desc, re.IGNORECASE
        )
        fallback = effect_kw.group(0) if effect_kw else ""
        if fallback:
            for c in search_cards(db_path, fallback, limit=6):
                code = int(c.get("code", 0))
                if code <= 0 or code in seen_codes:
                    continue
                if not c.get("desc"):
                    continue
                seen_codes.add(code)
                script = _read_script_file(script_dir_path, code)
                if script:
                    results.append({"code": code, "name": c["name"], "script": script})
                if len(results) >= 2:
                    break

    return results


def _read_script_file(script_dir: Path, code: int) -> str | None:
    """Read a Lua script file for a card code, searching subdirectories."""
    filename = f"c{code}.lua"
    # Search in script_dir and all immediate subdirectories
    candidates = [script_dir / filename]
    if script_dir.exists():
        for child in script_dir.iterdir():
            if child.is_dir():
                candidates.append(child / filename)
    for script_path in candidates:
        if script_path.exists():
            content = script_path.read_text(encoding="utf-8", errors="replace")
            return content[:3000] + ("\n-- [truncated]" if len(content) > 3000 else "")
    return None


def _row_to_card(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a database row to a card dict."""
    return {
        "code": row["id"],
        "alias": row["alias"],
        "name": row["name"] or "",
        "desc": row["desc"] or "",
        "ot": row["ot"],
        "type": row["type"],
        "attribute": row["attribute"],
        "race": row["race"],
        "attack": row["atk"],
        "defense": row["def"],
        "level": row["level"],
        "lscale": 0,  # not directly in CDB — stored in setcode or type-derived
        "rscale": 0,
        "linkMarker": 0,
        "setcode": _unpack_setcode(row["setcode"]),
        "category": row["category"],
        "strings": [row[f"str{i}"] or "" for i in range(1, 17)],
    }


def _unpack_setcode(raw: int) -> list[int]:
    """Unpack 64-bit setcode into 4 16-bit values."""
    return [
        raw & 0xFFFF,
        (raw >> 16) & 0xFFFF,
        (raw >> 32) & 0xFFFF,
        (raw >> 48) & 0xFFFF,
    ]


def _pack_setcode(values: list[int]) -> int:
    """Pack 4 16-bit setcode values into a 64-bit integer."""
    result = 0
    for i, v in enumerate(values[:4]):
        result |= (v & 0xFFFF) << (i * 16)
    return result


def _pack_strings(values: list[str]) -> list[str]:
    """Ensure strings list has exactly 16 elements."""
    result = list(values[:16])
    while len(result) < 16:
        result.append("")
    return result
