from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def load_jobs():
    path=ROOT/'addon'/'blender_mcp_addon'/'jobs.py'
    spec=importlib.util.spec_from_file_location('test_runtime_jobs',path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod

def test_job_tick_budget_status_and_cancel():
    j=load_jobs(); calls=[]
    rt=j.JobRuntime()
    def step(job):
        calls.append(job.id); return j.JobStep(progress=0.25, delay_seconds=0)
    ids=[rt.submit_job('demo',step) for _ in range(3)]
    assert rt.tick(max_jobs=2,time_budget_ms=100)==2
    assert len(calls)==2 and rt.get_job(ids[0]).status=='running'
    assert rt.cancel_job(ids[2]) is True
    assert rt.get_job(ids[2]).status=='cancelled'

def test_job_completion_and_timeout_are_terminal():
    j=load_jobs(); now=[0.0]
    rt=j.JobRuntime(clock=lambda:now[0])
    done=rt.submit_job('done',lambda job:j.JobStep(done=True,result={'x':1}))
    assert rt.tick(max_jobs=1,time_budget_ms=100)==1
    assert rt.get_job(done).status=='completed' and rt.get_job(done).result=={'x':1}
    pending=rt.submit_job('slow',lambda job:j.JobStep(delay_seconds=5),timeout_seconds=2)
    now[0]=3.0; rt.tick(max_jobs=2,time_budget_ms=100)
    assert rt.get_job(pending).status=='timeout'

def test_delayed_job_does_not_spin_or_sleep():
    j=load_jobs(); now=[0.0]; calls=[]
    rt=j.JobRuntime(clock=lambda:now[0])
    jid=rt.submit_job('poll',lambda job:(calls.append(1) or j.JobStep(delay_seconds=5)))
    rt.tick(max_jobs=4,time_budget_ms=100); rt.tick(max_jobs=4,time_budget_ms=100)
    assert len(calls)==1
    now[0]=5.0; rt.tick(max_jobs=4,time_budget_ms=100); assert len(calls)==2
    assert 'time.sleep' not in (ROOT/'addon'/'blender_mcp_addon'/'jobs.py').read_text(encoding='utf-8')

def test_ai_polling_source_has_no_sleep_loop():
    source=(ROOT/'addon'/'blender_mcp_addon'/'external'/'ai_models.py').read_text(encoding='utf-8')
    assert 'time.sleep' not in source
