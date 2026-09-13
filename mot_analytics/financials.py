"""Conservative extraction from filing summary financial tables, with evidence."""
import re
from itertools import islice
from bs4 import BeautifulSoup, NavigableString
import pandas as pd
from mot_analytics.storage import DATA, read_dataset, write_dataset

def extract_summary(html):
    heading = next((m for m in re.finditer(r'<h2\b[^>]*>.*?</h2>', html, re.I | re.S) if '재무에 관한 사항' in m.group()), None)
    if heading is None:
        raise ValueError('재무 절 없음')
    fragment = html[heading.end():heading.end()+100000]
    cutoff = next((m.start() for m in re.finditer(r'<h3\b[^>]*>.*?</h3>',fragment,re.I|re.S) if re.search(r'2\s*\.\s*연결재무제표|4\s*\.\s*재무제표',BeautifulSoup(m.group(),'html.parser').get_text())), len(fragment))
    soup = BeautifulSoup(fragment[:cutoff], 'html.parser')
    for table in soup.find_all('table'):
        metrics = {}
        for tr in table.find_all('tr'):
            cells = [re.sub(r'\s+','',c.get_text()) for c in tr.find_all(['td','th'],recursive=False)]
            if not cells:
                continue
            label=re.sub(r'^[IVXⅠⅡⅢⅣⅤㆍ·]+[.．]?','',cells[0])
            metric = {'매출액':'매출액','영업수익':'매출액','수익(매출액)':'매출액','영업이익':'영업이익','영업이익(손실)':'영업이익','영업손익':'영업이익','영업손실':'영업이익'}.get(label)
            if metric and len(cells) in (3,4) and all(re.fullmatch(r'[-(]?[\d,]+(?:\.\d+)?\)?',v) for v in cells[1:]):
                metrics[metric] = (cells[1:],label=='영업손실')
        if set(metrics) != {'매출액','영업이익'}:
            continue
        context = ' '.join(reversed(list(islice((str(item) for item in table.previous_elements if isinstance(item, NavigableString)),35))))
        header=' '.join(tr.get_text(' ',strip=True) for tr in table.find_all('tr')[:4])
        units = re.findall(r'단위\s*[:：]\s*(백만원|천원|억원|원)', context+' '+header)
        if not units:
            continue
        unit = units[-1]
        basis_matches = list(re.finditer(r'요약\s*연결|연결\s*재무|요약\s*별도|별도\s*재무|요약\s*개별|개별\s*재무|요약\s*재무정보\s*\(\s*(?:연결|별도)',context))
        if not basis_matches:
            next_heading=next((m for m in re.finditer(r'<h3\b[^>]*>.*?</h3>',fragment,re.I|re.S) if re.search(r'2\s*\.\s*연결재무제표',BeautifulSoup(m.group(),'html.parser').get_text())),None)
            following=BeautifulSoup(fragment[next_heading.end():next_heading.end()+1500],'html.parser').get_text(' ',strip=True) if next_heading else ''
            if not re.search(r'해당\s*사항(?:이)?\s*없|작성하지\s*않',following[:220]):
                continue
            basis='별도'
            context+=' 연결재무제표 절: '+following[:220]
        else:
            basis = '연결' if '연결' in basis_matches[-1].group() else '별도'
        terms=re.findall(r'제\s*(\d+)\s*(?:\([^)]*\))?\s*기',header)
        terms=list(dict.fromkeys(terms))
        count=len(metrics['매출액'][0])
        if len(metrics['영업이익'][0])!=count:
            continue
        years=list(dict.fromkeys(re.findall(r'(202[3-5])\s*(?:년|[./])',header)))
        if years and years[:count]!=['2025','2024','2023'][:count]:
            continue
        if not years and (len(terms)!=count or [int(x) for x in terms] != list(range(int(terms[0]),int(terms[0])-count,-1))):
            continue
        multiplier={'원':1,'천원':1000,'백만원':1000000,'억원':100000000}[unit]
        rows=[]
        audit_note='공시의 요약재무정보에 의견거절 표시가 있음' if '의견거절' in soup.get_text(' ',strip=True)[:1000] else ''
        for metric,(values,loss) in metrics.items():
            for year,value in zip([2025,2024,2023],values):
                numeric=float(value.replace(',','').replace('(','-').replace(')',''))
                if loss: numeric=-abs(numeric)
                rows.append({'year':year,'metric':metric,'value_krw':round(numeric*multiplier),'original_value':value,'original_unit':unit,'basis':basis,'audit_note':audit_note,'table_header':header,'evidence_context':context[-1600:]})
        return rows
    raise ValueError('연도·단위·연결/별도 기준이 확인되는 3개년 요약 표 없음')

def collect_financials():
    companies,_=read_dataset(DATA/'processed/companies.csv')
    rows,errors=[],[]
    for company in companies.itertuples():
        try:
            html=(DATA/'raw/kind'/f'{company.report_id}.html').read_text(encoding='utf-8-sig')
            found=extract_summary(html)
            for row in found:
                row.update(company=company.company,sector=company.sector,source_url=company.source_url,report_id=company.report_id,collected_at=company.collected_at,section='III. 재무에 관한 사항 / 요약재무정보')
            rows.extend(found)
            print(company.company,found[0]['basis'],found[0]['original_unit'],[(r['metric'],r['year'],r['original_value']) for r in found],flush=True)
        except ValueError as error:
            errors.append({'company':company.company,'reason':str(error)})
    frame=pd.DataFrame(rows)
    if frame.empty:
        raise ValueError('검증 가능한 재무 표 없음')
    manifest={'source':'한국거래소 KIND 사업보고서 / III. 요약재무정보','fiscal_year':2025,'currency':'KRW','extraction':'2-3 year summary tables with verified fiscal cover, descending year/term headers, explicit unit and consolidated/separate context; consolidated table preferred by document order. Missing years remain missing.','missing_records':errors,'limitations':'Rounded summary values; audit qualifications, restatements and continued/discontinued operations follow each filing. No sector-total market-size interpretation.'}
    write_dataset(frame,DATA/'processed/financials.csv',manifest)
    return frame,manifest

if __name__=='__main__':
    collect_financials()
