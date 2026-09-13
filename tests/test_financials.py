import pytest
from mot_analytics.analysis import ko_tokens
from mot_analytics.financials import extract_summary

def filing(unit='백만원',headers='제3기 제2기 제1기',basis='요약재무정보(연결)'):
    return f'<h2>III. 재무에 관한 사항</h2><h3>1. 요약재무정보</h3><p>{basis}</p><p>(단위:{unit})</p><table><tr><td>{headers}</td></tr><tr><td>매출액</td><td>1,234</td><td>900</td><td>800</td></tr><tr><td>영업이익</td><td>(100)</td><td>90</td><td>80</td></tr></table><h3>2. 연결재무제표</h3>'

def test_financial_units_and_losses():
    rows=extract_summary(filing())
    assert rows[0]['value_krw']==1_234_000_000
    assert rows[3]['value_krw']==-100_000_000
    assert rows[0]['year']==2025 and rows[2]['year']==2023
    assert rows[0]['basis']=='연결'

def test_missing_basis_and_wrong_years_rejected():
    with pytest.raises(ValueError):extract_summary(filing(basis='요약재무정보'))
    with pytest.raises(ValueError):extract_summary(filing(headers='2024년 2023년 2022년'))

def test_separate_only_with_explicit_no_consolidated_statement():
    rows=extract_summary(filing(unit='원',basis='요약재무정보')+'<p>해당사항 없습니다.</p>')
    assert rows[0]['basis']=='별도' and rows[0]['value_krw']==1234

def test_korean_filler_words_removed_and_technical_words_kept():
    assert ko_tokens('따라 있으며 당사는 등의 같습니다 제78기 DRAM 메모리 클라우드 신약')==['dram','메모리','클라우드','신약']
