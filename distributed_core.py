import os
import json
import uuid
import ipaddress
import uvicorn
from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
import pydantic
from threading import Thread
import asyncio
# Befund K7: `sdr_cortex` liegt NICHT im Repository. Der Import auf Modulebene
# liess `import distributed_core` aus einem frischen Clone scheitern — der
# Hive-Master war damit aus dem Repo nicht startbar. Jetzt optional mit
# degradiertem Betrieb statt Totalausfall.
try:
    from sdr_cortex import SDRCortex
    SDR_CORTEX_AVAILABLE = True
except ImportError:  # pragma: no cover
    SDR_CORTEX_AVAILABLE = False

    class SDRCortex:  # Platzhalter, damit der Hive ohne SDR-Modul laeuft
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            print("[HIVE][WARNUNG] sdr_cortex.py fehlt im Repo — SDR Cortex ist deaktiviert.")

app = FastAPI(title="Fenrir Hive-Mind Master API")

# Mount MII Dashboard safely
import os
mii_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mii_dashboard")
os.makedirs(mii_dir, exist_ok=True)
try:
    app.mount("/mii", StaticFiles(directory=mii_dir, html=True), name="mii")
except Exception as e:
    print(f"[!] Warning: Konnte mii_dashboard nicht mounten: {e}")

# =========================================================================
# NEXUS 2.0 HAERTUNG — Audit-Befunde K1, K4, K5, H5, H6, H1
# =========================================================================
import threading
import time as _time
import hmac as _hmac
from fastapi import Header, Request
from fastapi.responses import JSONResponse

# --- Auth (Befund K1 + K4) -----------------------------------------------
# Token kommt aus der Umgebung. Ist es NICHT gesetzt, laeuft der Hive wie
# bisher weiter (Rueckwaertskompatibilitaet), loggt aber eine laute Warnung.
# Einzelne Routen koennen weiterhin ohne Token erreichbar sein.
HIVE_TOKEN = os.environ.get("FENRIR_HIVE_TOKEN", "").strip()

def _token_matches(supplied: str) -> bool:
    return _hmac.compare_digest(supplied.encode("utf-8"), HIVE_TOKEN.encode("utf-8"))

def require_token(x_fenrir_token: str = Header(default="")):
    """FastAPI-Dependency: prueft den Hive-Token, falls einer konfiguriert ist."""
    if not HIVE_TOKEN:
        return True
    if not _token_matches(x_fenrir_token):
        raise HTTPException(status_code=401, detail="Hive-Token fehlt oder ist falsch.")
    return True

if not HIVE_TOKEN:
    print("[HIVE][WARNUNG] FENRIR_HIVE_TOKEN ist nicht gesetzt — der Hive ist UNGESCHUETZT. "
          "Jeder im Netz kann Tasks einstellen und Code ausfuehren. Token setzen!")


def _allowed_hosts() -> set[str]:
    configured = os.environ.get("FENRIR_ALLOWED_HOSTS", "").strip()
    if configured:
        return {item.strip().lower() for item in configured.split(",") if item.strip()}
    return {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}


def _host_without_port(raw_host: str) -> str:
    host = raw_host.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        return host[: end + 1] if end != -1 else host
    if ":" in host:
        return host.rsplit(":", 1)[0]
    return host


