"""Subprocess bridge to Node.js AI engine."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BRIDGE_DIR = Path(__file__).parent / "bridge"
BRIDGE_SCRIPT = BRIDGE_DIR / "ai-bridge.mjs"
TS_CONFIG = BRIDGE_DIR / "tsconfig.json"

# Timeout for AI generation (5 minutes)
AI_TIMEOUT = 300


@dataclass
class AIConfig:
    """AI provider configuration for backup CLI use only."""
    api_base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 1.0
    api_key: str = ""

    def to_bridge_config(self) -> dict[str, Any]:
        return {
            "apiBaseUrl": self.api_base_url,
            "model": self.model,
            "temperature": self.temperature,
            "apiKey": self.api_key,
        }


class BridgeError(Exception):
    """Error from the Node.js bridge."""
    pass


def _run_bridge(payload: dict[str, Any], timeout: int = AI_TIMEOUT) -> dict[str, Any]:
    """Run the Node.js bridge with JSON input, return JSON output."""
    proc = subprocess.run(
        ["bun", "--tsconfig=" + str(TS_CONFIG), str(BRIDGE_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(BRIDGE_DIR),
    )

    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        # Try to parse JSON error from stdout even on failure
        try:
            result = json.loads(proc.stdout.strip())
            if not result.get("ok"):
                raise BridgeError(result.get("error", "Unknown bridge error"))
            return result
        except json.JSONDecodeError:
            raise BridgeError(stderr or f"Bridge exited with code {proc.returncode}")

    try:
        result = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        raise BridgeError(f"Failed to parse bridge output: {proc.stdout[:200]}")

    if not result.get("ok"):
        raise BridgeError(result.get("error", "Unknown bridge error"))

    return result


def diagnose(script: str) -> dict[str, Any]:
    """Run local Lua diagnostics on a script (no AI call)."""
    return _run_bridge({
        "action": "diagnose",
        "script": script,
        "config": {},
    }, timeout=30)


def generate(
    card: dict[str, Any],
    config: AIConfig,
    database_cards: list[dict] | None = None,
    ref_scripts: list[dict] | None = None,
    timeout: int = AI_TIMEOUT,
) -> dict[str, Any]:
    """Generate a Lua script for a card using AI."""
    return _run_bridge({
        "action": "generate",
        "card": card,
        "config": config.to_bridge_config(),
        "databaseCards": database_cards or [],
        "refScripts": ref_scripts or [],
    }, timeout=timeout)


def repair(
    script: str,
    card: dict[str, Any] | None,
    config: AIConfig,
    timeout: int = AI_TIMEOUT,
) -> dict[str, Any]:
    """Repair a Lua script using AI diagnostics feedback."""
    return _run_bridge({
        "action": "repair",
        "script": script,
        "card": card or {},
        "config": config.to_bridge_config(),
    }, timeout=timeout)


def parse_manuscript(
    manuscript: str,
    config: AIConfig,
    current_card: dict[str, Any] | None = None,
    timeout: int = AI_TIMEOUT,
) -> dict[str, Any]:
    """Parse free-form card manuscript into structured card data."""
    return _run_bridge({
        "action": "parse",
        "card": current_card or {},
        "manuscript": manuscript,
        "config": config.to_bridge_config(),
    }, timeout=timeout)


def batch_edit(
    instruction: str,
    config: AIConfig,
    database_cards: list[dict],
    timeout: int = AI_TIMEOUT,
) -> dict[str, Any]:
    """Run batch editing instruction on a set of cards."""
    return _run_bridge({
        "action": "batch",
        "instruction": instruction,
        "config": config.to_bridge_config(),
        "databaseCards": database_cards,
    }, timeout=timeout)
