#!/usr/bin/env python3
"""Build a deterministic SHA-256 inventory for the code-only release."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "CODE_SOURCE_MANIFEST.sha256"
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".venv", "venv"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return (
        path != OUTPUT
        and not any(part in EXCLUDED_PARTS for part in relative.parts)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
    )


def main() -> None:
    files = sorted(
        (path for path in ROOT.rglob("*") if path.is_file() and included(path)),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    lines = [
        f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in files
    ]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"CODE_SOURCE_MANIFEST_ENTRIES={len(lines)}")
    print(f"CODE_SOURCE_MANIFEST_SHA256={sha256(OUTPUT)}")


if __name__ == "__main__":
    main()

