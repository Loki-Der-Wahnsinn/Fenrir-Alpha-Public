# Härtung Nexus 2.0 — Änderungsübersicht

Basis: Architektur-Audit `ARCHITEKTUR_AUDIT_NEXUS_2.0.md`
Branch: `fix/nexus2-architektur-haertung`

## Generierte Mutationsziele

Vom Modell generierte Mutationsziele muessen einfache Python-Modulnamen sein;
Pfade, Windows-Geraetenamen und Verknuepfungen am Ziel werden abgewiesen.
Bestehende gleichnamige Dateien im Workspace koennen weiterhin ausgewaehlt
werden. Dies beschraenkt keine Codeausfuehrung und schuetzt nicht vor allen
Verzeichnisverknuepfungen oder zeitgleichen Aenderungen am Dateisystem. Der
Core ist damit nicht fuer eine oeffentliche Bereitstellung freigegeben.

## Nachtrag: Schutz privater Hive-Daten

Wenn `FENRIR_HIVE_TOKEN` gesetzt ist, benoetigen Chat-Endpunkte,
`/tasks/result/{task_id}`, `/queue_size`, `/generate` und `/api/generate`
den Header `X-Fenrir-Token`. Fuer `/ws/logs` und
`/ws/sdr` ist wie bei `/ws/swarm_status` der Query-Parameter `token`
erforderlich. Die vorhandenen Core-Aufrufe fuer Chat, Aufgabenergebnisse und
Aufgabenversand senden den Token. Externe UIs muessen ihn ebenfalls mitsenden.
WebSocket-URLs koennen in Logs erscheinen; den Token nicht ueber ungeschuetzte
Netze senden oder in URLs speichern, die andere einsehen koennen.
Der Smoke-Test verwendet `TestClient`; er prueft keinen laufenden Dienst.

Ohne Token bleiben diese Endpunkte aus Kompatibilitaetsgruenden offen. Auch
mit Token gibt es nur einen gemeinsamen Zustand und keine Trennung nach Nutzer.
Andere Routen und angebundene Dienste sind nicht durch diesen Nachtrag
abgesichert; dieser Stand ist nicht fuer einen oeffentlichen Einsatz geeignet.
Die Worker verwenden standardmaessig `127.0.0.1` statt einer privaten LAN-IP;
fuer einen anderen Hive-Host `FENRIR_MASTER_IP` selbst setzen.
Der Hive bindet standardmaessig nur an `127.0.0.1`. Ein Netzwerk-Bind muss
explizit ueber `FENRIR_HIVE_HOST` gesetzt werden und erfordert bei den
mitgelieferten Startfunktionen `FENRIR_HIVE_TOKEN`. Ohne Token werden nur
numerische Loopback-Adressen zugelassen; Hostnamen wie `localhost` gelten
nicht als sicherer Loopback-Nachweis. Ein direkter Uvicorn-Aufruf kann diese
Bind-Pruefung umgehen. Allein das Setzen eines Tokens macht den Dienst nicht
sicher fuer die oeffentliche Bereitstellung.

## Hugging-Face-Upload

`hf_uploader.py` laedt nicht mehr automatisch den gesamten Arbeitsordner hoch.
Es verlangt ein eigenes Ziel-Repository und fuer jede Datei ein `--file`. Ohne
`--upload` zeigt es nur die ausgewaehlten Dateien an. Fuer einen tatsaechlichen
Upload muss der Nutzer `HF_TOKEN` selbst setzen und `--upload` angeben:

```powershell
python hf_uploader.py --folder <gepruefter-ordner> --repo-id <konto/repo> --file <relative-datei>
```

Diese Auswahl und einfache Dateinamen-Sperren ersetzen keine Inhaltspruefung auf
private Daten oder Geheimnisse. Verknuepfungen und Windows-Reparse-Points im
Quellpfad werden abgelehnt. Dateien werden einzeln hochgeladen; bei einem
Fehler koennen zuvor hochgeladene Dateien bereits im Ziel stehen.

## Geänderte Dateien

| Datei | Befunde |
|---|---|
| `distributed_core.py` | K1, K3, K4, K5, K7, H1, H2, H4, H5, H6, M1, M4 |
| `lightweight_swarm_worker.py` | K2, H3, H4, H7 |
| `swarm_workers.py` | H3, H4, H7, M5 |
| `tools/fenrir_schwester_bridge_daemon.py` | K6, H8, M2, M3, M6 |
| `tests/smoke_test_hive.py` | neu — 20 Prüfungen |

## Verhalten, das sich ändert

**Rückwärtskompatibel, ohne Eingriff:**
- Ohne `FENRIR_HIVE_TOKEN` startet der Hive auf Loopback und loggt eine Warnung.
- `/receive/{node_id}` bleibt bestehen, liefert jetzt nur noch Knotenstatus statt einer Aufgabe.

**Bricht bewusst mit dem alten Verhalten:**
- `/get_task` ist **POST**, nicht mehr GET. Alte Worker mit GET bekommen 405. Grund: GET hat die Queue verändert (H4).
- `fetch_skill` liefert bei unbekanntem Namen **404** statt irgendeines Skills (K3).
- `execute_code` wird ohne gesetztes `FENRIR_HIVE_TOKEN` mit **403** abgelehnt (K1).
- Worker beenden sich nicht mehr nach 60 s Leerlauf. Wer das alte Verhalten will: `FENRIR_WORKER_IDLE_EXIT=60`.

## Empfohlene Reihenfolge beim Ausrollen

1. Token setzen: `set FENRIR_HIVE_TOKEN=<zufallswert>` (PowerShell: `$env:FENRIR_HIVE_TOKEN="..."`)
2. Hive neu starten (`distributed_core`)
3. Worker neu starten — sie senden den Token automatisch aus derselben Umgebungsvariable
4. `python tests/smoke_test_hive.py` gegen den laufenden Stand
5. Bridge-Daemon neu starten

## Offen (nicht in diesem Branch)

- **K7 Rest:** `sdr_cortex.py` fehlt weiterhin im Repo. Der Import ist jetzt optional, der Dienst läuft ohne SDR Cortex — aber die Datei muss versioniert werden, sonst ist die SDR-Funktion nicht reproduzierbar.
- **Nexus selbst:** `web_apps/nexus/` ist nicht im Repo und konnte nicht geprüft werden.
- **M7:** Port-Inventar hat weiterhin keine Single Source of Truth.
