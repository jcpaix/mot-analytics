"""Actual annual filings from KRX KIND and arXiv metadata from OpenAlex."""
import hashlib
import json
import re
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests
from bs4 import BeautifulSoup

from mot_analytics.arxiv import DEFAULT_PERIODS
from mot_analytics.dart import extract_business, validate_companies
from mot_analytics.storage import DATA, utc_now, write_dataset

OPENALEX_QUERY = '(accelerator OR "AI chip" OR "neural processing") AND ("neural network" OR "deep learning")'
HARDWARE_PATTERN = r"\b(hardware|chip|chips|fpga|asic|microcontroller|dram|sram|neuromorphic|npu|gpu|gpus|accelerator|accelerators)\b|in.memory|processing.in.memory"


def collect_kind():
    sources = json.loads((DATA / "kind_sources.json").read_text(encoding="utf-8"))
    raw_dir = DATA / "raw" / "kind"
    raw_dir.mkdir(parents=True, exist_ok=True)
    def fetch(source):
        report_id = source["url"].split("/")[-2]
        path = raw_dir / f"{report_id}.html"
        record_path = path.with_suffix(".json")
        if path.exists() and record_path.exists():
            payload = path.read_bytes()
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if hashlib.sha256(payload).hexdigest() != record["raw_sha256"]:
                raise ValueError("KIND 원문 캐시 해시가 일치하지 않습니다.")
        else:
            response = requests.get(source["url"], timeout=30)
            response.raise_for_status()
            payload = response.content
            record = {"company": source["company"], "source_url": source["url"], "report_id": report_id,
                      "collected_at": utc_now(), "raw_sha256": hashlib.sha256(payload).hexdigest()}
            path.write_bytes(payload)
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        html = payload.decode("utf-8-sig")
        header = re.sub(r"\s+", "", BeautifulSoup(html[:50000], "html.parser").get_text(" ", strip=True)[:3500])
        if source.get("alias", source["company"]) not in header or not re.search(r"2025(?:년|[./-])12(?:월|[./-])31", header):
            raise ValueError(f"{source['company']}: 기업명 또는 2025년 결산 표지가 일치하지 않습니다.")
        headings = list(re.finditer(r"<h2\b[^>]*>.*?</h2>", html, re.I | re.S))
        start = next((match for match in headings if "사업의 내용" in BeautifulSoup(match.group(), "html.parser").get_text()), None)
        end = next((match for match in headings if start and match.start() > start.start() and "재무에 관한 사항" in BeautifulSoup(match.group(), "html.parser").get_text()), None)
        if start is None or end is None:
            raise ValueError(f"{source['company']}: 사업/재무 절의 경계를 찾지 못했습니다.")
        text = extract_business(html[start.start():end.start()].encode("utf-8"))
        return {"company": source["company"], "sector": source.get("sector", "반도체"), "text": text, "source_url": source["url"], "report_id": report_id,
                "collected_at": record["collected_at"], "section": "II. 사업의 내용", "fiscal_year": "2025", "is_example": "false"}, record
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, sources))
    frame = validate_companies(pd.DataFrame([row for row, _ in results]))
    manifest = {"source": "한국거래소 KIND 공개 사업보고서", "fiscal_year": 2025, "is_example": False,
                "extraction": "HTML heading II. 사업의 내용 through before III. 재무에 관한 사항",
                "verification": "company identity and fiscal-year end checked against filing cover",
                "sampling": "Curated listed companies in semiconductor, IT/games, automotive parts, and pharmaceuticals; sector labels based on principal business; fixed filing snapshots, not exhaustive or guaranteed latest corrections",
                "preprocessing": "NFKC lowercasing, simple Korean/Latin tokens, Korean stopwords, word TF-IDF 1-2 grams",
                "records": [record for _, record in results]}
    write_dataset(frame, DATA / "processed" / "companies.csv", manifest)
    print(f"KIND actual companies: {len(frame)}", flush=True)
    return frame, manifest


def restore_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {position: word for word, indexes in inverted_index.items() for position in indexes}
    return " ".join(positions[p] for p in sorted(positions))


