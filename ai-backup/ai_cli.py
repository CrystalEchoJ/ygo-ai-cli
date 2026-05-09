"""Standalone AI generation CLI — NOT used by YGO-Script/YGO-Desc skills.

Usage:
  python -m ai-backup.ai_cli generate --name "Card" --desc "Effect..."
  python -m ai-backup.ai_cli parse "卡名：..."
  python -m ai-backup.ai_cli repair -s script.lua
  python -m ai-backup.ai_cli batch --db-path cards.cdb -i "add HOPT"
"""

import json
import sys
from pathlib import Path

import click

# Import from the main ygo_ai package
sys.path.insert(0, str(Path(__file__).parent.parent))

from ygo_ai.bridge import (  # noqa: E402
    AIConfig,
    BridgeError,
    batch_edit,
    generate as _generate,
    parse_manuscript,
    repair as _repair,
)
from ygo_ai.card_utils import (  # noqa: E402
    ATTRIBUTE_MAP,
    LINK_MARKER_MAP,
    MAIN_TYPE_MAP,
    RACE_MAP,
    SUBTYPE_MAP,
    build_card_from_args,
    card_to_bridge_format,
    format_card_brief,
    format_diagnostics,
)
from ygo_ai.cdb import (  # noqa: E402
    count_cards,
    find_reference_scripts,
    get_all_cards,
    read_card,
    search_cards,
)
from ygo_ai.config import load_paths  # noqa: E402

AI_CONFIG_PATH = Path(__file__).parent / "ai_config.jsonc"


def _load_ai_config() -> AIConfig:
    """Load AI config from ai-backup/ai_config.jsonc."""
    if AI_CONFIG_PATH.exists():
        data = json.loads(AI_CONFIG_PATH.read_text(encoding="utf-8"))
        return AIConfig(
            api_base_url=data.get("api_base_url", AIConfig.api_base_url),
            model=data.get("model", AIConfig.model),
            temperature=data.get("temperature", AIConfig.temperature),
            api_key=data.get("api_key", AIConfig.api_key),
        )
    return AIConfig()


# ── generate ──────────────────────────────────────────────────────────

@click.command()
@click.option("--name", help="Card name")
@click.option("--desc", help="Card effect description")
@click.option("--type", "type_", type=int, help="Card type bitmask")
@click.option("--main-type", type=click.Choice(list(MAIN_TYPE_MAP.keys())))
@click.option("--subtype", "subtypes", multiple=True,
              type=click.Choice(list(SUBTYPE_MAP.keys())))
@click.option("--attribute", type=click.Choice(list(ATTRIBUTE_MAP.keys())))
@click.option("--race", type=click.Choice(list(RACE_MAP.keys())))
@click.option("--level", type=int)
@click.option("--atk", type=int)
@click.option("--def", "def_", type=int)
@click.option("--lscale", type=int)
@click.option("--rscale", type=int)
@click.option("--link-marker", "link_markers", multiple=True,
              type=click.Choice(list(LINK_MARKER_MAP.keys())))
@click.option("--code", type=int, default=0)
@click.option("--alias", type=int, default=0)
@click.option("--ot", type=int, default=0)
@click.option("--ref-db", type=click.Path(exists=True))
@click.option("--json-input", is_flag=True, help="Read card as JSON from stdin")
@click.option("--output", "-o", type=click.Path())
@click.option("--timeout", type=int, default=300)
def generate(name, desc, type_, main_type, subtypes, attribute, race, level, atk,
             def_, lscale, rscale, link_markers, code, alias, ot, ref_db,
             json_input, output, timeout):
    """Generate a Lua script for a YGOPro card using AI."""
    if json_input:
        raw = json.loads(sys.stdin.read())
        card_data = raw if isinstance(raw, dict) else raw
    else:
        card_data = build_card_from_args(
            name=name, desc=desc, type_=type_, main_type=main_type,
            subtypes=subtypes, attribute=attribute, race=race,
            level=level, atk=atk, def_=def_, lscale=lscale, rscale=rscale,
            link_markers=link_markers, code=code, alias=alias, ot=ot,
        )

    config = _load_ai_config()
    ref_scripts = []
    db_cards = []

    if not ref_db:
        p = load_paths()
        ref_db = p.default_db_path or None
    if ref_db:
        click.echo(f"Searching reference scripts in {ref_db}...", err=True)
        paths = load_paths()
        ref_scripts = find_reference_scripts(
            ref_db, card_data, script_dir=paths.default_script_dir or None
        )
        if ref_scripts:
            click.echo(f"Found {len(ref_scripts)} reference script(s)", err=True)
        db_cards = get_all_cards(ref_db)

    click.echo("Generating script...", err=True)

    try:
        result = _generate(
            card_to_bridge_format(card_data), config,
            database_cards=[card_to_bridge_format(c) for c in db_cards],
            ref_scripts=ref_scripts, timeout=timeout,
        )
    except BridgeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    script = result.get("script", "")
    diagnostics = result.get("diagnostics", [])
    score = result.get("score", 0)

    if output:
        Path(output).write_text(script, encoding="utf-8")
        click.echo(f"Script written to {output}")
    else:
        click.echo(script)

    if diagnostics:
        click.echo(f"\n--- Diagnostics (score: {score}) ---", err=True)
        click.echo(format_diagnostics(diagnostics), err=True)


