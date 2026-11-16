"""Session memory: one JSONL record per candidate."""
import json
from pathlib import Path

RECORD_FIELDS = (
    "id", "parent_id", "blocks", "values", "protocol_version", "status",
    "metrics", "violations", "rationale", "change_type",
)


class SessionMemory:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict) -> None:
        missing = [field for field in RECORD_FIELDS if field not in record]
        if missing:
            raise ValueError(f"memory record missing {missing}")
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def records(self) -> list[dict]:
        if not self.path.is_file():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
