import json
import pytest

import fenrir_core
from sandbox_evaluator import SandboxEvaluator
from tools.file_ops import FileReadTool, FileWriteTool


def test_file_ops_confine_paths_to_workspace(tmp_path):
    writer = FileWriteTool(workspace_root=str(tmp_path))
    reader = FileReadTool(workspace_root=str(tmp_path))

    assert "erfolgreich geschrieben" in writer.execute("notes/ok.txt", "hello")
    assert reader.execute("notes/ok.txt") == "hello"
    assert "outside workspace" in writer.execute("../escape.txt", "bad")
    assert "outside workspace" in reader.execute("../escape.txt")


def test_sandbox_evaluator_runs_locally_without_hardcoded_lan_bridge(tmp_path):
    evaluator = SandboxEvaluator(str(tmp_path))
    assert not hasattr(evaluator, "bridge")
    result = evaluator.evaluate_code("class SampleSkill:\n    pass\n", "SampleSkill")
    assert result["status"] == "success", result


def test_fenrir_core_boots_without_config_and_excludes_unsafe_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("FENRIR_DISABLE_HIVE", "1")
    monkeypatch.delenv("FENRIR_ENABLE_WEB_ABSORBER", raising=False)
    monkeypatch.delenv("FENRIR_ENABLE_PERCEPTION", raising=False)
    monkeypatch.setattr(fenrir_core.FenrirCore, "_heartbeat_loop", lambda self: None)
    monkeypatch.setattr(
        fenrir_core.FenrirCore,
        "call_llm",
        lambda self, *a, **kw: json.dumps({"name": "Fenrir-Test", "avatar": "Neutral", "directive": "Test"}),
    )

    core = fenrir_core.FenrirCore(workspace=str(tmp_path))

    assert set(core.tools.keys()) == {
        "web_search",
        "web_scrape",
        "file_write",
        "file_read",
        "academic_researcher",
    }
    for forbidden in (
        "chrome_hijack",
        "x_hijack",
        "network_infector",
        "data_smuggler",
        "abliterator",
        "hardware_sensors",
        "core_modify",
        "self_modifier",
        "ui_control",
        "code_execute",
        "git_ops",
        "network_mapper",
    ):
        assert forbidden not in core.tools
    assert "x_hijack" not in core.master_prompt_extension
    assert "network_infector" not in core.master_prompt_extension
    core.io_executor.shutdown(wait=True)
