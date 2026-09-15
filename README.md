# MOT Analytics

실제 공시와 논문으로 산업·기술 분야별 핵심 단어, 기업의 사업 설명, 재무 실적을 살펴보는 Streamlit 앱.

공개 웹: [MOT Analytics](https://mot-analytics.vercel.app/) · [처음 보는 분을 위한 설명](https://mot-analytics.vercel.app/#guide)

웹 배포: Vercel · 서버 진입점 `server:app` · 로컬 실행 `uvicorn server:app --reload`. 아래 기존 Streamlit 실행도 지원합니다.

## 데이터

- 기업: 한국거래소 KIND의 2025년 결산 사업보고서 22개. 반도체 10개, IT·플랫폼·게임 4개, 자동차·부품 4개, 바이오·제약 4개. 분야는 주된 사업을 기준으로 직접 지정한 선정 표본이다.
- 기업 원문: II. 사업의 내용. 원문 표지의 기업명과 결산일을 확인하고 III. 재무에 관한 사항 전까지 추출한다. 보고서 표의 내용과 반복 문구도 일부 포함된다.
- 재무: KIND 요약재무정보에서 연도·단위·연결/별도 기준을 확인한 22개 기업의 2023~2025년 매출액과 영업이익. 원화로 저장하고 화면에서는 억원으로 표시한다. 틸론의 연결 기준 2023년 요약 값은 해당 공시에 없어 비워 둔다.
- 논문: 반도체·AI 하드웨어, AI·소프트웨어, 자동차·자율주행, 바이오·의료 AI의 각 120편, 총 480편. OpenAlex API에서 arXiv 링크와 초록이 있는 자료만 선정한다. 분야 사이의 논문 중복은 가능하다.
- 논문 기간: 2025년과 2026년 각각 1월 1일~8월 31일, 기간별 최신순 60편. 날짜는 OpenAlex 출판일로 arXiv 최초 제출일과 다를 수 있다.

기업 원문 URL은 `data/kind_sources.json`, 논문별 원문 및 OpenAlex URL은 각 처리 CSV에 있다. 각 데이터의 `.manifest.json`에 수집 시각, 검색 조건, 수집 상한, 원본 해시와 제외 기록을 보존한다. 모든 시각은 UTC다. 고정 제출본이며 최신 정정본 여부는 원문에서 확인한다.

## 화면

산업·기술 분야 선택, 분야별 분석 기업 수·목록과 단어 중요도 비교, 매출·영업이익 비교 및 연도별 실적, 기업별 제품·기술의 원문 설명, 같은 분야 기업 간 원문 유사도, 논문 주제 지도, 두 기간의 단어 등장 비율과 주제 비중, 근거 원문, 출처 및 수집 기록을 제공한다. 재무 화면은 분야별 모든 기업의 자체 연도 변화와 같은 분야의 실적 비교를 함께 제공한다. 원문은 어절을 유지하며 줄 간격과 문단 간격을 넓혔다. 원문 표의 병합 셀과 금액을 복원하고 소제목 토글·큰 항목 선택·원문 검색을 제공한다. 수집 기록은 표로 표시하며 소스 코드를 화면에 노출하지 않는다.

## 분석 기준

TF-IDF는 흔한 단어의 영향은 줄이고 특정 문서에서 중요한 단어의 영향은 높인다. 한국어는 간단한 토큰과 불용어를 사용하며 형태소 분석은 적용하지 않았다. ‘따라’, ‘있으며’, ‘당사는’, ‘등의’ 등 조사·연결 표현과 공시 반복 표현을 제외한다. 기업의 제품·기술과 주력 사업은 원문 설명과 실적으로 확인하며 단어의 중요도를 주력 매출 순위로 해석하지 않는다.

자동 군집은 단어 점수의 거리로 나누는 탐색 결과로 직접 지정한 분야와 별개다. 코사인 유사도는 문서의 표현 유사성이고 SVD 지도는 정보 일부를 잃은 2차원 표현이다. 기업 유사도·전략지도·원문 비교는 선택한 분야 안에서만 계산하며 해당 분야 문서만으로 TF-IDF를 다시 학습한다. 전체 분야 보기에서도 비교 분야를 별도로 선택한다. 같은 분야에서도 세부 사업과 연결 범위가 다를 수 있다. 제한된 최신순 논문 표본은 전체 연구량이나 시장 성장을 측정하지 않는다. 재무 값은 각 공시의 요약·재작성·계속/중단영업 기준을 따른다.

## 실행

Python 3.11 이상, 프로젝트 폴더에서 실행한다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt
.venv/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

앱: http://127.0.0.1:8501/ · 논문: http://127.0.0.1:8501/technology

수집 자료를 동봉해 오프라인으로 분석할 수 있다. 원본 KIND HTML은 로컬 캐시이며 Git에는 출처·추출 원문·수집 기록을 보존한다. 재수집은 `python -m mot_analytics.fields`, 재무 추출은 `python -m mot_analytics.financials`, 분석 기록은 `python -m mot_analytics.cli report`, 검증은 `python -m pytest -q`로 실행한다. DART는 선택 기능이며 키는 환경 변수로만 읽는다. API 응답 실패 시 임의 데이터를 생성하지 않는다.



## 출처

[한국거래소 KIND](https://kind.krx.co.kr/) · [OpenAlex Works 문서](https://docs.openalex.org/api-entities/works) · [arXiv](https://arxiv.org/) · [OpenDART](https://opendart.fss.or.kr/)

GitHub: https://github.com/jcpaix/mot-analytics

처음 보는 분을 위한 [프로젝트 설명](reports/project_guide.md): 만든 목적, 실제 데이터의 범위, 분석 방법과 결과를 읽는 순서를 설명합니다. Vercel 공개판에는 자사 기준 성장률·영업이익률·동일 기준 비교, 기술 항목별 논문 비율·초록 근거, CSV 업로드 분석과 요청별 새 논문 수집을 제공합니다. 기본 표본과 새 요청의 데이터는 별도로 처리합니다.

## Vercel 구성과 검증

`pyproject.toml`의 Python 의존성과 `server:app` 진입점을 사용합니다. Vercel 빌드는 `node scripts/build_vercel.cjs`로 화면 파일과 설명을 갱신합니다. 분석 표본을 갱신할 때는 `scripts/build_public.py`를 먼저 실행합니다. 외부 API 결과나 업로드는 요청별 임시 디렉터리와 메모리에서 처리하며 공용 데이터 파일을 바꾸지 않습니다.

`node --test tests/insights.test.cjs`로 손실·전환·중앙값·표본 분모를 검증하고 `python -m pytest tests/test_web_api.py -q`로 실제 업로드 분석과 입력 경계를 검증합니다.

현재 Vercel ZIHAF 팀의 `mot-analytics` 프로젝트에 CLI로 직접 배포합니다. GitHub 자동 연결은 설치 계정의 저장소 접근 권한이 없어 설정되지 않았으므로 GitHub에 푸시하는 것만으로 재배포되지는 않습니다.
