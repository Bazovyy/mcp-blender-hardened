import subprocess

from mcp_blender.server import TOOLS
from tests.qualification.run_blender_case import process_passed, run_blender_case
from tests.qualification.tool_manifest import build_manifest, discover_mcp_tool_names


def test_manifest_covers_every_mcp_tool_exactly_once():
    tool_names = [tool.name for tool in TOOLS]
    manifest_names = [case.name for case in build_manifest()]
    assert len(manifest_names) == len(set(manifest_names)), "manifest contains duplicate tool entries"
    assert set(manifest_names) == set(tool_names)
    assert discover_mcp_tool_names() == tool_names


def test_manifest_has_no_silent_external_holes():
    for case in build_manifest():
        assert case.risk in {"read", "bounded_mutation", "context_heavy", "blocking", "external"}
        if case.risk == "external":
            assert case.skip_external, f"{case.name} must state why live E2E is skipped"


def test_process_passed_rejects_python_and_native_crash_exits():
    assert process_passed(subprocess.CompletedProcess([], 0, stdout="MCP_QUALIFICATION_PASS {}", stderr=""))
    assert not process_passed(subprocess.CompletedProcess([], 1, stdout="", stderr=""))
    assert not process_passed(subprocess.CompletedProcess([], -1073741819, stdout="", stderr=""))
    assert not process_passed(subprocess.CompletedProcess([], 0, stdout="", stderr="traceback"))


def test_isolated_runner_executes_read_only_case():
    proc = run_blender_case("blender_get_version", timeout=20)
    assert process_passed(proc), proc.stdout + proc.stderr
    assert '"status": "PASS"' in proc.stdout