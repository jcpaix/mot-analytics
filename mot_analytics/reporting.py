import numpy as np
from mot_analytics.analysis import KO_STOP, analyze
from mot_analytics.fields import FIELDS
from mot_analytics.storage import DATA, ROOT, read_dataset, utc_now

def field_report():
    companies,cm=read_dataset(DATA/'processed/companies.csv')
    financials,fm=read_dataset(DATA/'processed/financials.csv')
    lines=['# 분야별 실제 데이터 분석 기록','',f'분석 기록 작성 시각: {utc_now()} (UTC)','',
           '기업 자료 제공처: 한국거래소 KIND. 2025년 결산 사업보고서의 II. 사업의 내용을 분석했다. 분야는 공시에 적힌 주된 사업을 기준으로 직접 지정한 선정 표본이다.','']
    for sector,group in companies.groupby('sector',sort=False):
        lines+=[f'## {sector} 기업 · {len(group)}개','']
        for row in group.itertuples():lines.append(f'- [{row.company}]({row.source_url}) · 원문 ID {row.report_id} · 수집 {row.collected_at}')
        lines.append('')
    lines+=['## 재무 실적','',f'연도·단위·연결/별도 기준을 확인한 {financials.company.nunique()}개 기업의 2023~2025년 매출액과 영업이익을 추출했다. 원화로 저장하며 화면에서는 억원으로 환산한다. 기업 전체 실적이며 원문 요약 표의 반올림·재작성·계속/중단영업 기준을 따른다.','',
            '확인 조건이 부족해 재무 수치를 표시하지 않은 기업: '+(', '.join(r['company'] for r in fm['missing_records']) or '없음. 틸론은 동일 연결 기준 요약 표에 2023년이 없어 2024~2025년만 표시'), '']
    all_ids=set(); total=0
    for field,(name,query,_) in FIELDS.items():
        frame,manifest=read_dataset(DATA/'processed'/f'{name}.csv')
        all_ids.update(frame.paper_id); total+=len(frame)
        result=analyze(tuple(frame.title+'. '+frame.abstract),4,'en')
        recent=frame[frame.period==manifest['periods'][-1]['period']]
        recent_result=analyze(tuple(recent.title+'. '+recent.abstract),4,'en')
        names=recent_result.vectorizer.get_feature_names_out(); weights=np.asarray(recent_result.matrix.mean(axis=0)).ravel()
        terms=[str(names[i]) for i in weights.argsort()[::-1] if ' ' not in names[i] and names[i] not in KO_STOP][:15]
        lines+=[f'## {field} 논문 · {len(frame)}편','',f'수집 검색 조건: {query}','',
                '자료 제공처: OpenAlex API. arXiv 원문 링크와 초록이 있는 자료만 사용한다. 날짜는 OpenAlex 출판일이며 arXiv 최초 제출일과 다를 수 있다.','']
        for record in manifest['periods']:
            lines.append(f"- {record['period']}: {record['start_date']}~{record['end_date']}, 검색 일치 {record['total_matches']}건, 선별 표본 {record['retained']}편. 수집 {record['collected_at']}. 처음 반환한 최신순 200건에서 최대 60편을 선별했다.")
        lines+=['', '최근 기간의 평균 단어 중요도 상위 표현: '+', '.join(terms)+'.','',
                f'자동 군집의 코사인 기준 실루엣: {result.silhouette:.3f}. 2차원 투영 설명 분산: {result.explained_variance:.1%}. 군집과 지도는 탐색용이며 검증된 기술 분류가 아니다.','']
        if result.silhouette < 0.05:lines+=['군집 분리가 약하다. 뚜렷한 분야 변화나 기술 이동을 발견했다고 단정하지 않는다.','']
        for row in recent.head(3).itertuples():lines.append(f'- [{row.title}]({row.source_url}) · 날짜 {row.published} · [메타데이터]({row.metadata_url})')
        lines.append('')
    lines+=['## 해석 범위','',f'4개 기술 분야의 표본 행은 총 {total}건, 중복을 제거한 arXiv ID는 {len(all_ids)}개다. 분야 사이의 동일 논문 중복을 전체 연구량으로 합산하지 않는다.',
            '단어 비교는 TF-IDF와 기간별 등장 비율로 계산한다. 조사·연결 표현 및 공시 반복 표현을 제외하지만 한국어 형태소 분석은 적용하지 않았다. 최신순 제한 표본에서의 단어 등장 비율과 주제 비중 변화는 연구 전체의 유행·시장 성장·인과효과를 증명하지 않는다.',
            '각 처리 CSV와 수집 기록 파일에 원문 링크, 수집 시각, 검색 조건 및 데이터 해시를 보존했다. 고정된 기업 제출본이며 최신 정정 여부는 원문에서 확인한다.','']
    output=ROOT/'reports/first_analysis.md'
    output.write_text('\n'.join(line.rstrip() for line in lines),encoding='utf-8')
    print(output,flush=True)
    return output
