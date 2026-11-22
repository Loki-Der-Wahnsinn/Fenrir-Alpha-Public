import datetime
import json
import os
import shutil
import zipfile


_EXCLUDED_PARTS = {"__pycache__", ".git", ".gemini", "core_snapshots", "memory", "lessons"}
_EXCLUDED_NAMES = {".env", "config.json", "credentials.json", "token.json", "secrets.json"}


def trigger_master_consolidation(core):
    """Creates a clean code snapshot while excluding secrets and runtime memory directories."""
    workspace = core.workspace
    skills_dir = os.path.join(workspace, "skills")
    core_lib_dir = os.path.join(workspace, "core_lib")
    os.makedirs(core_lib_dir, exist_ok=True)

    if os.path.exists(skills_dir):
        for filename in os.listdir(skills_dir):
            if filename.endswith(".py"):
                src = os.path.join(skills_dir, filename)
                dst = os.path.join(core_lib_dir, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

    config_path = getattr(core, "config_path", "")
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["version"] = "12.0 Base"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

    backup_folder = os.path.join(workspace, "core_snapshots", "Fenrir_V12_Base_Master")
    os.makedirs(backup_folder, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = os.path.join(backup_folder, f"Fenrir_V12_Base_{timestamp}.zip")

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_PARTS]
            for file in files:
                if file in _EXCLUDED_NAMES or file.startswith(".env.") or file.endswith((".key", ".pem", ".log")):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, workspace)
                zipf.write(file_path, arcname)

    core.brain_state["v12_base_consolidated"] = True
    core._save_brain_state()
