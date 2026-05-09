"""ygo-ai — YGOPro Lua script development CLI (the "Hands" layer).

=== Architecture ===

Three-layer system for custom YGO card creation:

  Vault  (Brain)  → YGO Obsidian vault
                    Single source of truth for OCG rules, effect-writing standards,
                    Lua scripting knowledge, card designs.
                    Managed via obsidian-ygo MCP server.

  CLI    (Hands)  → This package. Stateless tools only:
                    - from-cdb : Browse/search .cdb card database (CDB lookup)
                    - diagnose : Static Lua script diagnostics (no AI)
                    - data     : Download official card data from community sources
                    Rules and AI logic belong in the Vault and Skills — NOT here.

  Skills (Nerves) → /YGO-Script: Full card generation workflow
                    /YGO-Desc:   Description polishing
                    These read rules dynamically from the Vault via MCP,
                    call CLI tools for data/diagnostics, and save output
                    back to the Vault (wiki/custom-cards/).

=== Maintenance Guide ===

When updating card effect rules, OCG terminology, or scripting patterns:
  → Edit the Vault (wiki/effect-writing/, wiki/scripting/, wiki/rules/)
  → Do NOT hardcode rules in this CLI or in the Skill files

When adding a new CLI command:
  → Add it here as a stateless tool (data in → result out)
  → Do NOT add AI generation logic — that belongs in Skills

When updating data download sources:
  → Edit ygo_ai/sources.py (DEFAULT_SOURCES) for default URLs
  → Users can override in ~/.ygo-ai/sources.json

Commands:
  from-cdb    Browse and search cards in a .cdb database
  diagnose    Run local Lua static diagnostics (no AI call)
  data        Download and manage official card data
"""

import json
import os
import sys
from pathlib import Path

import click

from .bridge import BridgeError, diagnose as _diagnose
from .card_utils import card_to_bridge_format, format_card_brief, format_diagnostics
from .cdb import count_cards, get_all_cards, read_card, search_cards
from .config import load_paths


# ── from-cdb ──────────────────────────────────────────────────────────


@click.command()
@click.option("--db-path", type=click.Path(exists=True),
              help="Path to .cdb file (uses config default if omitted)")
@click.option("--code", type=int, help="Card password/code for detailed view")
@click.option("--search", "search_term", type=str, help="Search cards by keyword")
@click.option("--json", "-j", "as_json", is_flag=True, default=False,
              help="Output results as JSON")
