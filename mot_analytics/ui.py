import io
import math
import json
import html
import re
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import numpy as np

from mot_analytics.analysis import analyze, comparison_terms, cooccurrences, evidence, neighbors, period_shares, representatives
from mot_analytics.arxiv import DEFAULT_QUERY, collect
from mot_analytics.dart import validate_companies
from mot_analytics.storage import DATA, read_dataset, utc_now
from mot_analytics.public_data import OPENALEX_QUERY, collect_openalex
from mot_analytics.fields import FIELDS
from mot_analytics.documents import document_sections, business_description_text

COLORS = ["#167568", "#4875B8", "#D08D32", "#995798", "#C45F65", "#697F41"]


def beginner_explanation(kind):
    with st.expander("쉽게 읽는 분석 기준 · 무엇을 기준으로 묶나요?"):
        st.write("**질문:** " + ("기업들이 사업을 설명할 때 어떤 표현을 함께 쓰고, 어디서 차이가 날까요?" if kind == "company" else "논문들이 다루는 기술 표현은 어떻게 비슷하고, 두 기간 표본에서 어떤 차이가 날까요?"))
        st.write("**① 문서를 준비합니다.** " + ("같은 2025년 결산 사업보고서에서 'II. 사업의 내용'을 가져옵니다. 주요 사업·제품·연구개발 설명을 비교하며 재무제표 절은 제외합니다." if kind == "company" else "검색 조건에 맞고 arXiv 원문 링크와 초록이 있는 논문의 제목·초록을 사용합니다. PDF 전체를 분석하는 것은 아닙니다."))
        st.write("**② 단어에 점수를 줍니다.** 모든 문서에 흔한 단어의 영향은 낮추고, 특정 문서에서 자주 쓰는 표현의 영향은 높입니다. 이 방법이 TF-IDF입니다. 단어 하나와 연속된 두 단어를 함께 사용하고 문서 길이 차이를 보정합니다.")
        st.write("**③ 비슷한 단어 점수표끼리 묶습니다.** KMeans는 문서의 점수표와 각 묶음의 중심 사이의 거리를 줄이도록 문서를 나눕니다. 기본 4개는 탐색을 위한 설정이며, 검증으로 확정한 산업·기술 분류가 아닙니다. 군집 수를 바꾸면 묶음도 달라집니다.")
        st.write("**④ 결과를 원문으로 확인합니다.** 유사도는 점수표의 방향이 얼마나 비슷한지 나타내는 코사인 유사도입니다. 1에 가까울수록 같은 표현을 비슷하게 씁니다. 지도는 수천 개 단어 점수를 두 축으로 줄인 그림이라 가까운 점의 실제 유사도를 별도로 확인해야 합니다.")
        st.caption("읽는 순서: 지도에서 묶음을 살펴보기 → 기업 또는 논문 선택 → 주요 표현과 원문 읽기 → 출처 링크로 확인. 표현의 유사성이 사업 성공·실제 경쟁 관계·기술의 우수성을 증명하지는 않습니다.")


@st.cache_data(show_spinner=False)
def cached_analysis(texts, clusters, language, revision='stopwords-v2'):
    return analyze(texts, clusters, language)


def csv_download(frame, label, filename):
    st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"), filename, "text/csv")


