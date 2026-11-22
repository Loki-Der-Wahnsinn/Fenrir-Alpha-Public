import json
import zipfile

import pytest

from tools.copilot_jspace import CopilotJSpace


def test_jspace_discovers_bausteine_and_updates_ltm_and_epigenetics(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "sample_block.py").write_text(
        "class SampleBlock:\n    pass\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )

    jspace = CopilotJSpace(str(tmp_path))
    discovery = jspace.discover_bausteine(("tools",))
    assert "tools/sample_block.py" in discovery["bausteine"]
    assert discovery["bausteine"]["tools/sample_block.py"]["classes"] == ["SampleBlock"]
    assert discovery["bausteine"]["tools/sample_block.py"]["functions"] == ["helper"]

    jspace.activate_axiom("AXIOM_TEST", "Verify before reporting", skill_name="sample_skill.py")
    jspace.record_ltm("E-1", "Sample verified", ["pytest PASS"], bausteine=["tools/sample_block.py"])
    jspace.record_ltm("E-1", "Sample verified", ["pytest PASS"])  # deduplicates

    ctx = jspace.get_active_context()
    assert ctx["ltm_entries"] == 1
    assert "AXIOM_TEST" in ctx["active_axioms"]
    assert "sample_skill.py" in ctx["active_skills"]


def test_jspace_skill_creator_validates_sandbox_before_writing(tmp_path):
    jspace = CopilotJSpace(str(tmp_path))

    with pytest.raises(ValueError):
        jspace.compose_skill("../escape", "bad", "class Bad:\n    pass\n")

    with pytest.raises(ValueError, match="Sandbox evaluation failed"):
        jspace.compose_skill("broken_skill", "broken", "raise RuntimeError('fail')\n")

    assert not (tmp_path / "skills" / "broken_skill.py").exists()

    (tmp_path / "tools").mkdir(exist_ok=True)
    (tmp_path / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "tools" / "demo_block.py").write_text("VALUE = 42\n", encoding="utf-8")
    result = jspace.compose_skill(
        "topology_check_skill",
        "Checks module graph safety",
        "from tools.demo_block import VALUE\n\nclass TopologyCheckSkill:\n    def run(self):\n        return {'ok': VALUE}\n",
        bausteine=["tools/demo_block.py"],
    )
    assert result["status"] == "created"
    assert (tmp_path / "skills" / "topology_check_skill.py").is_file()
    ltm = json.loads((tmp_path / "memory" / "copilot_langzeit.json").read_text(encoding="utf-8"))
    assert ltm["entries"][0]["bausteine"] == ["tools/demo_block.py"]


def test_jspace_packages_valid_skill_archive(tmp_path):
    jspace = CopilotJSpace(str(tmp_path))
    archive = jspace.package_skill_archive(
        "fenrir-jspace-copilot",
        "Copilot J-Space functional structure and verified skill builder.",
        "# Fenrir Copilot J-Space\n\nVerified workflow.",
        tmp_path / "fenrir-jspace-copilot.skill",
    )
    with zipfile.ZipFile(archive, "r") as zf:
        content = zf.read("fenrir-jspace-copilot/SKILL.md").decode("utf-8")
    assert "name: fenrir-jspace-copilot" in content
    assert "# Fenrir Copilot J-Space" in content
