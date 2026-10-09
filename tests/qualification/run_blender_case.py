from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.qualification.tool_manifest import get_case

DEFAULT_BLENDER = Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe")
PASS_SENTINEL = "MCP_QUALIFICATION_PASS"
NATIVE_CRASH_EXIT = -1073741819


def process_passed(proc: subprocess.CompletedProcess[str]) -> bool:
    return proc.returncode == 0 and PASS_SENTINEL in (proc.stdout or "")


def run_blender_case(
    case_name: str,
    blender_executable: str | Path | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    get_case(case_name)
    blender = Path(blender_executable or os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))
    command = [
        str(blender), "--background", "--factory-startup",
        "--python", str(Path(__file__).resolve()), "--", "--execute-case", case_name,
    ]
    return subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, check=False)


def _execute_case(case_name: str) -> int:
    sys.path.insert(0, str(REPO_ROOT / "addon"))
    case = get_case(case_name)
    if case.skip_external:
        print(PASS_SENTINEL + " " + json.dumps({"status": "SKIP_EXTERNAL", "reason": case.skip_external}))
        return 0
    from blender_mcp_addon.handlers import CommandHandlers
    fixture = case.fixture_factory() if case.fixture_factory else None
    try:
        result = CommandHandlers().handle(case.name.removeprefix("blender_"), case.payload_factory())
        if case.assert_result:
            case.assert_result(result)
        print(PASS_SENTINEL + " " + json.dumps({"status": "PASS", "result": result}, default=str))
        return 0
    finally:
        if case.cleanup:
            case.cleanup()
        del fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-case")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    if not args.execute_case:
        parser.error("--execute-case is required when run as a script")
    return _execute_case(args.execute_case)


if __name__ == "__main__":
    raise SystemExit(main())