def readable_original(text):
    paragraphs, current = [], []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line)<110 and re.match(r'^(?:\d+\s*[.)]|\(\d+\)|[가-하]\s*[.)])',line):
            if current:paragraphs.append(' '.join(current)); current=[]
            paragraphs.append(line)
            continue
        current.append(line)
        if len(' '.join(current)) >= 500 or (len(' '.join(current)) >= 100 and re.search(r'[.!?。]$', line)):
            paragraphs.append(' '.join(current)); current=[]
    if current:
        paragraphs.append(' '.join(current))
    st.markdown('<div class="source-reader">' + ''.join('<p>'+html.escape(p)+'</p>' for p in paragraphs) + '</div>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def document_records(signature):
    path=DATA/'processed/company_documents.json'
    payload=path.read_bytes()
    import hashlib
    if hashlib.sha256(payload).hexdigest()!=signature:raise ValueError('원문 구조 데이터가 수집 기록과 다릅니다.')
    return {record['report_id']:record for record in json.loads(payload)}


def company_original(row,preview=False,context='profile'):
    path=DATA/'processed/company_documents.json'
    if not path.exists():readable_original(row.text[:2400] if preview else row.text); return
    metadata=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    record=document_records(metadata['sha256']).get(row.report_id)
    if not record or record['source_url']!=row.source_url:readable_original(row.text[:2400] if preview else row.text); return
    def render(blocks):
        for block in blocks:
            if block['type']=='heading':
                st.markdown('<div class="source-reader"><h4 style="margin:1.8rem 0 1rem;line-height:1.8;word-break:keep-all">'+html.escape(block['text'])+'</h4></div>',unsafe_allow_html=True)
            elif block['type']=='table':
                if block.get('unit'):st.caption(block['unit'])
                if not block['rows']:
                    st.caption(' · '.join(block['columns'])); continue
                st.dataframe(pd.DataFrame(block['rows'],columns=block['columns']),hide_index=True,width='stretch')
            else:readable_original(block['text'])
    if preview:
        paragraphs=business_description_text(record['blocks']).splitlines()
        own=[text for text in paragraphs if re.search(r'당사|연결회사|연결실체|회사는|회사가',text)]
        for text in (own or paragraphs)[:2]:readable_original(text)
        return
    sections=document_sections(record['blocks'])
    chapters=list(dict.fromkeys(section['chapter'] for section in sections))
    default_chapter=next((i for i,title in enumerate(chapters) if title!='사업의 내용'),0)
    chapter=st.selectbox('원문 큰 항목',chapters+['전체 항목'],index=default_chapter,key=context+'_chapter_'+row.report_id)
    search=st.text_input('원문 소제목·내용 검색',placeholder='예: 유동성, 외화, 연구개발',key=context+'_search_'+row.report_id)
    st.caption('소제목을 누르면 해당 원문과 표가 열립니다. 검색어를 입력하면 전체 사업 절에서 찾습니다.')
    found=False
    for section in sections:
        if search:
            if search.lower() not in (section['title']+' '+json.dumps(section['blocks'],ensure_ascii=False)).lower():continue
        elif chapter!='전체 항목' and section['chapter']!=chapter:continue
        found=True
        panel=st.expander(section['title'],key=context+'_section_'+row.report_id+'_'+str(section['id']),on_change='rerun')
        if panel.open:
            with panel:render(section['blocks'])
    if not found:st.info('검색 조건에 맞는 원문 항목이 없습니다.')


def collection_record(manifest):
    st.write("**데이터 제공처** · " + manifest.get('source','출처 미기록'))
    if 'query' in manifest:
        st.write("**수집 검색 조건** · " + manifest['query'])
    if manifest.get('periods'):
        records=[{'비교 기간':r['period'],'시작일':r['start_date'],'종료일':r['end_date'],'수집 시점':r['collected_at'],'검색 일치 수':r['total_matches'],'분석 표본 수':r['retained'],'수집 상한 적용':bool(r.get('capped'))} for r in manifest['periods']]
        st.dataframe(pd.DataFrame(records),hide_index=True,width='stretch')
    st.caption('수집 시각은 UTC입니다. 원문 식별자와 출처는 데이터 표에서 확인할 수 있습니다.')


def financial_panel(company_frame):
    path=DATA/'processed/financials.csv'
    if not path.exists():
        st.info('출처와 단위를 확인한 재무 데이터가 아직 없습니다.'); return
    financials,manifest=read_dataset(path)
    values=financials[financials.company.isin(company_frame.company)].copy()
    if values.empty:
        st.info('선택한 기업에 대해 기준을 확인한 재무 수치가 없습니다.'); return
    values['연도']=pd.to_numeric(values.year)
    values['금액(억원)']=pd.to_numeric(values.value_krw)/100000000
    st.subheader('매출과 영업이익 · 2023~2025년')
    st.caption('사업보고서 요약재무정보의 실적입니다. 원문 단위를 원화로 환산해 억원으로 통일했습니다. 기업 전체 매출이며 해당 분야 사업부의 매출과 다를 수 있습니다. 연결은 종속회사를 포함하고, 별도는 해당 법인만 집계합니다.')
    values['기업·기준']=values.company+' ('+values.basis+')'
    st.write('**각 기업의 자체 실적을 비교합니다.** 특정 기업을 기준값으로 삼지 않습니다. 아래 작은 그래프는 기업마다 세로축 범위를 맞춰 각 기업 안에서 매출과 영업이익의 연도별 변화를 읽을 수 있도록 했습니다.')
    number_columns={c:st.column_config.NumberColumn(c,format='%.2f') for c in ['매출액(억원)','영업이익(억원)']}
    number_columns['출처']=st.column_config.LinkColumn('출처',display_text='원문')
    sectors=list(dict.fromkeys(values.sector))
    sector_tabs=st.tabs([sector+' · '+str(values[values.sector==sector].company.nunique())+'개 기업' for sector in sectors])
    for sector,panel in zip(sectors,sector_tabs):
        with panel:
            group=values[values.sector==sector].sort_values(['company','연도','metric'])
            st.subheader(sector+' · 모든 기업의 자체 실적')
            st.caption('연결·별도 기준은 기업 이름 옆에 표시합니다. 기업 간 금액 크기는 아래 같은 축 비교 그래프와 수치 표로 확인하세요.')
            own_tab,comparison_tab=st.tabs(['기업별 연도 변화 · 전체 표시','같은 분야 기업 간 실적 비교'])
            with own_tab:
                st.caption('금액 단위: 억원 · 가로축: 연도 · 파란색: 매출액 · 초록색: 영업이익. 기업마다 세로축 범위가 다릅니다.')
                cards=st.columns(2,gap='large')
                for i,(company,records) in enumerate(group.groupby('company',sort=False)):
                    with cards[i%2]:
                        st.markdown('**'+company+' · '+records.basis.iloc[0]+'**')
                        fig=px.line(records,x='연도',y='금액(억원)',color='metric',markers=True,labels={'metric':'항목'},color_discrete_map={'매출액':'#4875B8','영업이익':'#167568'},hover_data={'basis':True,'original_value':True,'original_unit':True})
                        fig.update_yaxes(tickformat=',.0f',title_text=None,automargin=True,nticks=5)
                        fig.update_xaxes(tickvals=[2023,2024,2025],ticktext=['2023','2024','2025'],title_text=None,automargin=True)
                        fig.update_layout(height=260,showlegend=False,font=dict(size=12),margin=dict(l=10,r=15,t=15,b=20),hovermode='x unified')
                        st.plotly_chart(fig,width='stretch',key='financial_own_'+sector+'_'+company)
            with comparison_tab:
                current=group[group['연도']==2025]
                for metric in ['매출액','영업이익']:
                    fig=px.bar(current[current.metric==metric].sort_values('금액(억원)'),x='금액(억원)',y='기업·기준',orientation='h',text='금액(억원)',color_discrete_sequence=['#4875B8' if metric=='매출액' else '#167568'],title='2025년 '+metric)
                    fig.update_traces(texttemplate='%{x:,.2f}',textposition='auto')
                    fig.update_xaxes(tickformat=',.0f'); fig.update_layout(height=max(320,group.company.nunique()*40),margin=dict(t=50,b=20))
                    st.plotly_chart(fig,width='stretch',key='financial_compare_'+sector+metric)
            tidy=group.pivot_table(index=['company','연도','basis','source_url'],columns='metric',values='금액(억원)').reset_index().rename(columns={'company':'기업','basis':'기준','source_url':'출처','매출액':'매출액(억원)','영업이익':'영업이익(억원)'})
            tidy=tidy[['기업','연도','매출액(억원)','영업이익(억원)','기준','출처']]
            st.dataframe(tidy,hide_index=True,width='stretch',column_config=number_columns)
            for company,records in group.groupby('company',sort=False):
                missing={2023,2024,2025}-set(records['연도'])
                if missing:st.caption(company+' · '+', '.join(str(year) for year in sorted(missing))+'년은 선택한 공시의 동일 기준 요약 수치가 없어 비워두었습니다.')
                if 'audit_note' in records and records.audit_note.ne('').any():st.caption(company+' · '+records.audit_note.iloc[0]+'. 원문과 함께 확인하세요.')
    omitted=set(company_frame.company)-set(financials.company)
    if omitted: st.caption('연도·단위·기준 확인 부족으로 수치를 표시하지 않은 기업: '+', '.join(sorted(omitted)))
    csv_download(values,'재무 수치와 원문 근거 다운로드','financials.csv')


def draw_map(result, names, key):
    frame = pd.DataFrame({"x": result.coordinates[:, 0], "y": result.coordinates[:, 1],
                          "name": list(names), "cluster": [str(x + 1) for x in result.labels],
                          "keywords": [", ".join(result.keywords[int(x)][:4]) for x in result.labels]})
    fig = px.scatter(frame, x="x", y="y", color="cluster", hover_name="name", hover_data={"keywords": True, "x": False, "y": False},
                     color_discrete_sequence=COLORS, labels={"cluster": "군집"})
    fig.update_traces(marker=dict(size=13, opacity=0.88, line=dict(width=1, color="white")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=15, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      xaxis_title="SVD 축 1", yaxis_title="SVD 축 2", legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, width="stretch", key=key)
    st.caption(f"2차원 투영 설명 분산 {result.explained_variance:.1%}. 가까운 점도 전체 TF-IDF 공간의 유사도와 다를 수 있습니다.")


def method_note(result, language):
    with st.expander("분석 방법과 해석 범위"):
        st.write("현재 방법: 단어 TF-IDF(1~2그램) · 코사인 유사도 · KMeans · SVD 2차원 투영. 난수 시드 42.")
        st.write("NFKC 정규화, 소문자 변환, 공백 정리 후 " + ("간단한 한국어/영문 토큰과 불용어를 사용합니다. 형태소 분석은 적용하지 않았습니다." if language == "ko" else "영어 불용어를 제거합니다. 제목과 초록을 함께 사용합니다."))
        if result.silhouette is not None:
            st.write(f"코사인 기준 실루엣 점수 {result.silhouette:.3f}. 점수는 기술 분류나 경제적 타당성을 입증하지 않습니다.")
        st.write("군집 번호와 키워드는 자동으로 생성한 탐색용 라벨입니다. 문장 임베딩 비교는 아직 적용하지 않았습니다.")


def companies_page():
    st.caption("01 / COMPANY STRATEGY")
    st.title("기업 전략 지도")
    st.write("분야를 선택해 기업들의 핵심 단어, 매출·영업이익, 사업 설명의 공통점과 차이를 살펴봅니다.")
    beginner_explanation("company")
    real_path = DATA / "processed" / "companies.csv"
    sources = ["원문 CSV 업로드"]
    if real_path.exists():
        sources.insert(0, "수집된 실제 사업보고서")
    source = st.radio("데이터 선택", sources, horizontal=True)
    manifest = {}
    try:
        if source == "원문 CSV 업로드":
            st.info("기업당 한 행으로 동일 보고 기간의 주요 사업·신사업·연구개발 원문을 넣어주세요. DART 키 없이 시작할 수 있습니다.")
            upload = st.file_uploader("기업 원문 CSV", type=["csv"])
            if upload is None:
                st.caption("필수 열: company, text, source_url, report_id, collected_at, section. 권장 기업 수 10~15개.")
                st.stop()
            frame = pd.read_csv(io.BytesIO(upload.getvalue()), dtype=str, keep_default_na=False)
            manifest = {"source": "사용자 업로드", "uploaded_at": utc_now(), "filename": upload.name}
        else:
            frame, manifest = read_dataset(real_path)
            st.info(f"실제 데이터 출처: {manifest.get('source', '사업보고서')} · 2025년 결산 · II. 사업의 내용. 자동 추출 결과와 원문을 함께 확인하세요.")
        frame = validate_companies(frame)
        if 'sector' not in frame: frame['sector']='사용자 자료'
        selected_sector=st.selectbox('분석할 산업 분야',['전체 분야']+list(dict.fromkeys(frame.sector)),key='company_sector')
        st.caption('분야는 공시에 적힌 주된 사업을 기준으로 직접 지정했습니다. 아래 자동 군집과는 별개이며, 복수 사업을 하는 기업도 포함합니다. 기준 기간: 2025년 결산 사업보고서.')
        inventory_all=frame.copy()
        if selected_sector!='전체 분야': frame=frame[frame.sector==selected_sector].reset_index(drop=True)
        if "is_example" in frame and frame.is_example.str.lower().isin(["true", "1", "yes"]).any():
            raise ValueError("가상 데이터는 분석하지 않습니다. 실제 기업 원문을 올려주세요.")
        if source == "원문 CSV 업로드":
            if "is_example" in frame and frame.is_example.str.lower().isin(["true", "1", "yes"]).any():
                st.warning("업로드에 가상 예시가 포함되어 있습니다. 실제 기업 분석으로 해석하지 마세요.")
            else:
                st.caption("사용자가 제공한 원문입니다. 출처 진위와 추출 범위를 앱이 확인한 것은 아닙니다.")
        clusters = st.slider("군집 수", 2, min(6, len(frame) - 1), min(4, len(frame) - 1), key="company_k")
        result = cached_analysis(tuple(frame.text), clusters, "ko")
    except (ValueError, pd.errors.ParserError, UnicodeDecodeError) as error:
        st.error(str(error))
        st.stop()
    a, b, c = st.columns(3)
    a.metric("분석 기업", f"{len(frame)}개")
    b.metric("군집", f"{len(set(result.labels))}개")
    c.metric("사용 방법", "TF-IDF")
    with st.expander("실제 데이터 출처 · 수집 시점 · 사용 범위"):
        inventory = frame[["company", "source_url", "report_id", "collected_at", "section"]].rename(columns={"company": "기업", "source_url": "사업보고서 원문", "report_id": "원문 ID", "collected_at": "수집 시점", "section": "분석한 절"})
        st.dataframe(inventory, column_config={"사업보고서 원문": st.column_config.LinkColumn("사업보고서 원문")}, hide_index=True, width="stretch")
        st.caption("분야별 주된 사업과 원문 공개 여부를 기준으로 선정한 기업 표본입니다. 전수조사가 아니며 분야별 기업 수가 다릅니다. 특정 제출본을 고정해 분석하며 최신 정정본 여부는 원문에서 확인하세요.")
    overview_tab,finance_tab,original_tab,map_tab,matrix_tab=st.tabs(['분야별 현황','매출·영업이익','기업별 주력·전체 원문','전략 지도','기업 간 유사도'])
    with overview_tab:
        counts=inventory_all.groupby('sector',sort=False).size().reset_index(name='기업 수').rename(columns={'sector':'분야'})
        st.plotly_chart(px.bar(counts,x='분야',y='기업 수',color='분야',color_discrete_sequence=COLORS),width='stretch',key='sector_counts')
        st.caption('각 분야에서 선정한 기업 수입니다. 분야 전체의 시장 규모를 뜻하지 않습니다.')
        st.dataframe(frame[['sector','company']].rename(columns={'sector':'분야','company':'분석 기업'}),hide_index=True,width='stretch')
        if selected_sector=='전체 분야':
            names=result.vectorizer.get_feature_names_out()
            indices=[i for i,name in enumerate(names) if ' ' not in name]
            profiles=np.vstack([np.asarray(result.matrix[np.flatnonzero((frame.sector==sector).to_numpy())].mean(axis=0)).ravel() for sector in counts['분야']])
            selected=set()
            for profile in profiles:
                selected.update(sorted(indices,key=lambda i:profile[i],reverse=True)[:5])
            terms=sorted(selected,key=lambda i:float(profiles[:,i].max()),reverse=True)
            heat=pd.DataFrame(profiles[:,terms],index=counts['분야'],columns=names[terms])
            fig=px.imshow(heat,color_continuous_scale='Teal',labels={'x':'단어','y':'분야','color':'평균 중요도'},aspect='auto')
            fig.update_layout(height=360); st.plotly_chart(fig,width='stretch',key='sector_keywords')
            st.caption('같은 단어 점수표로 계산한 분야별 평균입니다. 색이 진할수록 해당 표현을 중요하게 쓰는 기업이 많습니다. 분야별 상위 단어를 함께 표시합니다.')
    with finance_tab: financial_panel(frame)
    with original_tab:
        original_company=st.selectbox('주력 사업과 전체 원문을 볼 기업',frame.company.tolist(),key='original_company')
        original_index=frame.index[frame.company==original_company][0]
        row=frame.iloc[original_index]
        st.subheader(row.company+' · '+row.sector)
        st.caption('2025년 결산 사업보고서 · '+row.section+' · 수집 '+row.collected_at)
        st.link_button(row.company+' 출처 원문',row.source_url)
        st.write('**주력 사업을 읽는 방법:** 아래 기업 사업 설명에서 제품·서비스와 고객을 확인하고, 전체 원문의 주요 제품·연구개발 항목과 매출·영업이익을 함께 살펴보세요.')
        st.markdown('**기업 사업 설명 · 원문 발췌**')
        company_original(row,preview=True)
        st.subheader(row.company+' · 전체 사업 내용 원문')
        company_original(row)
    with map_tab:
        draw_map(result, frame.company, "company_map")
    with matrix_tab:
        fig = px.imshow(result.similarity, x=frame.company, y=frame.company, zmin=0, zmax=1,
                        color_continuous_scale="Teal", labels={"color": "코사인 유사도"})
        st.plotly_chart(fig, width="stretch")
    st.subheader("기업별 원문 비교")
    chosen = st.selectbox("기업 선택", frame.company.tolist())
    index = frame.index[frame.company == chosen][0]
    similar = neighbors(result, index)
    cards = st.columns(len(similar))
    for card, (other, score) in zip(cards, similar):
        card.metric(frame.iloc[other].company, f"{score:.3f}", help="공시 텍스트의 코사인 유사도")
    other = st.selectbox("비교 기업", [frame.iloc[i].company for i, _ in similar])
    other_index = frame.index[frame.company == other][0]
    common, distinct_a, distinct_b = comparison_terms(result, index, other_index)
    st.write("**공통 표현** · " + (", ".join(common) or "상위 공통 표현 없음"))
    left, right = st.columns(2)
    for column, row_index, terms in [(left, index, distinct_a), (right, other_index, distinct_b)]:
        row = frame.iloc[row_index]
        with column:
            st.markdown(f"**{row.company}**")
            st.write("상대적으로 높은 표현 · " + (", ".join(terms) or "없음"))
            for excerpt in evidence(row.text, common + terms):
                st.info(excerpt)
            st.link_button("출처 원문", row.source_url)
            st.caption(f"원문 ID: {row.report_id} · 절: {row.section} · 수집: {row.collected_at}")
            st.caption('기업별 주력·전체 원문 탭에서 회사별 전체 사업 내용과 표를 읽을 수 있습니다.')
    st.caption("이 지도는 공시 문구의 유사성을 보여줍니다. 실제 경쟁 관계나 규제 변화의 인과효과를 의미하지 않습니다.")
    method_note(result, "ko")
    with st.expander("데이터와 수집 기록"):
        collection_record(manifest)
        export = frame.copy()
        export["cluster"] = result.labels + 1
        csv_download(export, "기업 분석 CSV 다운로드", "company_analysis.csv")


def network_chart(edges):
    edges = edges.head(45)
    if edges.empty:
        st.info("두 문서 이상에서 같이 등장한 키워드 쌍이 없습니다.")
        return
    nodes = sorted(set(edges.keyword_a) | set(edges.keyword_b))
    positions = {node: (math.cos(2 * math.pi * i / len(nodes)), math.sin(2 * math.pi * i / len(nodes))) for i, node in enumerate(nodes)}
    fig = go.Figure()
    for row in edges.itertuples():
        a, b = positions[row.keyword_a], positions[row.keyword_b]
        fig.add_trace(go.Scatter(x=[a[0], b[0]], y=[a[1], b[1]], mode="lines", line=dict(color="rgba(22,117,104,.22)", width=1 + row.documents / max(edges.documents) * 4), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[positions[n][0] for n in nodes], y=[positions[n][1] for n in nodes], mode="markers+text", text=nodes,
                             textposition="top center", marker=dict(size=15, color=COLORS[0]), hoverinfo="text", showlegend=False))
    fig.update_layout(height=450, margin=dict(l=60, r=60, t=30, b=30), xaxis=dict(visible=False), yaxis=dict(visible=False), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    st.caption("위치는 읽기 편한 원형 배치입니다. 선의 굵기는 두 키워드가 함께 등장한 문서 수이며 인과관계가 아닙니다.")
    st.dataframe(edges.rename(columns={"keyword_a": "키워드 A", "keyword_b": "키워드 B", "documents": "동시 등장 문서 수"}), hide_index=True, width="stretch")


def papers_page():
    st.caption("02 / TECHNOLOGY EXPLORER")
    st.title("신기술 트렌드 탐색기")
    st.write("기술 분야별 실제 논문의 핵심 단어와 두 기간의 표본 변화를 살펴봅니다.")
    selected_field=st.selectbox('분석할 기술 분야',list(FIELDS),key='paper_field')
    dataset_name,default_query,hardware_only=FIELDS[selected_field]
    beginner_explanation("paper")
    with st.expander("검색 조건과 실제 데이터 수집", expanded=not (DATA / "processed" / "papers.csv").exists()):
        route = st.radio("수집 경로", ["OpenAlex · arXiv 논문으로 한정", "arXiv 직접 API"], horizontal=True)
        with st.form("arxiv_search"):
            query = st.text_area("수집 검색 조건",default_query if route.startswith('OpenAlex') else DEFAULT_QUERY)
            a, b = st.columns(2)
            with a:
                start_a = st.date_input("기간 A 시작", date(2025, 1, 1))
                end_a = st.date_input("기간 A 끝", date(2025, 8, 31))
            with b:
                start_b = st.date_input("기간 B 시작", date(2026, 1, 1))
                end_b = st.date_input("기간 B 끝", date(2026, 8, 31))
            limit = st.number_input("기간별 최신순 수집 상한", 2, 100, 60)
            submitted = st.form_submit_button("실제 논문 수집 및 분석")
        st.caption("같은 요청은 원본 캐시를 재사용합니다. 데이터가 기간별 상한에 걸리면 해당 기간의 후반부에 치우칠 수 있습니다.")
        if submitted:
            try:
                with st.spinner("arXiv 초록을 수집하는 중입니다..."):
                    windows = [("기간 A", str(start_a), str(end_a)), ("기간 B", str(start_b), str(end_b))]
                    frame, manifest = collect_openalex(int(limit),query,windows,hardware_only,dataset_name,selected_field) if route.startswith('OpenAlex') else collect(query,windows,int(limit))
                    st.session_state['papers_dataset_'+dataset_name]=(frame,manifest)
            except (ValueError, RuntimeError) as error:
                st.error(str(error))
    try:
        if 'papers_dataset_'+dataset_name in st.session_state:
            frame,manifest=st.session_state['papers_dataset_'+dataset_name]
        elif (DATA/'processed'/f'{dataset_name}.csv').exists():
            frame,manifest=read_dataset(DATA/'processed'/f'{dataset_name}.csv')
        else:
            st.info("이 분야의 실제 데이터는 위의 수집 버튼으로 가져올 수 있습니다.")
            st.stop()
        if len(frame) < 4:
            st.warning("검색 결과가 4개 미만입니다. 분석하려면 조건을 넓혀주세요.")
            st.stop()
        clusters = st.slider("주제 군집 수", 2, min(6, len(frame) - 1), min(4, len(frame) - 1), key="paper_k")
        result = cached_analysis(tuple(frame.title + ". " + frame.abstract), clusters, "en")
    except (ValueError, KeyError) as error:
        st.error(str(error))
        st.stop()
    periods = [record["period"] for record in manifest["periods"]]
    st.info("실제 데이터 수집 출처: " + manifest["source"] + ". 논문별 arXiv 원문과 수집 기록을 아래에서 확인할 수 있습니다.")
    st.caption("사용된 검색식: " + manifest["query"])
    if manifest.get("title_abstract_filter"):
        st.caption("추가 선별: 제목·초록에 hardware, chip, FPGA, ASIC, 메모리, NPU, GPU, accelerator 등 하드웨어 관련 표현이 직접 등장한 논문입니다. 칩 설계 외에 AI 하드웨어 활용 연구도 포함합니다.")
    if "OpenAlex" in manifest["source"]:
        st.caption("날짜 기준은 OpenAlex의 출판일입니다. arXiv 최초 제출일과 다를 수 있습니다. 분류와 갱신일도 OpenAlex의 주제 및 메타데이터 갱신일입니다.")
    shares = period_shares(frame, result.labels, periods)
    a, b, c = st.columns(3)
    a.metric("실제 논문", f"{len(frame)}편")
    b.metric(periods[0], f"{(frame.period == periods[0]).sum()}편")
    c.metric(periods[1], f"{(frame.period == periods[1]).sum()}편")
    st.warning("표본 내 주제 비중입니다. 검색어와 최신순 수집 상한으로 제한한 결과를 전체 연구량 증가나 시장 성장으로 해석할 수 없습니다.")
    if result.silhouette is not None and result.silhouette < 0.05:
        st.warning(f"현재 단어 기준 군집 분리가 약합니다(실루엣 {result.silhouette:.3f}). 뚜렷한 기술 분야나 주제 이동이 발견됐다고 단정하기 어렵습니다. 대표 초록을 읽고 탐색용으로 사용하세요.")
    topic_tab,share_tab,keyword_tab=st.tabs(['주제 지도','두 기간 비교','키워드 동시 출현'])
    with topic_tab:
        draw_map(result, frame.title, "paper_map")
        for label, keywords in result.keywords.items():
            with st.expander(f"군집 {label + 1} · {', '.join(keywords[:4])} · {(result.labels == label).sum()}편"):
                st.caption("대표 논문: 군집 중심에 가장 가까운 초록 3개")
                for i in representatives(result, label):
                    row = frame.iloc[i]
                    st.link_button(row.title, row.source_url)
                    st.caption(f"{row.published[:10]} · {row.paper_id}")
                    st.write(row.abstract)
    with share_tab:
        names=result.vectorizer.get_feature_names_out()
        valid=[i for i,name in enumerate(names) if ' ' not in name]
        prevalence=[]
        for period in periods:
            positions=np.flatnonzero((frame.period==period).to_numpy())
            prevalence.append(np.asarray((result.matrix[positions][:,valid]>0).sum(axis=0)).ravel()/max(1,len(positions)))
        delta=(prevalence[1]-prevalence[0])*100
        selected=[i for i in delta.argsort()[::-1] if prevalence[1][i]>=0.1 and delta[i]>0][:15]
        if selected:
            changes=pd.DataFrame({'단어':[names[valid[i]] for i in selected],'이전 표본 등장 비율':[prevalence[0][i] for i in selected],'최근 표본 등장 비율':[prevalence[1][i] for i in selected],'변화(%p)':[delta[i] for i in selected]})
            st.subheader('최근 표본에서 더 널리 등장한 단어')
            st.plotly_chart(px.bar(changes.sort_values('변화(%p)'),x='변화(%p)',y='단어',orientation='h',color_discrete_sequence=COLORS),width='stretch',key='keyword_change')
            st.caption('각 기간 논문 중 해당 단어가 한 번 이상 등장한 비율을 비교합니다. 20%에서 30%로 바뀌면 +10%p입니다. 연구 전체의 유행을 확정하는 지표는 아닙니다.')
            st.dataframe(changes,hide_index=True,width='stretch',column_config={c:st.column_config.NumberColumn(c,format='percent') for c in ['이전 표본 등장 비율','최근 표본 등장 비율']})
        fig = px.bar(shares, x="cluster", y="share", color="period", barmode="group", range_y=[0, 1],
                     color_discrete_sequence=COLORS, labels={"cluster": "주제 군집", "share": "표본 내 비중", "period": "기간"},
                     hover_data=["count", "sample_n"])
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(shares.rename(columns={"cluster": "군집", "period": "기간", "count": "논문 수", "sample_n": "기간 표본 수", "share": "비중"}), hide_index=True, width="stretch")
        if any(record["retained"] == 0 for record in manifest["periods"]):
            st.error("한 기간의 표본이 비어 있어 기간 간 비중 비교를 해석할 수 없습니다.")
    with keyword_tab:
        edges = cooccurrences(result)
        network_chart(edges)
        csv_download(edges, "키워드 동시 출현 CSV", "keyword_cooccurrence.csv")
    st.subheader("논문 원문 탐색")
    search = st.text_input("제목 또는 초록 검색", placeholder="예: memory, FPGA, quantization")
    matches = frame[(frame.title + " " + frame.abstract).str.contains(search, case=False, regex=False)].copy()
    if matches.empty:
        st.info("현재 표본에서 검색 결과가 없습니다.")
    else:
        paper_id = st.selectbox("논문 선택", matches.paper_id.tolist(), format_func=lambda value: frame.loc[frame.paper_id == value, "title"].iloc[0])
        row = frame[frame.paper_id == paper_id].iloc[0]
        readable_original(row.abstract)
        st.caption(f"기록된 날짜 {row.published} · 메타데이터 갱신 {row.updated} · 저자 {row.authors} · 분류 {row.categories}")
        st.link_button("arXiv 원문 페이지", row.source_url)
        if "metadata_url" in row:
            st.link_button("OpenAlex 메타데이터 출처", row.metadata_url)
    method_note(result, "en")
    with st.expander("검색 조건 · 수집 기록 · 재현 데이터"):
        collection_record(manifest)
        export = frame.copy()
        export["cluster"] = result.labels + 1
        csv_download(export, "논문 분석 CSV 다운로드", "paper_analysis.csv")
        st.download_button("수집 기록 JSON 다운로드", json.dumps(manifest, ensure_ascii=False, indent=2), "papers.manifest.json", "application/json")
