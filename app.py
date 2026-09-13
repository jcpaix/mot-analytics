import streamlit as st

from mot_analytics.ui import companies_page, papers_page

st.set_page_config(page_title="MOT Analytics", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
[data-testid="stMarkdownContainer"],
[data-testid="stAlert"],
[data-testid="stCaptionContainer"],
[data-testid="stText"] {
    word-break: keep-all;
    overflow-wrap: break-word;
    line-break: strict;
}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stCaptionContainer"] p,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stAlert"] p {
    line-height: 1.8;
    word-break: keep-all !important;
    overflow-wrap: break-word;
}
[data-testid="stText"] pre {
    white-space: pre-wrap;
    word-break: keep-all;
    overflow-wrap: break-word;
    line-height: 1.8;
}
[data-testid="stLinkButton"] a,
[data-testid="stLinkButton"] p {
    white-space: normal;
    word-break: keep-all;
    overflow-wrap: break-word;
    text-align: left;
}
.source-reader {font-family: sans-serif; font-size: 1rem; line-height: 2.1; word-break: keep-all; overflow-wrap: break-word; max-width: 76ch; margin: 0 auto;}
.source-reader p {line-height: 2.1 !important; margin: 0 0 1.4rem !important; word-break: keep-all !important;}
</style>
""", unsafe_allow_html=True)
with st.sidebar:
    st.markdown("## ◈ MOT Analytics")
    st.caption("공시와 논문으로 살펴보는 기술 전략")
page = st.navigation([
    st.Page(companies_page, title="기업 전략 지도", icon=":material/hub:", default=True, url_path="companies"),
    st.Page(papers_page, title="신기술 트렌드 탐색기", icon=":material/science:", url_path="technology"),
])
with st.sidebar:
    st.divider()
    st.caption("산업별 기업 공시 · 기술 분야별 논문\n\n실제 데이터와 출처를 함께 확인하는 분석")
page.run()
