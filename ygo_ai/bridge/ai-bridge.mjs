#!/usr/bin/env bun
/**
 * AI Bridge — stdin/stdout JSON interface to DataEditorY's AI script engine.
 *
 * Usage: echo '{"action":"diagnose","script":"...","config":{}}' | bun --tsconfig=bridge/tsconfig.json bridge/ai-bridge.mjs
 *
 * Protocol:
 *   stdin  → { action, card?, script?, instruction?, config, databaseCards?, refScripts? }
 *   stdout → { ok: true, script?, diagnostics?, score?, cards?, summary?, results? }
 *            { ok: false, error: "..." }
 */

import { analyzeLuaScript, ensureLuaDiagnosticsCatalogLoaded } from "./diagnostics-shim.mjs";

// service-shim is imported lazily — only generate/repair/batch need it
let _serviceShim = null;
async function getServiceShim() {
  if (!_serviceShim) {
    _serviceShim = await import("./service-shim.mjs");
  }
  return _serviceShim;
}

// ── Helpers ──────────────────────────────────────────────────────────

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const raw = Buffer.concat(chunks).toString("utf-8").trim();
  if (!raw) throw new Error("No stdin input received");
  return JSON.parse(raw);
}

function respond(data) {
  process.stdout.write(JSON.stringify(data) + "\n");
}

function fail(error) {
  respond({ ok: false, error: error instanceof Error ? error.message : String(error) });
  process.exit(1);
}

// ── Card builder helpers ─────────────────────────────────────────────

const ATTRIBUTE_MAP = {
  earth: 1, water: 2, fire: 4, wind: 8,
  light: 16, dark: 32, divine: 64,
};
const RACE_MAP = {
  warrior: 1, spellcaster: 2, fairy: 4, fiend: 8, zombie: 16,
  machine: 32, aqua: 64, pyro: 128, rock: 256, wingedbeast: 512,
  plant: 1024, insect: 2048, thunder: 4096, dragon: 8192,
  beast: 16384, beastwarrior: 32768, dinosaur: 65536,
  fish: 131072, seaserpent: 262144, reptile: 524288,
  psychic: 1048576, divinebeast: 2097152, creatorgod: 4194304,
  wyrm: 8388608, cyberse: 16777216, illusion: 33554432,
};
const SUBTYPE_MAP = {
  normal: 0x10, effect: 0x20, fusion: 0x40, ritual: 0x80,
  spirit: 0x200, union: 0x400, gemini: 0x800, tuner: 0x1000,
  synchro: 0x2000, token: 0x4000, quickplay: 0x10000,
  continuous_spell: 0x20000, continuous_trap: 0x20000,
  equip: 0x40000, field: 0x80000, counter: 0x100000,
  flip: 0x200000, toon: 0x400000, xyz: 0x800000,
  pendulum: 0x1000000, spssummon: 0x2000000, link: 0x4000000,
  ritual_spell: 0x8000000,
};
const LINK_MARKER_NAME_TO_BIT = {
  downleft: 1, down: 2, downright: 4,
  left: 8, right: 32,
  upleft: 64, up: 128, upright: 256,
};

