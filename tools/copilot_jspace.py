"""Copilot J-Space (E1-E3-R), Baustein-Index, and verified Skill Creator."""

import argparse
import ast
import json
import os
from pathlib import Path
import socket
import sys
import time
import zipfile

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

if __package__:
    from .mutation_target import reject_link_or_reparse, validate_mutation_filename
    from .topology_features import dependency_graph, topology_features
else:
    from mutation_target import reject_link_or_reparse, validate_mutation_filename
    from topology_features import dependency_graph, topology_features

from sandbox_evaluator import SandboxEvaluator


DEFAULT_AXIOMS = {
    "AXIOM_E1_LTM_PRESERVATION": "Langzeitgedaechtnis atomar und verlustfrei ergaenzen, niemals pauschal ueberschreiben.",
    "AXIOM_E2_EVIDENCE_FIRST": "Nur belegte Messungen (Test, Hash, Socket, HTTP) als verified markieren.",
    "AXIOM_E3_SANDBOX_BEFORE_SAVE": "Jeder generierte Skill durchlaeuft Namenspruefung, AST-Check und lokale Sandbox vor Ablage.",
    "AXIOM_R_LOOPBACK_GUARD": "Lokale HTTP-Dienste auf 127.0.0.1 mit Host/Origin-Pruefung absichern.",
}


def _atomic_write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


