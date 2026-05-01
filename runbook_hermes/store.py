from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

class JsonStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str) -> Path:
        return self.root / f"{bucket}.json"

    def read(self, bucket: str) -> Dict[str, Any]:
        path = self._path(bucket)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def write(self, bucket: str, data: Dict[str, Any]) -> None:
        path = self._path(bucket)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def put(self, bucket: str, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        data = self.read(bucket)
        data[key] = value
        self.write(bucket, data)
        return value

    def append_event(self, incident_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self.read("events")
        events = data.setdefault(incident_id, [])
        event = {"event_type": event_type, "payload": payload, "ts": time.time()}
        events.append(event)
        self.write("events", data)
        return event

    def list_bucket(self, bucket: str) -> List[Dict[str, Any]]:
        data = self.read(bucket)
        return list(data.values())
