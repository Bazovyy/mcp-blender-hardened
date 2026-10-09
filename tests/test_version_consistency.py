from pathlib import Path
import ast,re,runpy,tomllib
ROOT=Path(__file__).resolve().parents[1]

def version_source():
    ns=runpy.run_path(str(ROOT/'addon'/'blender_mcp_addon'/'_version.py'))
    return ns['__version__'],tuple(ns['VERSION_TUPLE'])

def test_hatch_and_addon_share_single_version_source():
    data=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    project=data['project'];assert 'version' not in project
    assert 'version' in project.get('dynamic',[])
    assert data['tool']['hatch']['version']['path']=='addon/blender_mcp_addon/_version.py'
    version,vt=version_source();assert version=='0.5.0';assert vt==(0,5,0)
    addon=(ROOT/'addon'/'blender_mcp_addon'/'__init__.py').read_text(encoding='utf-8')
    assert 'from ._version import VERSION_TUPLE, __version__' in addon
    assert '"version": VERSION_TUPLE' in addon
    assert 'version %s", __version__' in addon

def test_packager_uses_same_version_source():
    version,_=version_source();ns=runpy.run_path(str(ROOT/'scripts'/'package_addon.py'))
    assert ns['get_version']()==version

def test_package_metadata_description_matches_tool_surface():
    data=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))
    assert '232 tools' in data['project']['description']