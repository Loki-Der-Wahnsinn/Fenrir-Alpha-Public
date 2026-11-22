"""Smoke-Test fuer den gehaerteten Hive. Prueft die Audit-Befunde K1-K5, H1, H2, H4."""
import os, sys, json, time, threading
from pathlib import Path
os.environ["FENRIR_HIVE_TOKEN"] = "test-token-123"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import distributed_core as dc
from fastapi.testclient import TestClient

client = TestClient(dc.app)
H = {"X-Fenrir-Token": "test-token-123"}
BAD = {"X-Fenrir-Token": "falsch"}

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  -> " + detail) if detail and not cond else ""))

print("\n=== K2: Lightweight-Worker Registrierung (vorher 422) ===")
r = client.post("/register_node", json={"node_ip": "worker_1_abc", "status": "idle"}, headers=H)
check("Registrierung ohne 'capabilities' akzeptiert (K2)", r.status_code == 200, f"HTTP {r.status_code} {r.text[:120]}")

r = client.post("/register_node", json={"node_ip": "worker_2_xyz", "status": "idle",
                                        "capabilities": {"execute_code": True}}, headers=H)
check("Registrierung mit capabilities", r.status_code == 200, f"HTTP {r.status_code}")

print("\n=== K4: Auth ===")
r = client.post("/register_node", json={"node_ip": "evil", "capabilities": {}})
check("Ohne Token -> 401 (K4)", r.status_code == 401, f"HTTP {r.status_code}")
r = client.post("/register_node", json={"node_ip": "evil", "capabilities": {}}, headers=BAD)
check("Falscher Token -> 401 (K4)", r.status_code == 401, f"HTTP {r.status_code}")

print("\n=== K1: execute_code nur mit Token + Allowlist ===")
r = client.post("/tasks/submit", json={"task_type": "boese_sache", "payload": {}}, headers=H)
check("Unbekannter task_type -> 400 (K1 Allowlist)", r.status_code == 400, f"HTTP {r.status_code}")
r = client.post("/tasks/submit", json={"task_type": "execute_code", "payload": {"code": "print(1)"}})
check("execute_code ohne Token -> 401", r.status_code == 401, f"HTTP {r.status_code}")

print("\n=== H4: /get_task ist POST, GET verbrennt keine Aufgabe mehr ===")
r = client.get("/get_task", params={"node_ip": "worker_1_abc"}, headers=H)
check("GET /get_task -> 405 (H4)", r.status_code == 405, f"HTTP {r.status_code}")

print("\n=== K5/H5: Queue, Zuweisung, IN_FLIGHT ===")
tid = client.post("/tasks/submit", json={"task_type": "llm_query",
                                         "payload": {"prompt": "hallo"}}, headers=H).json()["task_id"]
r = client.post("/get_task", params={"node_ip": "worker_1_abc"}, headers=H).json()
check("Task zugewiesen", r.get("status") == "assigned", str(r))
check("Task liegt in IN_FLIGHT (H5)", tid in dc.IN_FLIGHT, str(list(dc.IN_FLIGHT)))
check("Knoten ist busy", dc.REGISTERED_NODES["worker_1_abc"]["status"] == "busy")

r = client.post("/submit_result", params={"node_ip": "worker_1_abc"},
                json={"task_id": tid, "result": {"ok": True}}, headers=H)
check("Ergebnis angenommen", r.status_code == 200, f"HTTP {r.status_code}")
check("IN_FLIGHT geleert", tid not in dc.IN_FLIGHT)
r = client.get(f"/tasks/result/{tid}", headers=H).json()
check("Ergebnis abholbar", r.get("status") == "completed", str(r))

print("\n=== H5: Requeue bei Worker-Timeout ===")
dc.TASK_VISIBILITY_TIMEOUT = 0.01
tid2 = client.post("/tasks/submit", json={"task_type": "llm_query", "payload": {}}, headers=H).json()["task_id"]
client.post("/get_task", params={"node_ip": "worker_1_abc"}, headers=H)
time.sleep(0.05)
r = client.post("/get_task", params={"node_ip": "worker_2_xyz"}, headers=H).json()
check("Verwaister Task wurde zurueckgeholt (H5)", r.get("task", {}).get("task_id") == tid2, str(r))

print("\n=== H1: nur noch EINE UI-Route ===")
paths = [r.path for r in dc.app.routes]
check("ui/message/send genau einmal definiert (H1)", paths.count("/ui/message/send") == 1,
      f"{paths.count('/ui/message/send')}x")
client.post("/ui/message/send", json={"message": "test"}, headers=H)
r = client.get("/ui/message/poll_for_core", headers=H).json()
check("Nachricht kommt an (H1, keine gespaltene Queue)", r["messages"] == ["test"], str(r))

print("\n=== K3: fetch_skill liefert keinen fremden Code mehr ===")
dc.TEMP_SKILLS.clear()
dc.TEMP_SKILLS["EchterSkill"] = "class EchterSkill: pass"
r = client.get("/fetch_skill/FalscherName", headers=H)
check("Falscher Name -> 404, kein fremder Code (K3)", r.status_code == 404, f"HTTP {r.status_code} {r.text[:120]}")
r = client.get("/fetch_skill/EchterSkill", headers=H)
check("Richtiger Name -> Code", r.status_code == 200 and "EchterSkill" in r.json().get("code", ""), f"HTTP {r.status_code}")

print("\n=== H2: start_master_api respektiert Port ===")
import inspect
src = inspect.getsource(dc.start_master_api)
check("kein hart verdrahtetes 8000 mehr (H2)", 'args=("0.0.0.0", 8000)' not in src)

print("\n=== H6: Obergrenze COMPLETED_TASKS ===")
check("MAX_COMPLETED_TASKS gesetzt", dc.MAX_COMPLETED_TASKS > 0)

print("\n" + "=" * 60)
ok = sum(1 for _, c, _ in results if c)
print(f"ERGEBNIS: {ok}/{len(results)} Pruefungen bestanden")
fails = [n for n, c, _ in results if not c]
if fails:
    print("FEHLGESCHLAGEN:")
    for f in fails:
        print("  - " + f)
sys.exit(0 if not fails else 1)
