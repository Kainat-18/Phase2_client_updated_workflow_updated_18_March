from __future__ import annotations

import re
import zipfile
from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def clean_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\t+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "project"


def is_heading(line: str) -> bool:
    if line.startswith("#"):
        return True
    if len(line) < 80 and line == line.upper() and any(c.isalpha() for c in line):
        return True
    if line.endswith(":") and len(line.split()) <= 12:
        return True
    return False


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"“])', text)
    results = []
    for part in parts:
        chunk = part.strip()
        if chunk:
            results.append(chunk)
    return results


def zip_folder(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(folder.parent))
