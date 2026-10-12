from __future__ import annotations
import ast,copy,json
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Callable
PayloadFactory=Callable[[],dict[str,Any]]
@dataclass(frozen=True)
class ToolCase:
    name:str
    risk:str
    payload_factory:PayloadFactory
    status:str
    reason:str|None=None
    skip_external:str|None=None
    allowed_error_codes:tuple[str,...]=()

def _server_path()->Path:return Path(__file__).resolve().parents[2]/'src'/'mcp_blender'/'server.py'
def _cases_path()->Path:return Path(__file__).with_name('cases.json')
def discover_mcp_tool_names(server_path:Path|None=None)->list[str]:
    path=server_path or _server_path();tree=ast.parse(path.read_text(encoding='utf-8-sig'),filename=str(path));names=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Name) or node.func.id!='Tool':continue
        for kw in node.keywords:
            if kw.arg=='name' and isinstance(kw.value,ast.Constant) and isinstance(kw.value.value,str):names.append(kw.value.value);break
    return names

def build_manifest()->list[ToolCase]:
    raw=json.loads(_cases_path().read_text(encoding='utf-8'))
    out=[]
    for entry in raw:
        payload=entry.get('payload',{})
        out.append(ToolCase(name=entry['name'],risk=entry['risk'],status=entry['status'],reason=entry.get('reason'),skip_external=entry.get('reason') if entry['status']=='SKIP_EXTERNAL' else None,payload_factory=lambda p=payload:copy.deepcopy(p),allowed_error_codes=tuple(entry.get('allowed_error_codes',()))))
    return out

def get_case(name:str)->ToolCase:
    matches=[c for c in build_manifest() if c.name==name]
    if len(matches)!=1:raise KeyError(f'Expected exactly one manifest case for {name!r}, found {len(matches)}')
    return matches[0]