def _origin_is_allowed(origin: str) -> bool:
    if not origin:
        return True
    configured = os.environ.get("FENRIR_ALLOWED_ORIGINS", "").strip()
    if configured:
        allowed = {item.strip().lower() for item in configured.split(",") if item.strip()}
        if "*" in allowed or origin.strip().lower() in allowed:
            return True
    from urllib.parse import urlparse

    parsed = urlparse(origin.strip())
    return (
        parsed.scheme in ("http", "https")
        and (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"}
    )


@app.middleware("http")
async def host_and_origin_guard(request: Request, call_next):
    """Rejects untrusted Host headers and cross-site browser Origins on local services."""
    allowed_hosts = _allowed_hosts()
    host_header = request.headers.get("host", "")
    if "*" not in allowed_hosts:
        if not host_header or _host_without_port(host_header) not in allowed_hosts:
            return JSONResponse(status_code=400, content={"detail": "Untrusted Host header."})

    origin_header = request.headers.get("origin", "")
    if origin_header and not _origin_is_allowed(origin_header):
        return JSONResponse(status_code=403, content={"detail": "Untrusted Origin header."})

    return await call_next(request)

# --- Gemeinsamer Zustand unter Lock (Befund K5) --------------------------
STATE_LOCK = threading.RLock()

# Globale Warteschlange fuer anstehende LLM- oder Berechnungs-Tasks
TASK_QUEUE = []
# Registrierte und aktive Rechenknoten
REGISTERED_NODES = {}
# Speicher fuer abgeschlossene Tasks (Ergebnisse)
COMPLETED_TASKS = {}
# Speicher fuer temporaere unbestaetigte Skills (fuer Worker)
TEMP_SKILLS = {}
# Laufende Tasks: task_id -> {"task": dict, "node": str, "ts": float} (Befund H5)
IN_FLIGHT = {}

# Obergrenzen gegen unbegrenztes Wachstum (Befund H6)
MAX_COMPLETED_TASKS = 5000
MAX_REGISTERED_NODES = 2000
# Nach dieser Zeit gilt ein zugewiesener Task als verwaist und geht zurueck in die Queue
TASK_VISIBILITY_TIMEOUT = 300.0
# Nach dieser Zeit gilt ein Knoten ohne Lebenszeichen als tot
NODE_TTL = 120.0

# --- Messaging Queues ---
MESSAGES_FOR_CORE = []
MESSAGES_FOR_UI = []

def queue_new_task(task_type: str, payload: dict) -> str:
    task_id = str(uuid.uuid4())
    with STATE_LOCK:
        TASK_QUEUE.append({"task_id": task_id, "task_type": task_type, "payload": payload})
    return task_id

def get_task_result(task_id: str):
    with STATE_LOCK:
        return COMPLETED_TASKS.get(task_id)

def _requeue_orphaned_tasks():
    """Holt Tasks zurueck, deren Worker sich nicht mehr gemeldet hat (Befund H5)."""
    now = _time.time()
    with STATE_LOCK:
        for task_id in list(IN_FLIGHT.keys()):
            entry = IN_FLIGHT[task_id]
            if now - entry["ts"] > TASK_VISIBILITY_TIMEOUT:
                IN_FLIGHT.pop(task_id, None)
                node = entry.get("node")
                if node in REGISTERED_NODES:
                    REGISTERED_NODES[node]["status"] = "idle"
                TASK_QUEUE.insert(0, entry["task"])
                print(f"[HIVE] Task {task_id} von Node {node} zurueck in die Queue (Timeout).")

def _prune_nodes():
    """Entfernt Knoten ohne Lebenszeichen (Befund H5/H6)."""
    now = _time.time()
    with STATE_LOCK:
        for ip in list(REGISTERED_NODES.keys()):
            last = REGISTERED_NODES[ip].get("last_seen", now)
            if now - last > NODE_TTL:
                REGISTERED_NODES.pop(ip, None)

class UIMessage(pydantic.BaseModel):
    message: str

@app.post("/ui/message/send")
def ui_message_send(req: UIMessage, _auth: bool = Depends(require_token)):
    """User sendet eine Nachricht ueber das UI an Fenrir."""
    with STATE_LOCK:
        MESSAGES_FOR_CORE.append(req.message)
    return {"status": "delivered"}

@app.get("/ui/message/poll_for_core")
def poll_for_core(_auth: bool = Depends(require_token)):
    """Fenrir holt Nachrichten des Users ab."""
    with STATE_LOCK:
        msgs = list(MESSAGES_FOR_CORE)
        MESSAGES_FOR_CORE.clear()
    return {"messages": msgs}

@app.post("/ui/message/from_core")
def ui_message_from_core(req: UIMessage, _auth: bool = Depends(require_token)):
    """Fenrir sendet eine Nachricht an das UI."""
    with STATE_LOCK:
        MESSAGES_FOR_UI.append(req.message)
    return {"status": "delivered"}

@app.get("/ui/message/poll")
def ui_message_poll(_auth: bool = Depends(require_token)):
    """UI holt Nachrichten von Fenrir ab."""
    with STATE_LOCK:
        msgs = list(MESSAGES_FOR_UI)
        MESSAGES_FOR_UI.clear()
    return {"messages": msgs}



# --- Web-UI Injektion & Telemetrie ---
INJECTED_GOALS = []
uvicorn_loop = None
_MINISTRY_CLIENT = None

class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_state(self, state_dict: dict):
        payload = json.dumps(state_dict)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()
log_manager = ConnectionManager()
sdr_manager = ConnectionManager()

def broadcast_sdr_sync(log_line: str):
    """Sicherer Aufruf aus dem synchronen Core-Thread, um SDR Logs an WebSockets zu senden."""
    global uvicorn_loop
    if uvicorn_loop is not None and sdr_manager.active_connections:
        payload = {"type": "log", "message": log_line}
        asyncio.run_coroutine_threadsafe(sdr_manager.broadcast_state(payload), uvicorn_loop)

def broadcast_telemetry_sync(state_dict: dict):
    """Sicherer Aufruf aus dem synchronen Core-Thread, um an WebSockets zu senden."""
    global uvicorn_loop
    if uvicorn_loop is not None and manager.active_connections:
        asyncio.run_coroutine_threadsafe(manager.broadcast_state(state_dict), uvicorn_loop)

def broadcast_log_sync(log_line: str):
    """Sicherer Aufruf aus dem synchronen Core-Thread, um Logs an WebSockets zu senden."""
    global uvicorn_loop
    if uvicorn_loop is not None and log_manager.active_connections:
        payload = {"type": "log", "message": log_line}
        asyncio.run_coroutine_threadsafe(log_manager.broadcast_state(payload), uvicorn_loop)

@app.websocket("/ws/swarm_status")
async def websocket_endpoint(websocket: WebSocket):
    # Befund K4: Jeder konnte per WebSocket Ziele injizieren. Wenn ein Token
    # konfiguriert ist, muss er als ?token=... mitgegeben werden.
    if HIVE_TOKEN:
        supplied = websocket.query_params.get("token", "")
        if not _token_matches(supplied):
            await websocket.close(code=1008)
            return
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if message.get("action") == "inject_goal":
                new_goal = message.get("payload")
                if new_goal and "description" in new_goal:
                    print(f"[UI-INJEKTION] Ein Administrator hat ein neues Ziel injiziert: {new_goal['description']}")
                    with STATE_LOCK:
                        INJECTED_GOALS.append(new_goal)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    if HIVE_TOKEN and not _token_matches(websocket.query_params.get("token", "")):
        await websocket.close(code=1008)
        return
    await log_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Logs empfangen keine Daten
    except WebSocketDisconnect:
        log_manager.disconnect(websocket)

@app.websocket("/ws/sdr")
async def websocket_sdr_endpoint(websocket: WebSocket):
    if HIVE_TOKEN and not _token_matches(websocket.query_params.get("token", "")):
        await websocket.close(code=1008)
        return
    await sdr_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        sdr_manager.disconnect(websocket)
# -----------------------------------

class TaskSubmit(pydantic.BaseModel):
    task_id: str
    result: dict

class NodeRegistration(pydantic.BaseModel):
    node_ip: str
    # Befund K2: capabilities war Pflichtfeld, der Lightweight-Worker sendet es
    # nicht -> 422 -> Worker bekam nie Arbeit. Jetzt optional mit Default.
    capabilities: dict = {}
    status: str = "idle"

@app.post("/register_node")
def register_node(data: NodeRegistration, _auth: bool = Depends(require_token)):
    """Worker Nodes rufen diesen Endpunkt auf, um sich im Hive anzumelden."""
    with STATE_LOCK:
        if len(REGISTERED_NODES) >= MAX_REGISTERED_NODES and data.node_ip not in REGISTERED_NODES:
            _prune_nodes()
        REGISTERED_NODES[data.node_ip] = {
            "status": data.status or "idle",
            "capabilities": data.capabilities,  # z.B. {"has_gpu": True, "ollama_models": ["llama3"]}
            "last_seen": _time.time(),
        }
        node_count = len(REGISTERED_NODES)
    print(f"[HIVE] Neuer Worker registriert: {data.node_ip}")
    return {"status": "registered", "node_count": node_count}


@app.post("/get_task")
def get_task(node_ip: str, _auth: bool = Depends(require_token)):
    """Worker Nodes fordern Arbeit an.

    Befund H4: war GET und hat dabei die Queue veraendert — jeder Retry,
    Proxy oder Prefetch verbrannte eine Aufgabe. Jetzt POST.
    Befund K5: Zugriff auf Queue und Knoten erfolgt unter Lock.
    """
    with STATE_LOCK:
        _requeue_orphaned_tasks()

        if node_ip not in REGISTERED_NODES:
            return {"status": "error", "message": "Node nicht registriert."}

        REGISTERED_NODES[node_ip]["last_seen"] = _time.time()

        if TASK_QUEUE:
            task = TASK_QUEUE.pop(0)
            REGISTERED_NODES[node_ip]["status"] = "busy"
            IN_FLIGHT[task["task_id"]] = {
                "task": task, "node": node_ip, "ts": _time.time()
            }
            return {"status": "assigned", "task": task}

        REGISTERED_NODES[node_ip]["status"] = "idle"
        return {"status": "no_tasks"}


@app.get("/receive/{node_id}")
def receive_alias(node_id: str, _auth: bool = Depends(require_token)):
    """Veralteter Alias. Bleibt aus Kompatibilitaet, ist aber ebenfalls POST-frei
    lesend: er liefert nur den Knotenstatus, keine Aufgabe mehr (Befund H4)."""
    with STATE_LOCK:
        node = REGISTERED_NODES.get(node_id)
    if not node:
        return {"status": "error", "message": "Node nicht registriert."}
    return {"status": "ok", "node": node_id, "state": node.get("status")}


@app.post("/submit_result")
def submit_result(node_ip: str, data: TaskSubmit, _auth: bool = Depends(require_token)):
    """Worker liefert das Ergebnis (z.B. generierten Code oder LLM-Antwort) ab."""
    with STATE_LOCK:
        if node_ip in REGISTERED_NODES:
            REGISTERED_NODES[node_ip]["status"] = "idle"
            REGISTERED_NODES[node_ip]["last_seen"] = _time.time()

        IN_FLIGHT.pop(data.task_id, None)

        # Befund H6: Obergrenze, damit COMPLETED_TASKS nicht bis zum OOM waechst.
        if len(COMPLETED_TASKS) >= MAX_COMPLETED_TASKS:
            for _k in list(COMPLETED_TASKS.keys())[: MAX_COMPLETED_TASKS // 10]:
                COMPLETED_TASKS.pop(_k, None)
        COMPLETED_TASKS[data.task_id] = data.result
    print(f"[HIVE] Task {data.task_id} erfolgreich verarbeitet von Node {node_ip}")
    return {"status": "acknowledged"}

@app.get("/fetch_skill/{class_name:path}")
def fetch_skill(class_name: str, _auth: bool = Depends(require_token)):
    """Gibt den Quellcode einer Klasse zurueck, damit Worker ihn in-memory ausfuehren koennen."""
    print(f"[HIVE] fetch_skill aufgerufen fuer: '{class_name}'. Verfügbare TEMP_SKILLS: {list(TEMP_SKILLS.keys())}")
    if class_name in TEMP_SKILLS:
        return {"status": "success", "class_name": class_name, "code": TEMP_SKILLS[class_name]}
    
    # Befund K3: Der frueher hier stehende Fallback ("wenn nur ein Skill aktiv ist,
    # liefere diesen, egal wie er heisst") ist ENTFERNT. Er hat bei einem Tippfehler
    # im Klassennamen fremden Code als "success" ausgeliefert. Lieber 404 als falscher Erfolg.

    brain_state_path = "memory/brain_state.json"
    if not os.path.exists(brain_state_path):
        raise HTTPException(status_code=404, detail="brain_state nicht gefunden")
    
    with open(brain_state_path, "r", encoding="utf-8") as f:
        state = json.load(f)
        
    arch_graph = state.get("architecture_graph", {})
    class_data = arch_graph.get(class_name)
    
    if not class_data or not class_data.get("file"):
        raise HTTPException(status_code=404, detail="Klasse oder Datei nicht gefunden")

    # Befund M1: Der Pfad kam ungeprueft aus brain_state.json. Ist diese Datei
    # durch Core oder LLM beschreibbar, war beliebiges Datei-Lesen moeglich.
    # Jetzt: realpath muss innerhalb des Repo-Wurzelverzeichnisses liegen.
    repo_root = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
    target = os.path.realpath(os.path.join(repo_root, class_data["file"]))
    if not target.startswith(repo_root + os.sep):
        raise HTTPException(status_code=403, detail="Pfad ausserhalb des Repos verweigert.")
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="Klasse oder Datei nicht gefunden")

    with open(target, "r", encoding="utf-8") as f:
        code = f.read()
        
    return {"status": "success", "class_name": class_name, "code": code}

class TaskRequest(pydantic.BaseModel):
    task_type: str
    payload: dict

# Befund K1: "execute_code" nimmt freien Python-Code entgegen und startet ihn.
# Ohne Allowlist ist /tasks/submit eine Remote-Code-Execution-Schnittstelle.
ALLOWED_TASK_TYPES = {"web_search", "llm_query", "execute_code"}

@app.post("/tasks/submit")
def submit_task_endpoint(req: TaskRequest, _auth: bool = Depends(require_token)):
    """Der Core nutzt diesen Endpunkt, um Arbeit an den Hive zu delegieren."""
    if req.task_type not in ALLOWED_TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Unbekannter task_type: {req.task_type}")
    if req.task_type == "execute_code" and not HIVE_TOKEN:
        # Ohne gesetzten Token wird freie Codeausfuehrung verweigert.
        raise HTTPException(
            status_code=403,
            detail="execute_code erfordert FENRIR_HIVE_TOKEN. Ohne Token ist der Hive offen.",
        )
    task_id = queue_new_task(req.task_type, req.payload)
    return {"status": "queued", "task_id": task_id}

@app.get("/tasks/result/{task_id}")
def get_task_result_endpoint(task_id: str, _auth: bool = Depends(require_token)):
    """Liest das Ergebnis eines Tasks aus, falls vorhanden."""
    with STATE_LOCK:
        if task_id in COMPLETED_TASKS:
            return {"status": "completed", "result": COMPLETED_TASKS.pop(task_id)}
    return {"status": "pending"}

@app.get("/queue_size")
def get_queue_size(_auth: bool = Depends(require_token)):
    """Gibt die aktuelle Anzahl der ausstehenden Tasks zurück (für Swarm Orchestrator)."""
    with STATE_LOCK:
        return {"size": len(TASK_QUEUE), "in_flight": len(IN_FLIGHT), "nodes": len(REGISTERED_NODES)}

# (Doppelte UI-Routen entfernt — Befund H1. Die einzige Implementierung steht oben.)

# --- Mobile & Nexus Reverse Proxy to Ministry (Port 8001) ---
@app.post("/generate")
@app.post("/api/generate")
async def proxy_generate_to_ministry(req: dict, _auth: bool = Depends(require_token)):
    """Proxy fuer Handy- & Nexus-Clients: Leitet Anfragen transparent an das Ministerium (Port 8001) weiter."""
    # Befund M4: Client pro Request (kein Pooling), kein Retry, resp.json()
    # ungeprueft -> ein Nicht-JSON-Fehler des Ministeriums wurde zum 500er.
    # Jetzt: geteilter Client, ein Retry, saubere Fehlerabbildung.
    import httpx
    global _MINISTRY_CLIENT
    try:
        if _MINISTRY_CLIENT is None:
            _MINISTRY_CLIENT = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=5.0),
                limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            )
        client = _MINISTRY_CLIENT
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Proxy-Client nicht verfuegbar: {e}")

    last_err = None
    for attempt in (1, 2):
        try:
            resp = await client.post("http://127.0.0.1:8001/generate", json=req)
            if resp.status_code >= 500:
                last_err = f"Ministerium antwortete {resp.status_code}"
                continue
            try:
                return resp.json()
            except ValueError:
                raise HTTPException(
                    status_code=502,
                    detail="Ministerium lieferte kein gueltiges JSON.",
                )
        except HTTPException:
            raise
        except Exception as e:
            last_err = str(e)

    raise HTTPException(status_code=503, detail=f"Ministry uplink (8001) offline: {last_err}")

