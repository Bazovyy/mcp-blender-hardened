from pathlib import Path
import importlib.util,sys,pytest
ROOT=Path(__file__).resolve().parents[1]
def load():
 p=ROOT/'addon'/'blender_mcp_addon'/'file_policy.py';s=importlib.util.spec_from_file_location('file_policy_under_test',p);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m

def test_prepare_output_refuses_existing_without_overwrite(tmp_path):
 m=load();p=tmp_path/'x.bin';p.write_bytes(b'old')
 with pytest.raises(m.FilePolicyError) as e:m.prepare_output_path(str(p),overwrite=False)
 assert e.value.code=='file_exists';assert p.read_bytes()==b'old'

def test_prepare_output_normalizes_and_creates_parent(tmp_path):
 m=load();raw=tmp_path/'a'/'..'/'out'/'x.bin';got=m.prepare_output_path(str(raw),overwrite=False)
 assert Path(got).is_absolute();assert Path(got).parent.exists();assert Path(got)==(tmp_path/'out'/'x.bin').resolve()

def test_prepare_output_allows_explicit_overwrite(tmp_path):
 m=load();p=tmp_path/'x.bin';p.write_bytes(b'old');got=m.prepare_output_path(str(p),overwrite=True);assert Path(got)==p.resolve()
