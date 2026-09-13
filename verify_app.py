from streamlit.testing.v1 import AppTest
import json
from mot_analytics.storage import DATA, read_dataset

companies,_=read_dataset(DATA/"processed/companies.csv")

def verify_company_scope(at,sector):
    allowed=set(companies[companies.sector==sector].company)
    comparison=next(box for box in at.selectbox if box.label=="기업 선택")
    assert set(comparison.options)==allowed, (sector,comparison.options)
    peers=next(box for box in at.selectbox if box.label=="비교 기업")
    assert set(peers.options)<=allowed
    charts=[json.loads(chart.proto.spec) for chart in at.get("plotly_chart")]
    matrices=[trace for chart in charts for trace in chart["data"] if trace.get("type")=="heatmap" and set(trace.get("x",[]))==allowed]
    assert len(matrices)==1,(sector,"Missing within-sector matrix")
    assert set(matrices[0]["y"])==allowed
    assert "분야별 현황" in [tab.label for tab in at.tabs]
    assert not any(trace.get("type")=="bar" and set(trace.get("x",[]))==set(companies.sector) for chart in charts for trace in chart["data"]), "Company count chart still visible"
from mot_analytics.fields import FIELDS

for function,selector,choices in [('companies_page','company_sector',['전체 분야','반도체','IT·플랫폼·게임','자동차·부품','바이오·제약']),('papers_page','paper_field',list(FIELDS))]:
    at=AppTest.from_string('import streamlit as st\nfrom mot_analytics.ui import '+function+'\nst.set_page_config(layout="wide")\n'+function+'()').run(timeout=60)
    for choice in choices:
        at.selectbox(key=selector).select(choice).run(timeout=60)
        assert len(at.exception)==0,[(e.message,e.stack_trace) for e in at.exception]
        assert not len(at.get('imgs')) and not len(at.get('image')), 'Removed word cloud still visible'
        assert len(at.get('plotly_chart'))>0, 'Analysis charts missing'
        assert len(at.get('json'))==0,'Code-style metadata visible'
        if function=="companies_page":
            if choice=="전체 분야":
                for sector in dict.fromkeys(companies.sector):
                    at.selectbox(key="company_similarity_sector").select(sector).run(timeout=60)
                    assert not at.exception,[(e.message,e.stack_trace) for e in at.exception]
                    verify_company_scope(at,sector)
                    print("Whole-data view: similarity limited to",sector,flush=True)
            else:verify_company_scope(at,choice)
        print(function,choice,[m.value for m in at.metric],flush=True)
