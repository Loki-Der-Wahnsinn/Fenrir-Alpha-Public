import sys
import os
import time
import requests
import uuid
import threading
import subprocess
import tempfile
import json
import logging

# =========================================================================
# FENRIR LIGHTWEIGHT FRACTAL SWARM WORKER
# Zero-Dependency Node - Kann auf jedem PC mit Python + requests ausgefuehrt werden!
#
# HAERTUNG (Architektur-Audit Nexus 2.0, Befunde K2, H3, H7):
#   - Registrierung sendet jetzt capabilities (vorher 422 -> Node bekam nie Arbeit)
#   - Ergebnis-Abgabe sendet node_ip als Query-Parameter (vorher 422)
#   - Aufgabenabholung per POST statt GET (H4)
#   - Timeout-Kill funktioniert auch auf Linux (vorher nur taskkill/Windows)
#   - Kein dauerhaftes Selbstabschalten nach 60 s mehr (H7)
#   - Token-Unterstuetzung fuer den gehaerteten Hive
# =========================================================================

# KONFIGURATION: IP des Haupt-PCs. Ueberschreibbar per Umgebungsvariable.
MASTER_IP = os.environ.get("FENRIR_MASTER_IP", "127.0.0.1")
DISTRIBUTED_CORE_URL = f"http://{MASTER_IP}:8000"
MINISTRY_URL = f"http://{MASTER_IP}:8001/generate"
HIVE_TOKEN = os.environ.get("FENRIR_HIVE_TOKEN", "").strip()

# Wie lange der Node ohne Arbeit wartet, bevor er sich beendet.
# 0 = nie beenden (Dauerbetrieb). Default: Dauerbetrieb.
IDLE_EXIT_SECONDS = int(os.environ.get("FENRIR_WORKER_IDLE_EXIT", "0"))
# Timeout fuer fremden Code in Sekunden
CODE_TIMEOUT = int(os.environ.get("FENRIR_CODE_TIMEOUT", "10"))

HEADERS = {"X-Fenrir-Token": HIVE_TOKEN} if HIVE_TOKEN else {}

# Simple Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("LightweightWorker")


def _kill_tree(proc):
    """Beendet einen Prozess samt Kindern, plattformuebergreifend.

    Befund H3: Vorher wurde hier ausschliesslich `taskkill` aufgerufen. Auf
    Linux warf das FileNotFoundError, der Prozess lief weiter und die
    Temp-Datei blieb liegen - eine Endlosschleife brannte CPU bis zum Neustart.
    """
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10)
        else:
            proc.kill()
    except Exception as e:
        logger.warning(f"Prozess {proc.pid} konnte nicht beendet werden: {e}")
    finally:
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass


