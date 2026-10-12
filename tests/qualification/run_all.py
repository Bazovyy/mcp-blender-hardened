from __future__ import annotations
import argparse,json,subprocess,time,sys
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))
from tests.qualification.run_blender_case import process_passed,run_blender_case,PASS_SENTINEL
from tests.qualification.tool_manifest import build_manifest

def parse_status(stdout):
    for line in (stdout or '').splitlines():
        if line.startswith(PASS_SENTINEL):
            try:return json.loads(line[len(PASS_SENTINEL):].strip())
            except Exception:return None
    return None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='tests/qualification/results.json');ap.add_argument('--risk',action='append');args=ap.parse_args()
    cases=[c for c in build_manifest() if not args.risk or c.risk in args.risk];results=[];started=time.time();local=[c for c in cases if c.status!='SKIP_EXTERNAL'];done=0
    for case in cases:
        if case.status=='SKIP_EXTERNAL':
            results.append({'name':case.name,'status':'SKIP_EXTERNAL','reason':case.reason,'risk':case.risk});continue
        timeout=120 if case.risk=='blocking' else 45
        try:proc=run_blender_case(case.name,timeout=timeout);ok=process_passed(proc);parsed=parse_status(proc.stdout)
        except subprocess.TimeoutExpired as e:
            results.append({'name':case.name,'status':'FAIL','risk':case.risk,'reason':f'timeout after {timeout}s'});print('FAIL',case.name,'TIMEOUT',flush=True);done+=1;continue
        if ok and parsed and parsed.get('status')=='PASS':status='PASS';reason=None
        else:
            status='FAIL';text=((proc.stdout or '')+'\n'+(proc.stderr or '')).strip();reason=text[-4000:];print('FAIL',case.name,'rc=',proc.returncode,'\n',reason[-1200:],flush=True)
        results.append({'name':case.name,'status':status,'risk':case.risk,'reason':reason});done+=1
        if done%20==0:print(f'PROGRESS {done}/{len(local)} elapsed={time.time()-started:.1f}s',flush=True)
    Path(args.output).write_text(json.dumps(results,indent=2),encoding='utf-8')
    counts={s:sum(r['status']==s for r in results) for s in ('PASS','FAIL','SKIP_EXTERNAL')};print('SUMMARY',counts,'elapsed',round(time.time()-started,1),flush=True)
    return 1 if counts['FAIL'] else 0
if __name__=='__main__':raise SystemExit(main())