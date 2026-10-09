"""Shared output-path policy for user-owned files."""
from __future__ import annotations
from pathlib import Path

class FilePolicyError(Exception):
    def __init__(self, code: str, message: str, *, path: str | None = None):
        super().__init__(message)
        self.code = code
        self.path = path

def prepare_output_path(path: str, *, overwrite: bool = False, create_parent: bool = True) -> str:
    target = Path(path).expanduser().resolve(strict=False)
    if target.exists() and target.is_dir():
        raise FilePolicyError("invalid_output_path", f"Output path is a directory: {target}", path=str(target))
    if target.exists() and not overwrite:
        raise FilePolicyError("file_exists", f"Output already exists; pass overwrite=true to replace it: {target}", path=str(target))
    if create_parent:
        target.parent.mkdir(parents=True, exist_ok=True)
    return str(target)