class LightweightWorker(threading.Thread):
    def __init__(self, index):
        super().__init__()
        self.node_id = f"worker_{index}_{uuid.uuid4().hex[:8]}"
        self.daemon = True

    def register(self):
        # Befund K2: `capabilities` ist im Hive-Modell ein Pflichtfeld (jetzt mit
        # Default). Der Node sendet es nun explizit, damit die Registrierung
        # nicht mehr mit 422 abgewiesen wird.
        try:
            resp = requests.post(f"{DISTRIBUTED_CORE_URL}/register_node", json={
                "node_ip": self.node_id,
                "status": "idle",
                "capabilities": {
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                    "execute_code": True,
                    "llm_query": True,
                    "web_search": False,
                },
            }, headers=HEADERS, timeout=5)
            if resp.status_code == 200:
                logger.info(f"{self.node_id} erfolgreich am Hive registriert ({MASTER_IP}).")
                return True
            logger.warning(f"{self.node_id} Registrierung abgelehnt: HTTP {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"{self.node_id} Registrierung fehlgeschlagen: {e}")
        return False

    def run(self):
        self.register()
        idle_count = 0
        while True:
            try:
                # Befund H4: POST statt GET, weil die Abholung die Queue veraendert.
                resp = requests.post(
                    f"{DISTRIBUTED_CORE_URL}/get_task",
                    params={"node_ip": self.node_id},
                    headers=HEADERS,
                    timeout=5,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "assigned":
                        task = data.get("task", {})
                        self.process_task(task)
                        idle_count = 0
                    elif data.get("status") == "error":
                        # Nicht registriert (z.B. Hive neu gestartet) -> erneut anmelden
                        self.register()
                        idle_count += 1
                    else:
                        idle_count += 1
                else:
                    idle_count += 1
            except Exception:
                idle_count += 1

            # Befund H7: Frueher beendete sich der Node nach 60 s Leerlauf
            # dauerhaft, wodurch der Schwarm in ruhigen Phasen auf null fiel.
            # Jetzt: Dauerbetrieb (Default), optional per Env begrenzbar.
            if IDLE_EXIT_SECONDS > 0 and idle_count > IDLE_EXIT_SECONDS:
                logger.info(f"{self.node_id} beendet sich nach {IDLE_EXIT_SECONDS}s Leerlauf (konfiguriert).")
                break

            # Alle 30 s stilles Re-Registrieren, damit der Hive den Knoten nicht verwirft
            if idle_count and idle_count % 30 == 0:
                self.register()

            time.sleep(1)

    def process_task(self, task):
        task_id = task.get("task_id")
        task_type = task.get("task_type")
        payload = task.get("payload", {})

        logger.info(f"{self.node_id} verarbeitet Task {task_id} vom Typ {task_type}...")
        result = {}

        try:
            if task_type == "execute_code":
                class_name = payload.get("class_name", "Unknown")
                code = payload.get("args", {}).get("code", payload.get("code", ""))
                if code:
                    temp_name = None
                    try:
                        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                            f.write(code)
                            temp_name = f.name
                        proc = subprocess.Popen(
                            [sys.executable, temp_name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        try:
                            stdout, stderr = proc.communicate(timeout=CODE_TIMEOUT)
                            res_code = proc.returncode
                        except subprocess.TimeoutExpired:
                            _kill_tree(proc)
                            stdout, stderr, res_code = "", "", -1
                            result = {"status": "error",
                                      "message": "Timeout (Endlosschleife erkannt) - Prozessbaum terminiert."}
                        else:
                            if res_code == 0:
                                result = {"status": "success",
                                          "data": f"Klasse {class_name} erfolgreich syntaktisch geprueft."}
                            else:
                                result = {"status": "error",
                                          "message": f"Syntax/Runtime Error:\n{stderr or stdout}"}
                    finally:
                        # Befund H3: Temp-Datei wird jetzt in JEDEM Fall geloescht.
                        if temp_name and os.path.exists(temp_name):
                            try:
                                os.unlink(temp_name)
                            except OSError:
                                pass
                else:
                    result = {"status": "error", "message": "No code provided for execution."}

            elif task_type == "llm_query":
                prompt = payload.get("prompt", "")
                llm_resp = requests.post(MINISTRY_URL, json={
                    "prompt": prompt, "temperature": 0.7, "max_tokens": 1024, "role": "agent_worker"
                }, timeout=120)
                try:
                    result = {"status": "success", "data": llm_resp.json().get("response", "")}
                except ValueError:
                    result = {"status": "error",
                              "message": f"Ministerium lieferte kein JSON (HTTP {llm_resp.status_code})."}

            elif task_type == "web_search":
                result = {"status": "error",
                          "message": "Web search wird auf Lightweight-Nodes nicht unterstuetzt. An Master delegieren."}

            else:
                result = {"status": "error", "message": f"Unknown task type: {task_type}"}

        except Exception as e:
            result = {"status": "error", "message": f"Worker Exception: {str(e)}"}

        # Ergebnis abgeben.
        # Befund K2b: `node_ip` ist im Hive ein QUERY-Parameter, nicht Teil des
        # Bodys. Vorher wurde es in den Body gelegt -> 422 -> Ergebnis verworfen.
        try:
            requests.post(
                f"{DISTRIBUTED_CORE_URL}/submit_result",
                params={"node_ip": self.node_id},
                json={"task_id": task_id, "result": result},
                headers=HEADERS,
                timeout=5,
            )
            logger.info(f"{self.node_id} hat Task {task_id} abgeschlossen.")
        except Exception as e:
            logger.error(f"{self.node_id} konnte Ergebnis nicht abgeben: {e}")


class LightweightOrchestrator:
    def __init__(self, max_workers=50):
        self.workers = []
        self.max_workers = max_workers

    def run(self):
        logger.info(f"Starte LIGHTWEIGHT Fractal Swarm Orchestrator (Max Workers: {self.max_workers})...")
        self.spawn_worker()

        while True:
            try:
                resp = requests.get(f"{DISTRIBUTED_CORE_URL}/queue_size", headers=HEADERS, timeout=5)
                if resp.status_code == 200:
                    payload = resp.json()
                    q_size = payload.get("size", 0)
                    active_workers = len([w for w in self.workers if w.is_alive()])

                    if q_size > active_workers and active_workers < self.max_workers:
                        needed = min(q_size - active_workers, 5)
                        for _ in range(needed):
                            self.spawn_worker()
                        if needed > 0:
                            logger.info(f"[SWARM] Queue: {q_size}. Starte {needed} neue Lightweight-Agenten. "
                                        f"Aktiv: {active_workers + needed}")

                self.workers = [w for w in self.workers if w.is_alive()]
            except Exception as e:
                # Befund M5: Fehler nicht mehr stumm verschlucken.
                logger.debug(f"Orchestrator-Zyklus: {e}")
            time.sleep(1)

    def spawn_worker(self):
        w = LightweightWorker(len(self.workers))
        w.start()
        self.workers.append(w)


if __name__ == "__main__":
    print("==================================================================")
    print(" FENRIR LIGHTWEIGHT NODE")
    print(" Vollstaendig entkoppelter Worker. Braucht nur Python + requests.")
    print(f" Master: {MASTER_IP}")
    print(f" Token:  {'gesetzt' if HIVE_TOKEN else 'NICHT GESETZT (Hive ungeschuetzt)'}")
    print("==================================================================")
    try:
        orchestrator = LightweightOrchestrator()
        orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Lightweight Node wird beendet.")
    except Exception as e:
        logger.error(f"Fataler Fehler: {e}")

    input("Druecke ENTER zum Beenden...")