# ── repair ────────────────────────────────────────────────────────────

@click.command()
@click.option("--script", "-s", type=click.Path(exists=True), required=True)
@click.option("--name", help="Card name (context for repair)")
@click.option("--desc", help="Card description (context for repair)")
@click.option("--output", "-o", type=click.Path())
@click.option("--timeout", type=int, default=300)
def repair(script, name, desc, output, timeout):
    """Repair a Lua script using AI, guided by local diagnostics."""
    script_content = Path(script).read_text(encoding="utf-8")
    config = _load_ai_config()
    card_data = {"name": name or "", "desc": desc or ""}

    click.echo("Repairing...", err=True)
    try:
        result = _repair(script_content, card_data, config, timeout=timeout)
    except BridgeError as e:
        click.echo(f"Repair error: {e}", err=True)
        sys.exit(1)

    repaired = result.get("script", "")
    score = result.get("score", 0)
    diagnostics = result.get("diagnostics", [])

    if output:
        Path(output).write_text(repaired, encoding="utf-8")
        click.echo(f"Repaired script written to {output}")
    else:
        click.echo(repaired)
    if diagnostics:
        click.echo(f"\n--- Diagnostics (score: {score}) ---", err=True)
        click.echo(format_diagnostics(diagnostics), err=True)


# ── parse ─────────────────────────────────────────────────────────────

@click.command()
@click.argument("manuscript", required=False)
@click.option("--file", "-f", type=click.Path(exists=True),
              help="Read manuscript from file")
@click.option("--timeout", type=int, default=300)
def parse(manuscript, file, timeout):
    """Parse free-form card manuscript into structured data (AI)."""
    if file:
        manuscript = Path(file).read_text(encoding="utf-8")
    elif not manuscript:
        manuscript = sys.stdin.read()

    if not manuscript.strip():
        click.echo("Error: no manuscript text provided", err=True)
        sys.exit(1)

    config = _load_ai_config()
    click.echo("Parsing manuscript...", err=True)

    try:
        result = parse_manuscript(manuscript, config, timeout=timeout)
    except BridgeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    cards = result.get("cards", [])
    summary = result.get("summary", "")
    click.echo(f"Parsed {len(cards)} card(s): {summary}")
    for c in cards:
        click.echo(format_card_brief(c))


# ── batch ─────────────────────────────────────────────────────────────

@click.command()
@click.option("--db-path", type=click.Path(exists=True))
@click.option("--instruction", "-i", required=True,
              help="Natural language instruction for batch processing")
@click.option("--search", "search_term", help="Only process cards matching keyword")
@click.option("--limit", type=int, default=10)
@click.option("--dry-run", is_flag=True, help="Preview affected cards without generating")
@click.option("--output-dir", type=click.Path())
@click.option("--timeout", type=int, default=300)
def batch(db_path, instruction, search_term, limit, dry_run, output_dir, timeout):
    """Batch generate Lua scripts for cards in a CDB using AI."""
    if not db_path:
        paths = load_paths()
        db_path = paths.default_db_path
    if not db_path:
        raise click.UsageError("No CDB path. Set default_db_path or use --db-path.")
    if not Path(db_path).exists():
        raise click.UsageError(f"CDB file not found: {db_path}")

    if search_term:
        cards = search_cards(db_path, search_term, limit=limit)
    else:
        cards = get_all_cards(db_path)[:limit]

    if not cards:
        click.echo("No cards found.")
        return

    click.echo(f"Processing {len(cards)} card(s)...", err=True)

    if dry_run:
        for c in cards:
            click.echo(format_card_brief(c))
        return

    config = _load_ai_config()
    all_cards = get_all_cards(db_path)
    paths = load_paths()
    ref_scripts = find_reference_scripts(
        db_path, cards[0] if cards else {},
        script_dir=paths.default_script_dir or None,
    )

    results = []
    for i, card in enumerate(cards):
        click.echo(f"[{i+1}/{len(cards)}] {format_card_brief(card)}", err=True)
        try:
            result = _generate(
                card_to_bridge_format(card), config,
                database_cards=[card_to_bridge_format(c) for c in all_cards],
                ref_scripts=ref_scripts, timeout=timeout,
            )
            script = result.get("script", "")
            score = result.get("score", 0)
            results.append({
                "code": card["code"], "name": card["name"],
                "ok": True, "script": script, "score": score,
            })
            if output_dir:
                out_path = Path(output_dir) / f"c{card['code']}.lua"
                out_path.write_text(script, encoding="utf-8")
                click.echo(f"  -> {out_path} (score: {score})", err=True)
            else:
                click.echo(f"  -> score: {score}", err=True)
        except BridgeError as e:
            click.echo(f"  -> Error: {e}", err=True)
            results.append({
                "code": card["code"], "name": card["name"],
                "ok": False, "error": str(e),
            })

    ok_count = sum(1 for r in results if r.get("ok"))
    click.echo(f"\nDone: {ok_count}/{len(results)} succeeded.")


# ── Main CLI group ────────────────────────────────────────────────────

@click.group()
def main():
    """AI generation backup CLI — not used by YGO-Script/YGO-Desc skills."""


main.add_command(generate)
main.add_command(repair)
main.add_command(parse)
main.add_command(batch)

if __name__ == "__main__":
    main()
