import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_dataset(frame, path, manifest):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = frame.to_csv(index=False).encode("utf-8-sig")
    path.write_bytes(payload)
    metadata = dict(manifest, rows=len(frame), sha256=hashlib.sha256(payload).hexdigest())
    path.with_suffix(".manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def read_dataset(path):
    path = Path(path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    metadata_path = path.with_suffix(".manifest.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if metadata.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("데이터가 수집 기록 이후 변경되었습니다. 다시 수집하거나 기록을 갱신하세요.")
    return frame, metadata
