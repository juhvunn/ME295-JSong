"""Which part-model files a simulation used, and whether any of them are placeholders.

The SHA-256 is computed on the file text with line endings normalised to LF, so the
same model file hashes the same on Windows and Linux.
"""
import hashlib
from pathlib import Path

import yaml

from pedal_agent.build import load_block
from pedal_agent.config import REPO_ROOT
from pedal_agent.schemas import Candidate, ModelFile

MANIFEST = REPO_ROOT / "models" / "manifest.yaml"


def text_sha256(path: Path) -> str:
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_status(path: Path) -> str:
    path = Path(path).resolve()
    if path.parent != (REPO_ROOT / "models").resolve():
        return "unregistered"
    files = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["files"]
    return files.get(path.name, "unregistered")


def describe(path: Path) -> ModelFile:
    path = Path(path).resolve()
    try:
        shown = path.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        shown = str(path)
    return ModelFile(path=shown, sha256=text_sha256(path), status=file_status(path))


def unvalidated_choices(candidate: Candidate) -> list[str]:
    """'block.param=value' for every choice marked validated: false in block.yaml."""
    out = []
    for blk in candidate.chain:
        _, meta = load_block(blk.block_id)
        for name, spec in meta["params"].items():
            if spec["type"] != "choice":
                continue
            value = blk.params.get(name, spec.get("default"))
            if spec.get("validated", {}).get(value, True) is False:
                out.append(f"{blk.block_id}.{name}={value}")
    return out


def flagged(files: list[ModelFile], unvalidated: list[str]) -> bool:
    return bool(unvalidated) or any(f.status != "validated" for f in files)
