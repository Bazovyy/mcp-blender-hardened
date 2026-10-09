"""Ownership-aware temporary asset lifecycle for the hardened Blender bridge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import tempfile
import time
from typing import Callable
from uuid import uuid4


@dataclass(slots=True)
class AssetRecord:
    path: Path
    created_at: float
    user_owned: bool = False


class TempAssetManager:
    def __init__(self, root, ttl_seconds=600, max_bytes=1_073_741_824, *, clock: Callable[[], float]=time.time, session_id: str | None=None):
        self.root=Path(root).resolve()
        self.ttl_seconds=int(ttl_seconds)
        self.max_bytes=int(max_bytes)
        self.clock=clock
        self.session_id=session_id or f"{os.getpid()}-{uuid4().hex[:10]}"
        self.session_root=(self.root/self.session_id).resolve()
        self.session_root.mkdir(parents=True,exist_ok=True)
        self._records: dict[Path,AssetRecord]={}
        self._next_cleanup_at=self.clock()+60.0

    def new_path(self, *, prefix='asset_', suffix='') -> Path:
        return self.session_root/f"{prefix}{uuid4().hex}{suffix}"

    def new_dir(self, *, prefix='dir_') -> Path:
        path=self.new_path(prefix=prefix)
        path.mkdir(parents=True,exist_ok=False)
        self.register(path)
        return path

    def _inside_session(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.session_root)
            return True
        except ValueError:
            return False

    def register(self, path, *, user_owned=False) -> Path:
        path=Path(path).resolve()
        if not user_owned and not self._inside_session(path):
            raise ValueError(f"Managed temp asset must be inside session root: {path}")
        self._records[path]=AssetRecord(path=path,created_at=self.clock(),user_owned=bool(user_owned))
        if not user_owned:
            self.enforce_cap()
        return path

    def is_managed(self, path) -> bool:
        record=self._records.get(Path(path).resolve())
        return bool(record is not None and not record.user_owned)

    def _size(self, path: Path) -> int:
        if not path.exists(): return 0
        if path.is_file():
            try: return path.stat().st_size
            except OSError: return 0
        total=0
        for child in path.rglob('*'):
            if child.is_file():
                try: total+=child.stat().st_size
                except OSError: pass
        return total

    def _delete(self, path: Path) -> bool:
        if not path.exists(): return False
        try:
            if path.is_dir(): shutil.rmtree(path)
            else: path.unlink()
            return True
        except OSError:
            return False

    def cleanup_expired(self, now=None) -> int:
        now=self.clock() if now is None else float(now)
        removed=0
        for path,record in list(self._records.items()):
            if record.user_owned: continue
            if now-record.created_at < self.ttl_seconds: continue
            if self._delete(path): removed+=1
            self._records.pop(path,None)
        return removed

    def enforce_cap(self) -> int:
        managed=[record for record in self._records.values() if not record.user_owned and record.path.exists()]
        total=sum(self._size(record.path) for record in managed)
        removed=0
        for record in sorted(managed,key=lambda r:r.created_at):
            if total<=self.max_bytes: break
            size=self._size(record.path)
            if self._delete(record.path):
                total=max(0,total-size);removed+=1
            self._records.pop(record.path,None)
        return removed

    def startup_cleanup(self, now=None) -> int:
        now=self.clock() if now is None else float(now)
        removed=0
        if not self.root.exists(): return 0
        for child in self.root.iterdir():
            if child.resolve()==self.session_root: continue
            try: age=now-child.stat().st_mtime
            except OSError: continue
            if age>=self.ttl_seconds and self._delete(child): removed+=1
        return removed

    def maybe_cleanup(self) -> int:
        now=self.clock()
        if now<self._next_cleanup_at: return 0
        removed=self.cleanup_expired(now)+self.enforce_cap()
        self._next_cleanup_at=now+60.0
        return removed


_default_manager: TempAssetManager | None=None
def get_temp_asset_manager() -> TempAssetManager:
    global _default_manager
    if _default_manager is None:
        root=Path(tempfile.gettempdir())/'mcp-blender'
        _default_manager=TempAssetManager(root)
        _default_manager.startup_cleanup()
    return _default_manager
