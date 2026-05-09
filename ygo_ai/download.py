"""Data download logic for ygo-ai.

Handles downloading all 5 data types: cards.cdb, strings.conf, lflist.conf,
Lua scripts (git clone/pull), and card images.
"""

import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import click

from .sources import get_data_dir, get_image_source, load_sources


def _http_download(url: str, dest: Path, label: str) -> None:
    """Download a file via HTTP GET with a progress bar."""
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with click.progressbar(length=total, label=label) as bar:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    bar.update(len(chunk))


def _run_git(args: list[str], cwd: Path, label: str) -> None:
    """Run a git command, showing output on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            click.echo(f"{label}: git {' '.join(args)} failed:", err=True)
            click.echo(result.stderr or result.stdout, err=True)
    except FileNotFoundError:
        raise click.UsageError(
            "git is not installed. Please install git to download card scripts."
        )
    except subprocess.TimeoutExpired:
        click.echo(f"{label}: git {' '.join(args)} timed out after 5 minutes", err=True)


# ── Individual downloaders ──────────────────────────────────────────────


def download_cdb(sources: dict | None = None) -> Path:
    """Download cards.cdb and return its path."""
    if sources is None:
        sources = load_sources()
    data_dir = get_data_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "cards.cdb"
    url = sources["cdb"]["url"]
    _http_download(url, dest, "Downloading cards.cdb")
    _validate_cdb(dest)
    return dest


def download_strings(sources: dict | None = None) -> Path:
    """Download strings.conf and return its path."""
    if sources is None:
        sources = load_sources()
    data_dir = get_data_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "strings.conf"
    url = sources["strings"]["url"]
    _http_download(url, dest, "Downloading strings.conf")
    return dest


def download_banlist(sources: dict | None = None) -> Path:
    """Download lflist.conf and return its path."""
    if sources is None:
        sources = load_sources()
    data_dir = get_data_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / "lflist.conf"
    url = sources["banlist"]["url"]
    _http_download(url, dest, "Downloading lflist.conf")
    return dest


def download_scripts(sources: dict | None = None) -> Path:
    """Clone or pull Lua card scripts via git. Returns script dir path."""
    if sources is None:
        sources = load_sources()
    scripts_dir = get_data_dir() / "scripts"
    url = sources["scripts"]["url"]

    if (scripts_dir / ".git").exists():
        click.echo("Updating scripts (git pull)...")
        _run_git(["pull", "--ff-only"], cwd=scripts_dir, label="Scripts")
    else:
        click.echo(f"Cloning scripts from {url} ...")
        scripts_dir.mkdir(parents=True, exist_ok=True)
        _run_git(
            ["clone", "--depth", "1", url, str(scripts_dir)],
            cwd=scripts_dir.parent,
            label="Scripts",
        )
    return scripts_dir


def download_pics(
    card_codes: list[int],
    source_name: str | None = None,
    delay: float = 0.1,
) -> Path:
    """Download card images for specific card codes.

    Args:
        card_codes: List of card passcodes to download images for.
        source_name: Name of image source (see sources.json). None uses default.
        delay: Seconds to wait between requests (rate limiting).
    """
    img_src = get_image_source(source_name)
    pics_dir = get_data_dir() / "pics"
    pics_dir.mkdir(parents=True, exist_ok=True)

    url_template = img_src["url_template"]
    total = len(card_codes)
    downloaded = 0
    skipped = 0
    failed = 0

    label = f"Downloading images [{img_src['name']}]"
    with click.progressbar(card_codes, label=label) as bar:
        for code in bar:
            dest = pics_dir / f"{code}.jpg"
            if dest.exists():
                skipped += 1
                continue

            try:
                _http_download_image(url_template.format(id=code), dest)
                downloaded += 1
            except Exception:
                failed += 1

            if delay > 0:
                time.sleep(delay)

    if skipped:
        click.echo(f"  {skipped} already present, {downloaded} new, {failed} failed")
    else:
        click.echo(f"  {downloaded} downloaded, {failed} failed")
    return pics_dir


def _http_download_image(url: str, dest: Path) -> None:
    """Download a single image (no progress bar — used inside batch bar)."""
    import requests

    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    if "image" not in resp.headers.get("content-type", ""):
        raise ValueError(f"Not an image: {url}")
    dest.write_bytes(resp.content)


def _validate_cdb(path: Path) -> None:
    """Verify that a downloaded .cdb file is valid SQLite with expected tables."""
    if not path.exists():
        raise click.ClickException(f"Downloaded file not found: {path}")
    if path.stat().st_size < 1024:
        raise click.ClickException(
            f"Downloaded {path.name} is too small ({path.stat().st_size} bytes) — "
            "the file may be corrupted or the source may be unavailable."
        )
    try:
        conn = sqlite3.connect(str(path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        conn.close()
        table_names = {t[0] for t in tables}
        if "datas" not in table_names or "texts" not in table_names:
            raise click.ClickException(
                f"Downloaded {path.name} is missing required tables (datas/texts). "
                f"Found: {table_names}"
            )
    except sqlite3.DatabaseError as e:
        raise click.ClickException(f"Downloaded {path.name} is not a valid database: {e}")


# ── Bulk operations ─────────────────────────────────────────────────────


def get_card_codes_from_cdb(cdb_path: Path) -> list[int]:
    """Read all card passcodes from a local cards.cdb."""
    if not cdb_path.exists():
        raise click.ClickException(f"CDB not found: {cdb_path}. Run 'ygo-ai data update --type cdb' first.")
    conn = sqlite3.connect(str(cdb_path))
    try:
        rows = conn.execute("SELECT id FROM datas ORDER BY id").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def download_all(
    types: set[str] | None = None,
    pic_codes: list[int] | None = None,
    from_cdb: bool = False,
    pics_source: str | None = None,
) -> dict[str, Path | None]:
    """Download all specified data types. Returns paths to downloaded resources.

    Args:
        types: Set of types to download (cdb, strings, banlist, scripts, pics).
               None means all.
        pic_codes: Specific card codes for image download.
        from_cdb: If True, download images for all cards in local CDB.
        pics_source: Image source name override.
    """
    if types is None:
        types = {"cdb", "strings", "banlist", "scripts", "pics"}

    sources = load_sources()
    results: dict[str, Path | None] = {}

    if "cdb" in types:
        click.echo("── [1/5] Card database (cards.cdb) ──")
        results["cdb"] = download_cdb(sources)
        click.echo(f"  Done: {results['cdb']}")

    if "strings" in types:
        click.echo("── [2/5] Localization strings (strings.conf) ──")
        results["strings"] = download_strings(sources)
        click.echo(f"  Done: {results['strings']}")

    if "banlist" in types:
        click.echo("── [3/5] Banlist (lflist.conf) ──")
        results["banlist"] = download_banlist(sources)
        click.echo(f"  Done: {results['banlist']}")

    if "scripts" in types:
        click.echo("── [4/5] Card scripts (Lua) ──")
        results["scripts"] = download_scripts(sources)
        click.echo(f"  Done: {results['scripts']}")

    if "pics" in types:
        click.echo("── [5/5] Card images ──")
        if from_cdb:
            cdb_path = get_data_dir() / "data" / "cards.cdb"
            codes = get_card_codes_from_cdb(cdb_path)
            if not codes:
                click.echo("  No cards found in CDB. Run 'ygo-ai data update --type cdb' first.")
                results["pics"] = None
            else:
                click.echo(f"  Downloading images for {len(codes)} cards...")
                results["pics"] = download_pics(codes, source_name=pics_source)
        elif pic_codes:
            results["pics"] = download_pics(pic_codes, source_name=pics_source)
        else:
            click.echo(
                "  No cards specified. Use --cards-codes to download specific cards,\n"
                "  or --from-cdb to download images for all cards in the database."
            )
            results["pics"] = None

    return results
