# Fenrir-Alpha (Bereinigter öffentlicher Kandidat)

Dies ist eine bereinigte, eigenständige Vorbereitung ohne private Git-Historie,
persönliche Notizen, WhatsApp-Pakete oder Zugangsdaten.

## Enthaltene Komponenten

- **Core & Kognitive Module:** `fenrir_core.py`, `agi_evolution_tracker.py`,
  `ast_modifier.py`, `code_parser.py`, `decay_matrix.py`, `epigenetic_memory.py`,
  `feel_engine.py`, `gguf_gateway.py`, `global_workspace.py`, `god_mode.py`,
  `graph_generator.py`, `hlmf_manager.py`, `sandbox_evaluator.py`,
  `soul_matrix.py`, `ur_bewusstsein.py`, `vector_cortex.py`,
  `brain/lobes/*`, `memory/vector_db.py`, `skills/*`
- **Hive & Swarm Worker:** `distributed_core.py`, `swarm_workers.py`,
  `lightweight_swarm_worker.py`, `external_swarm_worker.py`, `nexus_api.py`
  (Standard-Bind `127.0.0.1`, Token über `FENRIR_HIVE_TOKEN`, gemeinsame
  In-Memory-Queue ohne Mehrbenutzer-Isolation)
- **Werkzeuge:** `tools/file_ops.py` (workspace-begrenzt), `tools/web_search.py`,
  `tools/web_scraper.py`, `tools/academic_researcher.py`,
  `tools/trace_analyzer.py`, `tools/module_preflight.py`,
  `tools/mutation_target.py`, `tools/topology_features.py`,
  `tools/topology_graph.lua`, `tools/topology_optimizer.py`, `hf_uploader.py`

## Eigene Konfiguration eintragen

Vor der Nutzung eigene Konfiguration und Umgebungswerte lokal hinterlegen
(weder `.env` noch `config.json` werden mitgeliefert):

1. `.env.example` nach `.env` kopieren und eigene Werte setzen
   (`FENRIR_HIVE_TOKEN`, `FENRIR_MASTER_IP`, `FENRIR_GROK_URL`, `HF_TOKEN`).
2. `config.example.json` nach `config.json` kopieren und lokale Modelle bzw.
   Profilpfad anpassen.

## Tests

```powershell
python -m pytest -q tests
python tests\smoke_test_hive.py
```

Für die optionalen Lua-Vergleichstests zusätzlich `lupa` installieren.