function buildCardFromInput(raw) {
  if (!raw) throw new Error("No card data provided");
  const card = {
    code: Number(raw.code ?? 0),
    alias: Number(raw.alias ?? 0),
    name: String(raw.name ?? ""),
    desc: String(raw.desc ?? ""),
    ot: Number(raw.ot ?? 0),
    type: Number(raw.type ?? 0),
    attribute: Number(raw.attribute ?? 0),
    race: Number(raw.race ?? 0),
    attack: Number(raw.attack ?? raw.atk ?? 0),
    defense: Number(raw.defense ?? raw.def ?? 0),
    level: Number(raw.level ?? 0),
    lscale: Number(raw.lscale ?? raw.leftScale ?? 0),
    rscale: Number(raw.rscale ?? raw.rightScale ?? 0),
    linkMarker: Number(raw.linkMarker ?? raw.linkmarker ?? 0),
    setcode: Array.isArray(raw.setcode) ? raw.setcode.map(Number) : [0, 0, 0, 0],
    category: Number(raw.category ?? 0),
    strings: Array.isArray(raw.strings) ? raw.strings.map(String) : [],
  };

  // Resolve mainType + subtypes → type bitmask
  if (raw.mainType && (raw.subtypes || card.type === 0)) {
    let bits = raw.mainType === "monster" ? 0x1
      : raw.mainType === "spell" ? 0x2
      : raw.mainType === "trap" ? 0x4 : 0;
    for (const sub of (raw.subtypes ?? [])) {
      const key = String(sub).toLowerCase().replace(/[\s_/-]+/g, "");
      const bit = SUBTYPE_MAP[key];
      if (bit) bits |= bit;
    }
    if (bits !== 0) card.type = bits;
  }

  // Resolve string attribute/race names → numeric values
  if (typeof raw.attribute === "string") {
    card.attribute = ATTRIBUTE_MAP[raw.attribute.toLowerCase()] ?? card.attribute;
  }
  if (typeof raw.race === "string") {
    card.race = RACE_MAP[raw.race.toLowerCase()] ?? card.race;
  }
  if (Array.isArray(raw.linkMarkers)) {
    card.linkMarker = raw.linkMarkers.reduce((acc, m) => {
      const bit = LINK_MARKER_NAME_TO_BIT[String(m).toLowerCase()];
      return bit ? acc | bit : acc;
    }, 0);
  }

  return card;
}

// ── AiAppContext for CLI ─────────────────────────────────────────────

function createCliContext(config, databaseCards, refScripts) {
  return {
    async getAiConfig() {
      if (!config.apiKey && !process.env.YGO_AI_API_KEY) {
        throw new Error("API key not configured. Set --api-key or YGO_AI_API_KEY env var.");
      }
      return {
        apiBaseUrl: config.apiBaseUrl || process.env.YGO_AI_API_BASE || "https://api.openai.com/v1",
        model: config.model || process.env.YGO_AI_MODEL || "gpt-4o-mini",
        temperature: config.temperature ?? 1.0,
        secretKey: config.apiKey || process.env.YGO_AI_API_KEY || "",
      };
    },
    listOpenDatabases() {
      return [{ id: "db-1", name: "CLI Database", path: config.dbPath || ".", isActive: true }];
    },
    getActiveDatabaseId() { return "db-1"; },
    async getCardByIdInTab(_tabId, cardId) {
      return databaseCards.find(c => Number(c.code) === Number(cardId)) || undefined;
    },
    async getCardsByIdsInTab(_tabId, cardIds) {
      const set = new Set(cardIds.map(Number));
      return databaseCards.filter(c => set.has(Number(c.code)));
    },
    async queryCardsRaw(_tabId, queryClause, params) {
      if (!databaseCards.length) return [];
      if (!params?.name) return [];
      const pattern = String(params.name).replace(/%/g, "").toLowerCase();
      if (!pattern) return [];
      const limitMatch = queryClause.match(/LIMIT\s+(\d+)/i);
      const limit = limitMatch ? parseInt(limitMatch[1], 10) : 6;
      return databaseCards
        .filter(c =>
          String(c.name || "").toLowerCase().includes(pattern) ||
          String(c.desc || "").toLowerCase().includes(pattern)
        )
        .slice(0, Math.min(limit, 12));
    },
    getSelectedCardsInActiveTab() { return []; },
    getVisibleCardsInActiveTab() { return databaseCards.slice(0, 50); },
    async modifyCardsWithSnapshotInTab() { return true; },
    async deleteCardsWithSnapshotInTab() { return true; },
    async readCardScript(code) {
      const ref = refScripts.find(r => r.code === code);
      if (ref) return { exists: true, path: `script/c${code}.lua`, content: ref.script };
      return { exists: false, path: null, content: null };
    },
  };
}

