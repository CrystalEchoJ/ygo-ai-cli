/**
 * Shim: re-exports from vendored Lua diagnostics engine.
 * Originally imported from DataEditorY; now self-contained in lua_diagnostics/.
 */

export { analyzeLuaScript, ensureLuaDiagnosticsCatalogLoaded } from "./lua_diagnostics/diagnostics.ts";
