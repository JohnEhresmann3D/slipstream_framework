from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DecisionLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: str, **details: Any) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **details,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=repr) + "\n")
