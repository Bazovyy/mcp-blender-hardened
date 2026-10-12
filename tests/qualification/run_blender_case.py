from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))
from tests.qualification.tool_manifest import get_case
DEFAULT_BLENDER=Path(r"C:\SteamLibrary\steamapps\common\Blender\blender.exe")
PASS_SENTINEL='MCP_QUALIFICATION_PASS';NATIVE_CRASH_EXIT=-1073741819

def process_passed(proc:subprocess.CompletedProcess[str])->bool:
    text=(proc.stdout or '')+'\n'+(proc.stderr or '')
    return proc.returncode==0 and PASS_SENTINEL in (proc.stdout or '') and 'Traceback (most recent call last)' not in text and 'EXCEPTION_ACCESS_VIOLATION' not in text

def run_blender_case(case_name:str,blender_executable:str|Path|None=None,timeout:float=60.0)->subprocess.CompletedProcess[str]:
    get_case(case_name);blender=Path(blender_executable or os.environ.get('BLENDER_EXE',DEFAULT_BLENDER));cmd=[str(blender),'--background','--factory-startup','--python',str(Path(__file__).resolve()),'--','--execute-case',case_name]
    return subprocess.run(cmd,cwd=REPO_ROOT,capture_output=True,text=True,timeout=timeout,check=False)

def _result_is_failure(result, allowed_error_codes=())->str|None:
    if isinstance(result,dict):
        if result.get("success") is True or result.get("ok") is True:
            return None
        if result.get("code") in allowed_error_codes:
            return None
        if result.get("success") is False:
            return str(result.get("error") or result.get("message") or result)
        if result.get("ok") is False:
            return str(result.get("error") or result)
        if result.get("error"):
            return str(result.get("error"))
    return None

def _execute_case(case_name:str)->int:
    sys.path.insert(0,str(REPO_ROOT/'addon'));case=get_case(case_name)
    if case.skip_external:
        print(PASS_SENTINEL+' '+json.dumps({'status':'SKIP_EXTERNAL','reason':case.skip_external}));return 0
    from blender_mcp_addon.handlers import CommandHandlers
    from tests.qualification.fixtures import prepare_standard,cleanup_standard,resolve_tokens
    fixture=prepare_standard(case_name)
    try:
        payload=resolve_tokens(case.payload_factory(),fixture);result=CommandHandlers().handle(case.name.removeprefix('blender_'),payload);failure=_result_is_failure(result,case.allowed_error_codes)
        if failure:raise AssertionError(f'{case.name} returned failure: {failure}; payload={payload!r}; result={result!r}')
        print(PASS_SENTINEL+' '+json.dumps({'status':'PASS','result':result},default=str));return 0
    finally:cleanup_standard(fixture)

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument('--execute-case');args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
    if not args.execute_case:parser.error('--execute-case is required')
    return _execute_case(args.execute_case)
if __name__=='__main__':raise SystemExit(main())