def collect_openalex(per_period=60, query=OPENALEX_QUERY, periods=None, hardware_only=True, output_name="papers", field=None):
    periods = periods or DEFAULT_PERIODS
    if not 2 <= int(per_period) <= 100 or len(periods) != 2 or not query.strip():
        raise ValueError("검색식, 두 기간, 기간별 상한 2~100개가 필요합니다.")
    windows = [(name, date.fromisoformat(start), date.fromisoformat(end)) for name, start, end in periods]
    if any(start > end or end > date.today() for _, start, end in windows):
        raise ValueError("날짜 범위와 미래 날짜를 확인하세요.")
    if periods[0][0] == periods[1][0] or max(w[1] for w in windows) <= min(w[2] for w in windows):
        raise ValueError("기간 이름은 달라야 하고 기간은 겹치면 안 됩니다.")
    raw_dir = DATA / "raw" / "openalex"
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows, records, seen = [], [], set()
    for name, start, end in periods:
        params = {"search": query, "filter": f"locations.source.id:S4306400194,from_publication_date:{start},to_publication_date:{end},has_abstract:true",
                  "sort": "publication_date:desc", "per-page": 200}
        signature = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:20]
        path = raw_dir / f"{signature}.json"
        record_path = raw_dir / f"{signature}.request.json"
        if path.exists() and record_path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != json.loads(record_path.read_text(encoding="utf-8"))["raw_sha256"]:
                raise ValueError("OpenAlex 원본 캐시가 변경되었습니다.")
            data = json.loads(path.read_text(encoding="utf-8"))
            record = json.loads(record_path.read_text(encoding="utf-8"))
        else:
            response = requests.get("https://api.openalex.org/works", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            record = {"collected_at": utc_now(), "request_url": response.url, "params": params,
                      "raw_sha256": hashlib.sha256(response.content).hexdigest()}
            path.write_bytes(response.content)
            record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        retained = 0
        for work in data["results"]:
            locations = work.get("locations", [])
            arxiv_url = next((location.get("landing_page_url") or location.get("pdf_url")
                              for location in locations if "arxiv.org/" in (location.get("landing_page_url") or location.get("pdf_url") or "")), None)
            abstract = restore_abstract(work.get("abstract_inverted_index"))
            if not arxiv_url or len(abstract) < 80:
                continue
            if hardware_only and not re.search(HARDWARE_PATTERN, (work.get("title") or "") + " " + abstract, re.I):
                continue
            match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", arxiv_url)
            if not match:
                continue
            version_id = match.group(1).removesuffix(".pdf")
            paper_id = re.sub(r"v\d+$", "", version_id)
            if paper_id in seen:
                continue
            seen.add(paper_id)
            rows.append({"paper_id": paper_id, "version_id": version_id, "title": work["title"], "abstract": abstract,
                         "published": work["publication_date"], "updated": work.get("updated_date", ""),
                         "authors": "; ".join(a["author"]["display_name"] for a in work.get("authorships", [])),
                         "categories": "; ".join(t["display_name"] for t in work.get("topics", [])[:3]),
                         "source_url": f"https://arxiv.org/abs/{paper_id}", "metadata_url": work["id"],
                         "metadata_source": "OpenAlex", "collected_at": record["collected_at"], "period": name, "field": field or "AI 반도체"})
            retained += 1
            if retained >= per_period:
                break
        records.append(dict(record, period=name, start_date=start, end_date=end, total_matches=data["meta"]["count"],
                            returned=len(data["results"]), retained=retained, capped=data["meta"]["count"] > retained))
        print(f"OpenAlex/arXiv {name}: {retained}", flush=True)
    if len(rows) < 4 or any(period["retained"] == 0 for period in records):
        raise ValueError("실제 논문 표본이 부족합니다. 검색어와 기간을 조정하세요.")
    frame = pd.DataFrame(rows)
    manifest = {"source": "OpenAlex API, arXiv repository records only", "query": query,
                "per_period_limit": per_period, "periods": records, "is_example": False,
                "deduplication": "arXiv ID without version suffix; first retained",
                "sampling": f"OpenAlex publication_date descending; first 200 matched records considered, up to {per_period} with arXiv URL and abstract retained per period",
                "title_abstract_filter": HARDWARE_PATTERN if hardware_only else "",
                "date_basis": "OpenAlex publication_date, not necessarily first arXiv submission. updated and categories are OpenAlex update/topics.",
                "preprocessing": "NFKC lowercase, English stopwords, title plus abstract word TF-IDF 1-2 grams",
                "limitations": "Independent OpenAlex index, incomplete coverage, capped date-sorted search samples; shares do not measure research growth.",
                "fallback_reason": "Direct arXiv API returned HTTP 429; no further requests made to that API."}
    if not re.fullmatch(r"[a-z_]+", output_name):
        raise ValueError("데이터 파일 이름이 유효하지 않습니다.")
    write_dataset(frame, DATA / "processed" / f"{output_name}.csv", manifest)
    return frame, manifest


if __name__ == "__main__":
    collect_kind()
    collect_openalex()