// ── Actions ──────────────────────────────────────────────────────────

async function handleGenerate(input) {
  const card = buildCardFromInput(input.card);
  const context = createCliContext(input.config, input.databaseCards || [], input.refScripts || []);
  await ensureLuaDiagnosticsCatalogLoaded();

  const { generateCardScript } = await getServiceShim();
  const script = await generateCardScript(card, {
    context,
    signal: AbortSignal.timeout?.(300_000),
    onStageChange(stage) {
      if (process.stderr.isTTY) process.stderr.write(`[${stage}] `);
    },
  });

  const diagnostics = analyzeLuaScript(script);
  const score = diagnostics.reduce((s, d) => s + (d.severity === "error" ? 100 : 1), 0);
  if (process.stderr.isTTY) process.stderr.write("\n");

  respond({ ok: true, script, diagnostics, score });
}

async function handleRepair(input) {
  const card = buildCardFromInput(input.card || {});
  const context = createCliContext(input.config, [], input.refScripts || []);
  await ensureLuaDiagnosticsCatalogLoaded();

  const { generateCardScript } = await getServiceShim();
  const script = await generateCardScript(card, {
    context,
    signal: AbortSignal.timeout?.(300_000),
  });

  const diagnostics = analyzeLuaScript(script);
  const score = diagnostics.reduce((s, d) => s + (d.severity === "error" ? 100 : 1), 0);
  respond({ ok: true, script, diagnostics, score });
}

async function handleParse(input) {
  const card = buildCardFromInput(input.card || {});
  // For CLI use, return structured card data
  respond({
    ok: true,
    cards: [{
      code: card.code, alias: card.alias, name: card.name, desc: card.desc,
      ot: card.ot, type: card.type, attribute: card.attribute, race: card.race,
      level: card.level, lscale: card.lscale, rscale: card.rscale,
      attack: card.attack, defense: card.defense,
      linkMarker: card.linkMarker, setcode: card.setcode, category: card.category,
      strings: card.strings,
    }],
    summary: "Card data structured from input",
  });
}

async function handleDiagnose(input) {
  const script = (input.script || "").trim();
  if (!script) {
    respond({ ok: true, diagnostics: [], score: 0 });
    return;
  }
  await ensureLuaDiagnosticsCatalogLoaded();
  const diagnostics = analyzeLuaScript(script);
  const score = diagnostics.reduce((s, d) => s + (d.severity === "error" ? 100 : 1), 0);
  respond({ ok: true, diagnostics, score });
}

async function handleBatch(input) {
  const context = createCliContext(input.config, input.databaseCards || [], input.refScripts || []);
  const cards = (input.databaseCards || []).slice(0, 10); // safety limit
  const results = [];

  for (const dbCard of cards) {
    try {
      const card = buildCardFromInput(dbCard);
      const { generateCardScript: gen } = await getServiceShim();
      const script = await gen(card, {
        context,
        signal: AbortSignal.timeout?.(120_000),
      });
      const diagnostics = analyzeLuaScript(script);
      const score = diagnostics.reduce((s, d) => s + (d.severity === "error" ? 100 : 1), 0);
      results.push({ code: card.code, name: card.name, ok: true, script, diagnostics, score });
    } catch (err) {
      results.push({ code: dbCard.code, name: dbCard.name, ok: false, error: err.message });
    }
  }

  respond({ ok: true, results });
}

// ── Main ─────────────────────────────────────────────────────────────

const ACTIONS = { generate: handleGenerate, repair: handleRepair, parse: handleParse, diagnose: handleDiagnose, batch: handleBatch };

try {
  const input = await readStdin();
  const action = input.action || "diagnose";
  if (!ACTIONS[action]) {
    fail(`Unknown action: ${action}. Supported: ${Object.keys(ACTIONS).join(", ")}`);
  }
  await ACTIONS[action](input);
} catch (err) {
  fail(err);
}