def validate_hive_bind(host):
    host = host.strip()
    if not host:
        raise ValueError("Der Hive-Host darf nicht leer sein.")
    try:
        is_loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not HIVE_TOKEN and not is_loopback:
        raise ValueError("Ein Netzwerk-Bind erfordert FENRIR_HIVE_TOKEN; ohne Token nur Loopback-IP verwenden.")
    return host


def run_server(host, port):
    host = validate_hive_bind(host)
    global uvicorn_loop
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    uvicorn_loop = loop
    
    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    # Verhindert den "signal only works in main thread" Crash auf Windows
    server.install_signal_handlers = lambda: None
    try:
        loop.run_until_complete(server.serve())
    except OSError as e:
        if e.errno == 10048:
            print(f"[HIVE] Port {port} bereits belegt (Hive-Service des Orchestrators laeuft) - kein Fehler, Thread beendet sich leise.")
        else:
            print(f"[HIVE] Uvicorn OS-Fehler: {e}")
    except BaseException as e:
        # SPARK 14.10: SystemExit(3) = Uvicorn Startup-Failure = Port schon belegt
        # (Core-interner Hive vs. Hive-Service). Leise melden statt Traceback-Laerm.
        if isinstance(e, SystemExit) and getattr(e, "code", None) == 3:
            print(f"[HIVE] Port {port} bereits belegt (Hive-Service laeuft) - Thread beendet sich leise, kein Fehler.")
        else:
            print(f"[HIVE] Uvicorn Crash in Thread (BaseException): {e}")
            import traceback
            traceback.print_exc()

