import sys
import os

import sys
import os

try:
    # Fge den aktuellen Ordner zum Python-Pfad hinzu, damit er die Fenrir-Module (wie tools) findet
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

    from swarm_workers import SwarmOrchestrator, MicroWorker, logger
    import swarm_workers

    # Externe Hosts muessen bewusst konfiguriert werden.
    MASTER_IP = os.environ.get("FENRIR_MASTER_IP", "127.0.0.1")

    print("="*60)
    print(f"STARTE EXTERNE SWARM WORKER FUER FENRIR")
    print(f"Verbinde mit Haupt-Gehirn auf: {MASTER_IP}")
    print("="*60)

    # Patche die URLs im geladenen Modul
    swarm_workers.DISTRIBUTED_CORE_URL = f"http://{MASTER_IP}:8000"
    swarm_workers.MINISTRY_URL = f"http://{MASTER_IP}:8001/generate"

    # Starte den dynamischen Fraktal-Schwarm!
    orchestrator = SwarmOrchestrator()
    orchestrator.run()

except KeyboardInterrupt:
    print("Shutting down external Fractal Swarm.")
except Exception as e:
    print(f"\n[FEHLER] Das Skript ist abgestürzt: {e}")
    import traceback
    traceback.print_exc()

input("\nDrücke ENTER um das Fenster zu schließen...")