def from_cdb(db_path, code, search_term, as_json):
    """Browse and search cards in a .cdb database."""
    if not db_path:
        paths = load_paths()
        db_path = paths.default_db_path
    if not db_path:
        raise click.UsageError(
            "No CDB path provided. Set default_db_path in config.jsonc or use --db-path."
        )
    db_path = os.path.expanduser(db_path)
    if not Path(db_path).exists():
        raise click.UsageError(f"CDB file not found: {db_path}")

    # List all cards (first 50)
    if code is None and search_term is None:
        count = count_cards(db_path)
        cards = get_all_cards(db_path)
        click.echo(f"Database: {db_path} ({count} cards)")
        click.echo("---")
        for c in cards[:50]:
            click.echo(format_card_brief(c))
        if len(cards) > 50:
            click.echo(f"... and {len(cards) - 50} more. Use --code or --search to narrow down.")
        return

    # Search mode
    if code is None and search_term:
        cards = search_cards(db_path, search_term, limit=20)
        if as_json:
            click.echo(json.dumps(
                [card_to_bridge_format(c) for c in cards], ensure_ascii=False, indent=2
            ))
            return
        click.echo(f"Search results for '{search_term}' in {db_path}:")
        for c in cards:
            click.echo(format_card_brief(c))
        if not cards:
            click.echo("No cards found.")
        return

    # Single card detail view
    card = read_card(db_path, code)
    if card is None:
        click.echo(f"Card {code} not found in {db_path}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(card_to_bridge_format(card), ensure_ascii=False, indent=2))
        return

    click.echo(f"Code: {card['code']}")
    click.echo(f"Name: {card['name']}")
    click.echo(f"Type: 0x{card['type']:x}")
    click.echo(f"ATK: {card['attack']} / DEF: {card['defense']} / Level: {card['level']}")
    click.echo(f"Attribute: {card['attribute']} / Race: {card['race']}")
    click.echo(f"---")
    click.echo(f"Description:\n{card['desc']}")


# ── diagnose ──────────────────────────────────────────────────────────


@click.command()
@click.option("--script", "-s", type=click.Path(exists=True), required=True,
              help="Lua script to diagnose")
def diagnose(script):
    """Run local static diagnostics on a Lua script (no AI call)."""
    script_content = Path(script).read_text(encoding="utf-8")

    try:
        result = _diagnose(script_content)
    except BridgeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    diag = result.get("diagnostics", [])
    score = result.get("score", 0)
    if not diag:
        click.echo("No issues found.")
    else:
        click.echo(f"{len(diag)} issue(s) found (score: {score}):\n")
        click.echo(format_diagnostics(diag))


# ── data group ────────────────────────────────────────────────────────


VALID_TYPES = {"cdb", "strings", "banlist", "scripts", "pics", "all"}


@click.group()
def data():
    """Download and manage official card data.

    Fetches cards.cdb, strings.conf, lflist.conf, Lua scripts,
    and card images from community-maintained sources.
    """


@data.command()
@click.option(
    "--type", "data_type",
    type=click.Choice(list(VALID_TYPES)),
    default="all",
    help="Data type to download (default: all)",
)
@click.option(
    "--pics-source",
    type=str,
    default=None,
    help="Image source name (see 'ygo-ai data sources' for options)",
)
@click.option(
    "--cards-codes",
    type=str,
    default=None,
    help="Comma-separated card passcodes for image download (e.g. 89631139,10000)",
)
@click.option(
    "--from-cdb",
    is_flag=True,
    default=False,
    help="Download images for ALL cards in the local cards.cdb",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be downloaded without doing it",
)
def update(data_type, pics_source, cards_codes, from_cdb, dry_run):
    """Download/update card data from official sources."""
    from .download import download_all
    from .sources import get_data_dir, load_sources

    if dry_run:
        click.echo("Dry run — would download:")
        sources = load_sources()
        data_dir = get_data_dir()
        if data_type in ("cdb", "all"):
            click.echo(f"  cards.cdb  → {data_dir / 'data' / 'cards.cdb'}")
            click.echo(f"    from {sources['cdb']['url']}")
        if data_type in ("strings", "all"):
            click.echo(f"  strings.conf → {data_dir / 'data' / 'strings.conf'}")
            click.echo(f"    from {sources['strings']['url']}")
        if data_type in ("banlist", "all"):
            click.echo(f"  lflist.conf → {data_dir / 'data' / 'lflist.conf'}")
            click.echo(f"    from {sources['banlist']['url']}")
        if data_type in ("scripts", "all"):
            click.echo(f"  scripts/ → {data_dir / 'scripts' / ''}")
            click.echo(f"    from {sources['scripts']['url']}")
        if data_type in ("pics", "all"):
            click.echo(f"  pics/ → {data_dir / 'pics' / ''}")
            img_src = sources["images"][0]
            click.echo(f"    from {img_src['name']}: {img_src['url_template']}")
        return

    types = None if data_type == "all" else {data_type}
    pic_codes = None
    if cards_codes:
        pic_codes = [int(c.strip()) for c in cards_codes.split(",") if c.strip()]

    try:
        download_all(
            types=types,
            pic_codes=pic_codes,
            from_cdb=from_cdb,
            pics_source=pics_source,
        )
    except ImportError:
        raise click.UsageError(
            "The 'requests' library is required for downloads.\n"
            "Install it with: pip install requests"
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    click.echo("\nAll done. Use 'ygo-ai data info' to see current status.")


@data.command()
def info():
    """Show current data status."""
    from .sources import get_data_dir

    data_dir = get_data_dir()

    # cards.cdb
    cdb_path = data_dir / "data" / "cards.cdb"
    if cdb_path.exists():
        size_mb = cdb_path.stat().st_size / (1024 * 1024)
        try:
            card_count = count_cards(str(cdb_path))
        except Exception:
            card_count = "?"
        click.echo(f"cards.cdb:      {cdb_path}")
        click.echo(f"  Size: {size_mb:.1f} MB  Cards: {card_count}")
    else:
        click.echo(f"cards.cdb:      MISSING (run 'ygo-ai data update --type cdb')")

    # strings.conf
    strings_path = data_dir / "data" / "strings.conf"
    if strings_path.exists():
        size_kb = strings_path.stat().st_size / 1024
        click.echo(f"strings.conf:   {strings_path} ({size_kb:.1f} KB)")
    else:
        click.echo(f"strings.conf:   MISSING (run 'ygo-ai data update --type strings')")

    # lflist.conf
    banlist_path = data_dir / "data" / "lflist.conf"
    if banlist_path.exists():
        size_kb = banlist_path.stat().st_size / 1024
        click.echo(f"lflist.conf:    {banlist_path} ({size_kb:.1f} KB)")
    else:
        click.echo(f"lflist.conf:    MISSING (run 'ygo-ai data update --type banlist')")

    # scripts
    scripts_dir = data_dir / "scripts"
    if scripts_dir.exists():
        lua_count = sum(1 for _ in scripts_dir.rglob("*.lua"))
        click.echo(f"scripts/:       {scripts_dir} ({lua_count} Lua files)")
    else:
        click.echo(f"scripts/:       MISSING (run 'ygo-ai data update --type scripts')")

    # pics
    pics_dir = data_dir / "pics"
    if pics_dir.exists():
        jpg_count = sum(1 for _ in pics_dir.rglob("*.jpg"))
        total_size = sum(f.stat().st_size for f in pics_dir.rglob("*.jpg") if f.is_file())
        size_mb = total_size / (1024 * 1024)
        click.echo(f"pics/:          {pics_dir} ({jpg_count} images, {size_mb:.1f} MB)")
    else:
        click.echo(f"pics/:          MISSING (run 'ygo-ai data update --type pics')")


@data.command()
def sources():
    """List configured data sources."""
    from .sources import load_sources

    srcs = load_sources()

    click.echo("Text data sources (cdb / strings / banlist):")
    for key in ("cdb", "strings", "banlist"):
        s = srcs.get(key, {})
        click.echo(f"  {key}: {s.get('description', 'N/A')}")
        click.echo(f"    {s.get('url', 'N/A')}")

    click.echo(f"\nScript source:")
    s = srcs.get("scripts", {})
    click.echo(f"  {s.get('description', 'N/A')}")
    click.echo(f"  {s.get('url', 'N/A')}")

    click.echo(f"\nImage sources:")
    for i, src in enumerate(srcs.get("images", [])):
        marker = " (default)" if i == 0 else ""
        click.echo(f"  {src['name']}{marker}: {src.get('description', 'N/A')}")
        click.echo(f"    {src['url_template']}")

    click.echo(f"\nOverride sources by editing ~/.ygo-ai/sources.json")


# ── Main CLI group ────────────────────────────────────────────────────


@click.group()
@click.version_option(version="0.1.0")
def main():
    """ygo-ai — YGOPro Lua card script development CLI (the "Hands" layer).

    Local tools for browsing card databases and diagnosing Lua scripts.
    All AI-based generation is handled by YGO-Script / YGO-Desc skills.

    Architecture: Vault (Brain) → CLI (Hands) → Skills (Nerves)
    See module docstring or vault CLAUDE.md for full maintenance guide.

    Configuration: config.jsonc or environment variables.
    """


main.add_command(from_cdb)
main.add_command(diagnose)
main.add_command(data)


if __name__ == "__main__":
    main()
