from __future__ import annotations
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
def load_module():
    path=ROOT/'addon'/'blender_mcp_addon'/'temp_assets.py'
    spec=importlib.util.spec_from_file_location('test_temp_assets_module',path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod);return mod

def test_ttl_boundaries_and_user_owned_protection(tmp_path):
    m=load_module(); now=[1000.0]
    mgr=m.TempAssetManager(tmp_path,ttl_seconds=600,max_bytes=1024,clock=lambda:now[0],session_id='s')
    owned=mgr.new_path(prefix='owned_',suffix='.bin');owned.write_bytes(b'abc');mgr.register(owned)
    explicit=tmp_path/'explicit.bin';explicit.write_bytes(b'user');mgr.register(explicit,user_owned=True)
    now[0]=1599; assert mgr.cleanup_expired()==0 and owned.exists() and explicit.exists()
    now[0]=1600; assert mgr.cleanup_expired()==1 and not owned.exists() and explicit.exists()

def test_cap_evicts_oldest_managed_only(tmp_path):
    m=load_module(); now=[0.0]
    mgr=m.TempAssetManager(tmp_path,ttl_seconds=600,max_bytes=10,clock=lambda:now[0],session_id='s')
    a=mgr.new_path(prefix='a');a.write_bytes(b'a'*6);mgr.register(a)
    now[0]=1; b=mgr.new_path(prefix='b');b.write_bytes(b'b'*6);mgr.register(b)
    assert not a.exists() and b.exists()

def test_default_limits_match_design(tmp_path):
    m=load_module();mgr=m.TempAssetManager(tmp_path,session_id='s')
    assert mgr.ttl_seconds==600 and mgr.max_bytes==1_073_741_824
