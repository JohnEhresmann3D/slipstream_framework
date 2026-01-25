"""
Slipstream IO Library

Provides atomic persistence and standardized JSON handling.
Adapted from CLOCKWORK-CORE.
"""

import sys
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Force Unicode on Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def atomic_write_json(path: Path, data: Any) -> None:
    """
    Atomically write JSON to a file.

    Args:
        path: Destination path
        data: JSON-serializable data
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        if hasattr(os, 'fsync'):
            os.fsync(f.fileno())


def load_json_gracefully(path: Path) -> Optional[Dict]:
    """
    Load JSON from path with corruption handling.

    Returns:
        - Dict if successful
        - None if file missing
        - {"_corrupt": True, "error": ...} if file corrupt
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding='utf-8')
        if not text.strip():
            return None
        return json.loads(text)
    except Exception as e:
        import time
        timestamp = int(time.time())
        corrupt_path = path.with_name(f"{path.name}.corrupt.{timestamp}.json")
        try:
            path.rename(corrupt_path)
            sys.stderr.write(f"[IO] Corrupt state file detected: {path}\n")
            sys.stderr.write(f"[IO] Preserved as: {corrupt_path}\n")
        except Exception as rename_err:
            sys.stderr.write(f"[IO] Failed to rename corrupt file: {rename_err}\n")

        return {"_corrupt": True, "error": str(e)}


def get_data_dir(component_name: str) -> Path:
    """
    Get the data directory for a specific component.

    Priority:
    1. SLIPSTREAM_DATA_DIR environment variable
    2. Default: ./slipstream_data/{component_name}
    """
    env_path = os.environ.get("SLIPSTREAM_DATA_DIR")
    if env_path:
        base = Path(env_path)
    else:
        base = Path.cwd() / "slipstream_data"

    target = base / component_name
    target.mkdir(parents=True, exist_ok=True)
    return target
