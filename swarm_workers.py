import os
import time
import requests
import uuid
import threading
try:
    from loguru import logger
    logger.add("logs/swarm_workers.log", rotation="10 MB")
except ImportError:
    import logging
    logger = logging.getLogger("swarm_workers")

try:
    from tools.web_search import WebSearchTool
except ImportError:
    WebSearchTool = None

MASTER_IP = os.environ.get("FENRIR_MASTER_IP", "127.0.0.1")
DISTRIBUTED_CORE_URL = f"http://{MASTER_IP}:8000"
MINISTRY_URL = f"http://{MASTER_IP}:8001/generate"
HIVE_TOKEN = os.environ.get("FENRIR_HIVE_TOKEN", "").strip()
HEADERS = {"X-Fenrir-Token": HIVE_TOKEN} if HIVE_TOKEN else {}
IDLE_EXIT_SECONDS = int(os.environ.get("FENRIR_WORKER_IDLE_EXIT", "0"))

class MicroWorker(threading.Thread):
    def __init__(self, node_id):
        super().__init__(daemon=True)
        self.node_id = f"worker_{node_id}_{str(uuid.uuid4())[:8]}"
        self.search_tool = WebSearchTool() if WebSearchTool is not None else None
        
    def register(self):
        try:
            requests.post(f"{DISTRIBUTED_CORE_URL}/register_node", json={
                "node_ip": self.node_id,
                "capabilities": {"web_search": self.search_tool is not None, "llm_query": True}
            }, headers=HEADERS, timeout=5)
            logger.info(f"{self.node_id} successfully registered at Hive.")
        except Exception as e:
            logger.warning(f"{self.node_id} failed to register: {e}")

    def run(self):
        # Auf Hive warten (statt blind loszurennen): bis 5 Min, dann normal weiter
        for _w in range(150):
            try:
                requests.get(f"{DISTRIBUTED_CORE_URL}/", timeout=2)
                break
            except Exception:
                time.sleep(2)
        self.register()
        idle_count = 0
        while True:
            try:
                # Befund H4: POST statt GET — die Abholung veraendert die Queue.
                resp = requests.post(f"{DISTRIBUTED_CORE_URL}/get_task",
                                     params={"node_ip": self.node_id},
                                     headers=HEADERS, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "assigned":
                        task = data.get("task", {})
                        self.process_task(task)
                        idle_count = 0
                    else:
                        idle_count += 1
                else:
                    idle_count += 1
            except Exception as e:
                idle_count += 1
                # Re-Registrierung alle 30s Stille (Hive kam evtl. spaeter hoch)
                if idle_count % 30 == 0:
                    self.register()
                
            if IDLE_EXIT_SECONDS > 0 and idle_count > IDLE_EXIT_SECONDS:
                logger.info(f"{self.node_id} shutting down due to inactivity.")
                break
                
            time.sleep(1)

    def process_task(self, task):
        task_id = task.get("task_id")
        task_type = task.get("task_type")
        payload = task.get("payload", {})
        
        logger.info(f"{self.node_id} processing task {task_id} of type {task_type}...")
        result = {}
        
        try:
            if task_type == "web_search":
                if self.search_tool is None:
                    result = {"status": "error", "message": "WebSearchTool is not available."}
                else:
                    query = payload.get("query", "")
                    res = self.search_tool.execute(query=query)
                    result = {"status": "success", "data": res}
            
            elif task_type == "llm_query":
                prompt = payload.get("prompt", "")
                llm_resp = requests.post(MINISTRY_URL, json={
                    "prompt": prompt, "temperature": 0.7, "max_tokens": 1024, "role": "agent_worker"
                }, timeout=120)
                result = {"status": "success", "data": llm_resp.json().get("response", "")}
            elif task_type == "execute_code":
                class_name = payload.get("class_name", "Unknown")
                code = payload.get("args", {}).get("code", payload.get("code", ""))
                if code:
                    import subprocess, tempfile, sys, os
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
                        f.write(code)
                        temp_name = f.name
                    try:
                        proc = subprocess.Popen([sys.executable, temp_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        try:
                            stdout, stderr = proc.communicate(timeout=10)
                            res_code = proc.returncode
                        except subprocess.TimeoutExpired:
                            # Befund H3: Vorher stand hier ausschliesslich taskkill.
                            # Auf Linux warf das FileNotFoundError -> der Prozess lief
                            # weiter und die Temp-Datei blieb liegen.
                            if sys.platform == "win32":
                                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                               capture_output=True, timeout=10)
                            else:
                                proc.kill()
                            try:
                                proc.communicate(timeout=5)
                            except Exception:
                                pass
                            if os.path.exists(temp_name):
                                os.unlink(temp_name)
                            result = {"status": "error", "message": "Timeout (Infinite Loop erkannt) - Prozessbaum terminiert."}
                        else:
                            if os.path.exists(temp_name): os.unlink(temp_name)
                            if res_code == 0:
                                result = {"status": "success", "data": f"Klasse {class_name} erfolgreich syntaktisch geprueft."}
                            else:
                                result = {"status": "error", "message": f"Syntax/Runtime Error:\n{stderr or stdout}"}
                    except Exception as e:
                        if os.path.exists(temp_name): os.unlink(temp_name)
                        result = {"status": "error", "message": str(e)}
                else:
                    result = {"status": "error", "message": "No code provided for execution."}
            
            else:
                result = {"status": "error", "message": f"Unknown task type: {task_type}"}
        except Exception as e:
            result = {"status": "error", "message": str(e)}
            
        # Submit result
        try:
            requests.post(f"{DISTRIBUTED_CORE_URL}/submit_result?node_ip={self.node_id}", json={
                "task_id": task_id,
                "result": result
            }, headers=HEADERS, timeout=5)
            logger.info(f"{self.node_id} submitted result for {task_id}")
        except Exception as e:
            logger.error(f"{self.node_id} failed to submit result: {e}")

class SwarmOrchestrator:
    def __init__(self, max_workers=1000):
        self.workers = []
        self.max_workers = max_workers

    def run(self):
        logger.info("Starting Fractal Swarm Orchestrator...")
        # Start initial worker
        self.spawn_worker()
        
        while True:
            try:
                resp = requests.get(f"{DISTRIBUTED_CORE_URL}/queue_size", headers=HEADERS, timeout=5)
                if resp.status_code == 200:
                    q_size = resp.json().get("size", 0)
                    active_workers = len([w for w in self.workers if w.is_alive()])
                    
                    if q_size > active_workers and active_workers < self.max_workers:
                        needed = min(q_size - active_workers, 10)  # Spawn in batches of 10 max at once
                        for _ in range(needed):
                            self.spawn_worker()
                        if needed > 0:
                            logger.info(f"[FRACTAL SWARM] Queue: {q_size}. Spawning {needed} new agents. Total active: {active_workers + needed}")
                            
                # Cleanup dead threads
                self.workers = [w for w in self.workers if w.is_alive()]
            except Exception as e:
                pass
            time.sleep(1)

    def spawn_worker(self):
        w = MicroWorker(len(self.workers))
        w.start()
        self.workers.append(w)

if __name__ == "__main__":
    orchestrator = SwarmOrchestrator()
    try:
        orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Shutting down Fractal Swarm.")