def hive_bind_host():
    host = os.environ.get("FENRIR_HIVE_HOST", "127.0.0.1").strip()
    if not host:
        raise ValueError("FENRIR_HIVE_HOST darf nicht leer sein.")
    return host


def start_master_api(host=None, port=8000):
    """Startet den FastAPI Server absturzsicher in einem eigenen Thread."""
    host = validate_hive_bind(hive_bind_host() if host is None else host)
    print(f"[HIVE] Starte Master API auf {host}:{port}...")
    
    global sdr_cortex_instance
    try:
        sdr_cortex_instance = SDRCortex(broadcast_callback=broadcast_sdr_sync)
        sdr_cortex_instance.start()
        print("[HIVE] SDR Cortex Hintergrund-Scan gestartet.")
    except Exception as e:
        print(f"[HIVE] Fehler beim Starten des SDR Cortex: {e}")

    # Befund H2: Hier standen hart "0.0.0.0" und 8000 — die Parameter der
    # Funktion wurden ignoriert, jeder Aufruf mit anderem Port band still 8000.
    thread = Thread(target=run_server, args=(host, port), daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    import asyncio
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    host = validate_hive_bind(hive_bind_host())

    # Start SDR here when run as standalone
    try:
        from sdr_cortex import SDRCortex
        sdr_cortex_instance = SDRCortex(broadcast_callback=broadcast_sdr_sync)
        sdr_cortex_instance.start()
        print("[HIVE] SDR Cortex Hintergrund-Scan gestartet.")
    except Exception as e:
        print(f"[HIVE] Fehler beim Starten des SDR Cortex: {e}")
        
    import threading
    t = threading.Thread(target=run_server, args=(host, 8000), daemon=True)
    t.start()
    t.join()



