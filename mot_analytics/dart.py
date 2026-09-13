import io
import re
import time
import zipfile

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from defusedxml import ElementTree as ET

from mot_analytics.storage import DATA, utc_now, write_dataset

DEFAULT_COMPANIES = ["삼성전자", "SK하이닉스", "DB하이텍", "LX세미콘", "제주반도체", "텔레칩스", "어보브반도체", "넥스트칩", "가온칩스", "에이디테크놀로지", "하나마이크론", "SFA반도체"]


def validate_companies(frame):
    required = {"company", "text", "source_url", "report_id", "collected_at", "section"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("CSV에 필요한 열: " + ", ".join(sorted(missing)))
    frame = frame.copy().fillna("").astype(str)
    for column in required:
        if frame[column].str.strip().eq("").any():
            raise ValueError(f"{column} 열에 빈 값이 있습니다.")
    if frame["company"].duplicated().any():
        raise ValueError("기업당 동일 기간의 원문 한 행을 사용하세요. 중복 기업이 있습니다.")
    if not frame["source_url"].str.match(r"^https?://").all():
        raise ValueError("출처 URL은 http 또는 https 주소여야 합니다.")
    if pd.to_datetime(frame["collected_at"], errors="coerce", utc=True).isna().any():
        raise ValueError("수집 시점은 ISO 날짜/시간이어야 합니다.")
    if not 4 <= len(frame) <= 100:
        raise ValueError("기업 원문은 4~100개를 올려주세요. 권장 범위는 10~15개입니다.")
    return frame.reset_index(drop=True)


def extract_business(payload):
    soup = BeautifulSoup(payload, "html.parser")
    titles = soup.find_all(lambda tag: tag.name in {"title", "h1", "h2", "h3"} and "사업의 내용" in tag.get_text())
    if not titles:
        raise ValueError("'사업의 내용' 제목을 찾지 못했습니다. 해당 절을 직접 CSV에 넣어주세요.")
    # DART titles, rather than a plain-text table of contents, delimit the section.
    heading = titles[-1]
    parts = []
    for item in heading.next_elements:
        if isinstance(item, Tag) and item.name in {"title", "h1", "h2"}:
            title = item.get_text(" ", strip=True)
            if re.search(r"(?:III|Ⅲ|3)\s*[.．]?\s*재무|재무에 관한 사항|이사의 경영진단", title, re.I):
                break
        if isinstance(item, NavigableString) and item.parent.name not in {"script", "style"}:
            value = " ".join(str(item).split())
            if value:
                parts.append(value)
    text = "\n".join(parts)
    if len(text) < 300:
        raise ValueError("추출 원문이 너무 짧습니다. 보고서 구조를 직접 확인하세요.")
    return text


class DartClient:
    def __init__(self, key):
        if not key:
            raise ValueError("환경 변수 DART_API_KEY가 필요합니다.")
        self.key = key
        self.session = requests.Session()

    def get(self, endpoint, **params):
        # Never include URLs or request exceptions in logs: key is a query parameter.
        try:
            response = self.session.get(f"https://opendart.fss.or.kr/api/{endpoint}",
                                        params=dict(crtfc_key=self.key, **params), timeout=45)
            response.raise_for_status()
            return response
        except requests.RequestException:
            raise RuntimeError("DART 요청에 실패했습니다. 인증키와 네트워크를 확인하세요.") from None

    def json(self, endpoint, **params):
        payload = self.get(endpoint, **params).json()
        if payload.get("status") != "000":
            raise ValueError(f"DART 응답 {payload.get('status')}: {payload.get('message', '오류')}")
        return payload

    def registry(self):
        payload = self.get("corpCode.xml").content
        if not zipfile.is_zipfile(io.BytesIO(payload)):
            raise ValueError("DART 기업 목록 수집에 실패했습니다. 인증키를 확인하세요.")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            root = ET.fromstring(archive.read("CORPCODE.xml"))
        return {item.findtext("corp_name"): item.findtext("corp_code") for item in root.findall("list")}


def collect_companies(key, companies=None, fiscal_year=2025):
    client = DartClient(key)
    companies = companies or DEFAULT_COMPANIES
    registry = client.registry()
    rows, errors = [], []
    raw_dir = DATA / "raw" / "dart"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for company in companies:
        try:
            if company not in registry:
                raise ValueError("DART 기업명과 일치하지 않습니다.")
            filings = client.json("list.json", corp_code=registry[company], bgn_de=f"{fiscal_year + 1}0101",
                                  end_de=f"{fiscal_year + 1}1231", pblntf_detail_ty="A001",
                                  page_count=100, sort="date", sort_mth="desc")["list"]
            filing = next((f for f in filings if f"({fiscal_year}.12)" in f["report_nm"]), None)
            if not filing:
                raise ValueError("해당 연도 12월 결산 사업보고서가 없습니다.")
            report_id = filing["rcept_no"]
            payload = client.get("document.xml", rcept_no=report_id).content
            if not zipfile.is_zipfile(io.BytesIO(payload)):
                raise ValueError("원문 ZIP 대신 오류 응답을 받았습니다.")
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = [m for m in archive.infolist() if m.filename.lower().endswith(".xml")]
                if not members or sum(m.file_size for m in members) > 100_000_000:
                    raise ValueError("원문 XML이 없거나 파일이 너무 큽니다.")
                candidates = []
                for member in members:
                    try:
                        candidates.append(extract_business(archive.read(member)))
                    except ValueError:
                        continue
            if not candidates:
                raise ValueError("사업의 내용 추출 실패. 원문 확인 후 CSV를 사용하세요.")
            (raw_dir / f"{report_id}.zip").write_bytes(payload)
            rows.append({"company": company, "text": max(candidates, key=len), "source_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={report_id}",
                         "report_id": report_id, "collected_at": utc_now(), "section": "II. 사업의 내용",
                         "fiscal_year": fiscal_year, "is_example": "false"})
        except (ValueError, RuntimeError) as error:
            errors.append({"company": company, "error": str(error)})
        time.sleep(0.3)
    if len(rows) < 4:
        raise ValueError(f"수집 성공 {len(rows)}개로 분석 최소 개수에 미달합니다. 실패 내역: {errors}")
    frame = validate_companies(pd.DataFrame(rows))
    manifest = {"source": "OpenDART", "collected_at": utc_now(), "fiscal_year": fiscal_year,
                "requested_companies": companies, "errors": errors, "extraction": "II. 사업의 내용, latest matching annual filing",
                "preprocessing": "NFKC lowercase; simple Korean/Latin word tokens; stopwords; TF-IDF 1-2 grams",
                "verification": "Automatic section extraction; manually review original report before interpretation."}
    write_dataset(frame, DATA / "processed" / "companies.csv", manifest)
    return frame, manifest
