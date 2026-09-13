from streamlit.testing.v1 import AppTest
from mot_analytics.fields import FIELDS

for function,selector,choices in [('companies_page','company_sector',['전체 분야','반도체','IT·플랫폼·게임','자동차·부품','바이오·제약']),('papers_page','paper_field',list(FIELDS))]:
    at=AppTest.from_string('import streamlit as st\nfrom mot_analytics.ui import '+function+'\nst.set_page_config(layout="wide")\n'+function+'()').run(timeout=60)
    for choice in choices:
        at.selectbox(key=selector).select(choice).run(timeout=60)
        assert len(at.exception)==0,[(e.message,e.stack_trace) for e in at.exception]
        assert len(at.get('imgs')) or len(at.get('image')), 'Word cloud missing'
        assert len(at.get('json'))==0,'Code-style metadata visible'
        print(function,choice,[m.value for m in at.metric],flush=True)
