from bs4 import BeautifulSoup
from mot_analytics.documents import table_structure,document_sections,structured_business,business_keyword_text

def test_foreign_currency_table_spans_preserve_values():
    table=BeautifulSoup('<table><tr><td rowspan="2">구분</td><td colspan="2">자산</td><td colspan="2">부채</td></tr><tr><td>외화금액</td><td>원화환산액</td><td>외화금액</td><td>원화환산액</td></tr><tr><td>USD</td><td>110,799,089</td><td>158,985,613</td><td>4,851,311</td><td>6,961,146</td></tr></table>','html.parser').table
    result=table_structure(table)
    assert result['columns']==['구분','자산 / 외화금액','자산 / 원화환산액','부채 / 외화금액','부채 / 원화환산액']
    assert result['rows']==[['USD','110,799,089','158,985,613','4,851,311','6,961,146']]

def test_sections_keep_heading_separate_and_body_under_it():
    sections=document_sections([{'type':'heading','text':'7. 위험 관리','level':1},{'type':'heading','text':'3) 유동성','level':3},{'type':'paragraph','text':'회사는 유동성을 관리합니다.'}])
    assert len(sections)==1
    assert sections[0]['title']=='7. 위험 관리 › 3) 유동성'
    assert sections[0]['blocks'][0]['text']=='회사는 유동성을 관리합니다.'

def test_cloud_uses_business_prose_and_deduplicates_nested_headings():
    html='<h2><p>II. 사업의 내용</p></h2><table><tr><td>'+('연결회사는 메모리 설계를 주력으로 합니다. '*5)+'</td></tr></table><h3><p>1. 사업의 개요</p></h3><p>DRAM 메모리를 설계하고 공급합니다.</p><h3>4. 매출 및 수주상황</h3><p>가. 외화위험<br>액면금액과 재무 수치입니다.</p><h3>6. 주요계약 및 연구개발활동</h3><p>HBM 기술을 연구합니다.</p><table><tr><td>금액</td></tr><tr><td>123</td></tr></table><h2>III. 재무에 관한 사항</h2>'
    blocks=structured_business(html)
    assert sum(block.get('text')=='1. 사업의 개요' for block in blocks)==1
    assert any(block['type']=='heading' and block['text']=='가. 외화위험' for block in blocks)
    text=business_keyword_text(blocks)
    assert 'DRAM' in text and 'HBM' in text
    assert '메모리 설계를 주력' in text
    assert '액면금액' not in text and '123' not in text
    narrative='HBM 적층 기술을 연구하며 메모리 대역폭을 개선하고 있습니다. '*4
    assert narrative in business_keyword_text([{'type':'heading','text':'6. 연구개발','level':1},{'type':'table','rows':[['HBM',narrative,'123']]}])
