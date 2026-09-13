"""Preserve official filing paragraphs, headings, and financial table spans."""
import hashlib
import json
import re
from bs4 import BeautifulSoup
from mot_analytics.storage import DATA, read_dataset, utc_now

def paragraph_lines(tag):
    copy=BeautifulSoup(str(tag),'html.parser')
    for br in copy.find_all('br'):br.replace_with('__MOT_BREAK__')
    return [' '.join(line.split()) for line in copy.get_text(' ',strip=True).split('__MOT_BREAK__') if line.strip()]

def table_structure(table):
    grid={}; row_count=0
    original_rows=[tr for tr in table.find_all('tr') if tr.find_parent('table') is table]
    for r,tr in enumerate(original_rows):
        row_count=r+1; c=0
        for cell in tr.find_all(['td','th'],recursive=False):
            while (r,c) in grid:c+=1
            text=cell.get_text(' ',strip=True)
            rows=min(200,int(cell.get('rowspan',1))); cols=min(80,int(cell.get('colspan',1)))
            for dr in range(rows):
                for dc in range(cols):grid[r+dr,c+dc]=text
            c+=cols
    if not grid:return None
    width=max(c for _,c in grid)+1
    matrix=[[grid.get((r,c),'') for c in range(width)] for r in range(max(row_count,max(r for r,_ in grid)+1))]
    unit=''
    if len(set(matrix[0]))==1 and '단위' in matrix[0][0]:unit=matrix.pop(0)[0]
    if not matrix:return None
    header_rows=2 if any(int(cell.get('rowspan',1))>1 or int(cell.get('colspan',1))>1 for cell in original_rows[1 if unit else 0].find_all(['td','th'],recursive=False)) and len(matrix)>2 else 1
    if header_rows==2 and any(re.fullmatch(r'\(?-?[\d,]+(?:\.\d+)?%?\)?',value.strip()) for value in matrix[1]):header_rows=1
    columns=[]
    for c in range(width):
        levels=list(dict.fromkeys(matrix[r][c] for r in range(header_rows) if matrix[r][c]))
        name=' / '.join(levels) or f'항목 {c+1}'
        columns.append(name)
    unique=[]
    for name in columns:
        count=columns[:len(unique)].count(name)
        unique.append(name+(f' ({count+1})' if count else ''))
    return {'type':'table','columns':unique,'rows':matrix[header_rows:],'unit':unit}

def structured_business(html):
    headings=list(re.finditer(r'<h2\b[^>]*>.*?</h2>',html,re.I|re.S))
    start=next(m for m in headings if '사업의 내용' in BeautifulSoup(m.group(),'html.parser').get_text())
    end=next(m for m in headings if m.start()>start.start() and '재무에 관한 사항' in BeautifulSoup(m.group(),'html.parser').get_text())
    soup=BeautifulSoup(html[start.start():end.start()],'html.parser')
    blocks=[]
    for tag in soup.find_all(['h2','h3','h4','p','table']):
        if tag.find_parent('table') is not None:continue
        if tag.name=='p' and tag.find_parent(['h2','h3','h4']) is not None:continue
        if tag.name=='table':
            cells=tag.find_all(['td','th'])
            if len(cells)==1 and len(cells[0].get_text(strip=True))>80:
                blocks.extend({'type':'paragraph','text':line,'level':None} for line in paragraph_lines(cells[0]))
                continue
            block=table_structure(tag)
            if block:blocks.append(block)
            continue
        for text in paragraph_lines(tag):
            heading=tag.name.startswith('h') or (len(text)<110 and bool(re.match(r'^(?:\d+\s*[.)]|\(\d+\)|[가-하]\s*[.)]|\[[^\]]+\])',text)))
            level=(0 if tag.name=='h2' else 1 if tag.name=='h3' else 2 if tag.name=='h4' else 3 if re.match(r'^[가-하]\s*[.)]',text) else 2 if re.match(r'^\d+\s*[.)]|^\(\d+\)',text) else 3) if heading else None
            if heading and blocks and blocks[-1]['type']=='heading' and re.sub(r'\s+','',blocks[-1]['text'])==re.sub(r'\s+','',text):continue
            blocks.append({'type':'heading' if heading else 'paragraph','text':text,'level':level})
    return blocks

def document_sections(blocks):
    sections=[]; parents={}; current=None; chapter='사업의 내용'
    for block in blocks:
        if block['type']=='heading':
            level=block.get('level',1 if re.match(r'^\d+\s*\.',block['text']) else 3)
            if level==0:continue
            if level==1:chapter=block['text']
            parents={k:v for k,v in parents.items() if k<level}; parents[level]=block['text']
            current={'id':len(sections),'title':' › '.join(parents[k] for k in sorted(parents)),'chapter':chapter,'blocks':[]}
            sections.append(current)
        else:
            if current is None:
                current={'id':0,'title':'사업의 내용','chapter':chapter,'blocks':[]}; sections.append(current)
            current['blocks'].append(block)
    return [section for section in sections if section['blocks']]

def business_keyword_text(blocks):
    """Use business overview, products, and R&D prose for company clouds."""
    paragraphs=[]; include=True
    for block in blocks:
        if block['type']=='heading' and block.get('level')==1:
            include=bool(re.search(r'사업.*개요|주요.*제품|주요.*서비스|연구개발',block['text']))
        elif block['type']=='paragraph' and include:
            paragraphs.append(block['text'])
        elif block['type']=='table' and include:
            for row in block['rows']:
                if any(len(value)>=60 and len(re.findall(r'[가-힣a-zA-Z]',value))>=20 for value in row):
                    paragraphs.append(' '.join(dict.fromkeys(row)))
    return '\n'.join(paragraphs)

def collect_documents():
    companies,_=read_dataset(DATA/'processed/companies.csv')
    records=[]
    for row in companies.itertuples():
        path=DATA/'raw/kind'/f'{row.report_id}.html'
        payload=path.read_bytes()
        records.append({'company':row.company,'report_id':row.report_id,'source_url':row.source_url,'collected_at':row.collected_at,'raw_sha256':hashlib.sha256(payload).hexdigest(),'section':row.section,'blocks':structured_business(payload.decode('utf-8-sig'))})
    path=DATA/'processed/company_documents.json'
    payload=json.dumps(records,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    path.write_bytes(payload)
    path.with_suffix('.manifest.json').write_text(json.dumps({'source':'한국거래소 KIND 사업보고서','documents':len(records),'created_at':utc_now(),'sha256':hashlib.sha256(payload).hexdigest(),'extraction':'II. 사업의 내용 only; original headings/paragraphs/table cell text; rowspan and colspan expanded, no financial values inferred'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Structured actual filings:',len(records), 'bytes:',len(payload),flush=True)
    return records

if __name__=='__main__':collect_documents()