class CopilotJSpace:
    """Connects E1 (LTM), E2 (Epigenetics), E3 (Topology/Bausteine), and R (Feedback)."""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()
        self.memory_dir = self.workspace / "memory"
        self.skills_dir = self.workspace / "skills"
        self.ltm_path = self.memory_dir / "copilot_langzeit.json"
        self.epigen_path = self.memory_dir / "copilot_epigenetics.json"
        self.shared_epigen_path = self.memory_dir / "epigenetics.json"
        self.evaluator = SandboxEvaluator(str(self.workspace))

    def load_ltm(self) -> dict:
        if self.ltm_path.is_file():
            try:
                data = json.loads(self.ltm_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "stand": time.strftime("%Y-%m-%d"),
            "knoten": "Copilot",
            "rolle": "Struktur, Tests, Topologie und sichere Modul-Integration",
            "offen": [],
            "gelernt": [],
            "entries": [],
        }

    def record_ltm(self, entry_id: str, summary: str, evidence: list[str], bausteine: list[str] = None) -> dict:
        if not entry_id or not summary or not evidence:
            raise ValueError("entry_id, summary, and non-empty evidence are required.")
        ltm = self.load_ltm()
        ltm["stand"] = time.strftime("%Y-%m-%d")
        entries = ltm.setdefault("entries", [])
        if not any(item.get("id") == entry_id for item in entries):
            entries.append(
                {
                    "id": entry_id,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "summary": summary,
                    "evidence": list(evidence),
                    "bausteine": list(bausteine or []),
                }
            )
        gelernt = ltm.setdefault("gelernt", [])
        if summary not in gelernt:
            gelernt.append(summary)
        _atomic_write_json(self.ltm_path, ltm)
        return ltm

    def load_epigenetics(self) -> dict:
        if self.epigen_path.is_file():
            try:
                data = json.loads(self.epigen_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {
            "knoten": "Copilot",
            "axioms": dict(DEFAULT_AXIOMS),
            "active_skills": [],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def activate_axiom(self, axiom_id: str, rule: str, skill_name: str = None) -> dict:
        if not axiom_id or not rule:
            raise ValueError("axiom_id and rule are required.")
        state = self.load_epigenetics()
        state.setdefault("axioms", {})[axiom_id] = rule
        if skill_name:
            skills = state.setdefault("active_skills", [])
            if skill_name not in skills:
                skills.append(skill_name)
        state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _atomic_write_json(self.epigen_path, state)
        return state

    def get_active_context(self) -> dict:
        ltm = self.load_ltm()
        epigen = self.load_epigenetics()
        shared_keys = []
        if self.shared_epigen_path.is_file():
            try:
                shared_data = json.loads(self.shared_epigen_path.read_text(encoding="utf-8"))
                if isinstance(shared_data, dict):
                    shared_keys = sorted(shared_data.keys())[:20]
            except Exception:
                shared_keys = []
        return {
            "ltm_entries": len(ltm.get("entries", [])),
            "ltm_gelernt": len(ltm.get("gelernt", [])),
            "active_axioms": epigen.get("axioms", {}),
            "active_skills": epigen.get("active_skills", []),
            "shared_epigenetics_keys": shared_keys,
        }

    def discover_bausteine(self, relative_dirs: tuple[str, ...] = ("tools", "skills")) -> dict:
        catalog = {}
        topology_summary = {}
        for rel in relative_dirs:
            folder = self.workspace / rel
            if not folder.is_dir():
                continue
            try:
                vertices, edges = dependency_graph(folder)
                topo = topology_features(vertices, edges)
                topology_summary[rel] = {
                    "modules": topo["modules"],
                    "directed_imports": topo["directed_imports"],
                    "h0_essential": topo["h0_essential"],
                    "circular_import_groups": topo["circular_import_groups"],
                }
            except Exception:
                pass
            for py_file in sorted(folder.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    tree = ast.parse(py_file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                classes = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
                functions = [
                    n.name for n in tree.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
                ]
                catalog[f"{rel}/{py_file.name}"] = {
                    "classes": classes,
                    "functions": functions,
                }
        return {"bausteine": catalog, "topology": topology_summary}

    def compose_skill(
        self,
        skill_name: str,
        description: str,
        code: str,
        bausteine: list[str] = None,
    ) -> dict:
        filename = validate_mutation_filename(skill_name)
        reject_link_or_reparse(self.workspace)
        if self.skills_dir.exists():
            reject_link_or_reparse(self.skills_dir)
        target_path = self.skills_dir / filename
        reject_link_or_reparse(target_path)

        try:
            ast.parse(code)
        except SyntaxError as exc:
            raise ValueError(f"Generated skill has invalid syntax: {exc}") from exc

        if hasattr(self.evaluator, "_evaluate_locally"):
            eval_result = self.evaluator._evaluate_locally(code, Path(filename).stem)
        else:
            eval_result = self.evaluator.evaluate_code(code, Path(filename).stem)
        if eval_result.get("status") != "success":
            detail = eval_result.get("stderr") or eval_result.get("stdout") or eval_result.get("message")
            raise ValueError(f"Sandbox evaluation failed: {detail}")

        self.skills_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(".py.tmp")
        tmp_path.write_text(code, encoding="utf-8")
        os.replace(tmp_path, target_path)

        self.activate_axiom(
            f"SKILL_{Path(filename).stem.upper()}",
            description,
            skill_name=filename,
        )
        self.record_ltm(
            entry_id=f"SKILL_{Path(filename).stem}",
            summary=f"Verifizierter Skill erstellt: {filename} ({description})",
            evidence=[f"SandboxEvaluator PASS: {target_path}"],
            bausteine=bausteine or [],
        )
        return {
            "status": "created",
            "path": str(target_path),
            "filename": filename,
            "bausteine": list(bausteine or []),
        }

    def package_skill_archive(self, skill_slug: str, description: str, body: str, output_path: Path) -> Path:
        if not skill_slug or "/" in skill_slug or "\\" in skill_slug or ".." in skill_slug:
            raise ValueError("Invalid skill slug")
        content = f"---\nname: {skill_slug}\ndescription: {description}\n---\n\n{body.strip()}\n"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_zip = output_path.with_suffix(output_path.suffix + ".tmp")
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{skill_slug}/SKILL.md", content.encode("utf-8"))
        os.replace(tmp_zip, output_path)
        return output_path

    @staticmethod
    def measure_ports(ports: list[int], host: str = "127.0.0.1", timeout: float = 0.25) -> dict:
        results = {}
        for port in ports:
            try:
                with socket.create_connection((host, int(port)), timeout=timeout):
                    results[int(port)] = "open"
            except OSError:
                results[int(port)] = "closed"
        return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=os.getcwd(), help="Fenrir workspace directory")
    parser.add_argument("--inspect", action="store_true", help="Inspect E1/E2/E3 state and Bausteine")
    args = parser.parse_args()

    jspace = CopilotJSpace(args.workspace)
    if args.inspect:
        report = {
            "context": jspace.get_active_context(),
            "bausteine": jspace.discover_bausteine(),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(json.dumps(jspace.get_active_context(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
