import hashlib
import json
import re
import time
from datetime import date
from pathlib import Path
from threading import Lock

import pandas as pd
import requests
from defusedxml import ElementTree as ET

from mot_analytics.storage import DATA, utc_now, write_dataset

DEFAULT_QUERY = '(ti:"hardware accelerator" OR abs:"hardware accelerator") AND (all:"neural network" OR all:"deep learning")'
DEFAULT_PERIODS = [("2025 상반기", "2025-01-01", "2025-06-30"), ("2026 상반기", "2026-01-01", "2026-06-30")]
NS = {"atom": "http://www.w3.org/2005/Atom", "os": "http://a9.com/-/spec/opensearch/1.1/"}
_lock = Lock()
_last_request = 0.0


def parse_feed(payload, collected_at):
    root = ET.fromstring(payload)
    rows = []
    total = int(root.findtext("os:totalResults", default="0", namespaces=NS))
    for entry in root.findall("atom:entry", NS):
        raw_id = entry.findtext("atom:id", default="", namespaces=NS)
        if "/api/errors" in raw_id:
            raise ValueError("arXiv가 검색 오류를 반환했습니다. 검색식을 확인하세요.")
        version_id = raw_id.split("/abs/")[-1]
        paper_id = re.sub(r"v\d+$", "", version_id)
        def field(name):
            return " ".join(entry.findtext(f"atom:{name}", default="", namespaces=NS).split())
        rows.append({"paper_id": paper_id, "version_id": version_id, "title": field("title"),
                     "abstract": field("summary"), "published": field("published"), "updated": field("updated"),
                     "authors": "; ".join(a.findtext("atom:name", namespaces=NS) or "" for a in entry.findall("atom:author", NS)),
                     "categories": "; ".join(c.get("term", "") for c in entry.findall("atom:category", NS)),
                     "source_url": f"https://arxiv.org/abs/{paper_id}", "collected_at": collected_at})
    return rows, total


def request_feed(params, cache_dir):
    global _last_request
    signature = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw = cache_dir / f"{signature}.xml"
    record = cache_dir / f"{signature}.json"
    if raw.exists() and record.exists():
        metadata = json.loads(record.read_text(encoding="utf-8"))
        payload = raw.read_bytes()
        if hashlib.sha256(payload).hexdigest() != metadata.get("raw_sha256"):
            raise ValueError("arXiv 원본 캐시가 변경되었습니다. 해당 캐시 파일을 확인하세요.")
        return payload, metadata
    # Serial requests, including retries, with >=3 seconds between start times.
    with _lock:
        for attempt in range(3):
            time.sleep(max(0, 3.1 - (time.monotonic() - _last_request)))
            _last_request = time.monotonic()
            try:
                response = requests.get("https://export.arxiv.org/api/query", params=params,
                                        headers={"User-Agent": "MOT-Analytics/0.1 (educational research prototype)"}, timeout=45)
                if response.status_code == 429:
                    raise RuntimeError("arXiv API가 요청 제한(429)을 반환했습니다. 재요청을 멈추고 나중에 다시 시도하세요.")
                response.raise_for_status()
                collected = utc_now()
                parse_feed(response.content, collected)
            except (requests.RequestException, ET.ParseError) as error:
                if attempt == 2:
                    raise RuntimeError("arXiv 수집에 실패했습니다. 네트워크/API 상태를 확인하고 다시 실행하세요.") from error
                continue
            metadata = {"collected_at": collected, "request_url": response.url, "params": params,
                        "raw_sha256": hashlib.sha256(response.content).hexdigest()}
            raw.write_bytes(response.content)
            record.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            return response.content, metadata


def collect(query=DEFAULT_QUERY, periods=None, per_period=60, cache_dir=None):
    periods = periods or DEFAULT_PERIODS
    if len(periods) != 2 or not query.strip():
        raise ValueError("검색식과 두 개의 기간이 필요합니다.")
    if not 2 <= int(per_period) <= 100:
        raise ValueError("기간별 수집 상한은 2~100개입니다.")
    windows = []
    for name, start, end in periods:
        begin, finish = date.fromisoformat(start), date.fromisoformat(end)
        if begin > finish or finish > date.today():
            raise ValueError("기간의 시작/끝 또는 미래 날짜를 확인하세요.")
        windows.append((name, begin, finish))
    if periods[0][0] == periods[1][0] or max(w[1] for w in windows) <= min(w[2] for w in windows):
        raise ValueError("두 기간의 이름은 달라야 하며 날짜가 겹치면 안 됩니다.")
    rows, records, seen = [], [], set()
    for name, start, end in windows:
        expression = f'({query}) AND submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]'
        params = {"search_query": expression, "start": 0, "max_results": int(per_period),
                  "sortBy": "submittedDate", "sortOrder": "descending"}
        payload, metadata = request_feed(params, cache_dir or DATA / "raw" / "arxiv")
        entries, total = parse_feed(payload, metadata["collected_at"])
        kept = 0
        for entry in entries:
            published = date.fromisoformat(entry["published"][:10])
            if not start <= published <= end:
                raise ValueError("API 결과에 지정 기간 밖의 논문이 있습니다.")
            if entry["paper_id"] in seen:
                continue
            seen.add(entry["paper_id"])
            rows.append(dict(entry, period=name))
            kept += 1
        records.append(dict(metadata, period=name, start_date=start.isoformat(), end_date=end.isoformat(),
                            total_matches=total, returned=len(entries), retained=kept, capped=total > len(entries)))
    if not rows:
        raise ValueError("검색 결과가 없습니다. 검색어 또는 기간을 조정하세요.")
    frame = pd.DataFrame(rows)
    manifest = {"source": "arXiv API", "query": query, "per_period_limit": int(per_period), "periods": records,
                "deduplication": "arXiv ID without version suffix, first occurrence retained",
                "sampling": "submittedDate descending, capped separately per period",
                "preprocessing": "NFKC lowercase, whitespace normalization; English stopwords; word TF-IDF 1-2 grams",
                "limitations": "Search-matched capped samples; topic shares do not measure total research growth."}
    return frame, manifest


def save_default(query=DEFAULT_QUERY, per_period=60):
    frame, manifest = collect(query=query, per_period=per_period)
    write_dataset(frame, DATA / "processed" / "papers.csv", manifest)
    return frame, manifest
