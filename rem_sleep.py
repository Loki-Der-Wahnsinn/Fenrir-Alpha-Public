import os
import time
import json
import re
import requests
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger("rem_sleep")
from sandbox_evaluator import SandboxEvaluator

# Config
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
NATIVE_BRAIN_URL = "http://127.0.0.1:8001/generate"
MUTATION_COUNT = 3  # "Klon-Kaempfe" pro Fehler
QUARANTINE_DIR = os.path.join(CORE_DIR, "memory", "quarantine", "dreams")

os.makedirs(QUARANTINE_DIR, exist_ok=True)

def extract_code(llm_response: str) -> str:
    code_match = re.search(r"```(?:python)?\s*(.*?)\s*```", llm_response, re.DOTALL)
    if code_match:
        return code_match.group(1).strip()
    return ""

def llm_mutate(prompt: str) -> str:
    try:
        resp = requests.post(
            NATIVE_BRAIN_URL, 
            json={"prompt": prompt, "temperature": 0.8, "max_tokens": 4096, "role": "optimizer"}, 
            timeout=300
        )
        if resp.status_code == 200:
            return resp.json().get("response", "")
    except Exception as e:
        logger.error(f"[REM-SLEEP] Ministerium nicht erreichbar: {e}")
    return ""

def trigger_rem_sleep_cycle():
    logger.info("[REM-SLEEP] System geht in den Tiefschlaf (Offline-Modus). Aktiviere Traum-Evolution...")
    
    # Für den Anfang mutieren wir Skills, um eine Lobotomie des Kerns zu verhindern
    target_script = "skills/dummy_skill.py" 
    target_path = os.path.join(CORE_DIR, target_script)
    
    # Erstelle ein Dummy-Skill falls keins existiert (zum Testen der Evolution)
    if not os.path.exists(target_path):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("def do_something():\n    bad_code_that_fails_miserably\n")
            
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            code_content = f.read()
    except Exception as e:
        logger.error(f"Konnte {target_script} nicht lesen: {e}")
        return

    logger.info(f"[REM-SLEEP] Traum initiiert für: {target_script}. Generiere {MUTATION_COUNT} Klone...")
    
    prompt = (
        f"Du bist Fenrir im REM-Schlaf. Der folgende Code hat heute einen Fehler verursacht oder ist ineffizient.\n"
        f"Deine Aufgabe: Träume eine völlig neue, fehlerfreie und hocheffiziente Version dieses Codes.\n"
        f"Code ({target_script}):\n```python\n{code_content}\n```\n\n"
        f"Gib NUR den perfekten Python-Code im Block ```python ... ``` zurück. Keine Einleitung, kein Text."
    )

    evaluator = SandboxEvaluator(CORE_DIR)
    best_score = -999.0
    best_code = None
    
    # 2. Deathmatch
    for i in range(MUTATION_COUNT):
        logger.info(f"[REM-SLEEP] Generiere Klon {i+1}/{MUTATION_COUNT}...")
        response = llm_mutate(prompt)
        mutated_code = extract_code(response)
        
        if not mutated_code or len(mutated_code) < 20:
            logger.warning(f"[REM-SLEEP] Klon {i+1} war eine Halluzination (Stub). Stirbt im Traum.")
            continue
            
        variant_path = os.path.join(QUARANTINE_DIR, f"dream_variant_{i+1}.py")
        with open(variant_path, "w", encoding="utf-8") as f:
            f.write(mutated_code)
            
        logger.info(f"[REM-SLEEP] Teste Klon {i+1} in der Deathmatch-Sandbox...")
        result = evaluator._evaluate_locally(mutated_code, f"DreamVariant{i+1}")
        
        score = result.get("dopamine_shift", -1.0)
        status = result.get("status", "error")
        logger.info(f"[REM-SLEEP] Klon {i+1} Ergebnis: {status} (Score: {score})")
        
        if status == "success" and score > best_score:
            best_score = score
            best_code = mutated_code

    # 3. Awakening
    if best_code and best_score > 0:
        logger.info(f"[REM-SLEEP] EIN KLON HAT ÜBERLEBT! Bester Score: {best_score}. Integriere in die Wach-Matrix...")
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(best_code)
            logger.info(f"[REM-SLEEP] {target_script} erfolgreich überschrieben! Fenrir erwacht stärker.")
        except Exception as e:
            logger.error(f"[REM-SLEEP] Integrationsfehler beim Aufwachen: {e}")
    else:
        logger.info("[REM-SLEEP] Alle Klone sind im Traum gestorben (Syntaxfehler / Timeouts). Keine Änderungen vorgenommen.")

if __name__ == "__main__":
    trigger_rem_sleep_cycle()
