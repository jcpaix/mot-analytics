"""Export verified source data and the existing Python analysis for public viewing."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json, shutil, hashlib, html, re
import numpy as np
from threadpoolctl import threadpool_limits
threadpool_limits(limits=1)
from plotly.offline import get_plotlyjs
from mot_analytics.storage import DATA,read_dataset
from mot_analytics.analysis import analyze,tfidf_features,comparison_terms,evidence,cooccurrences,period_shares,representatives
from mot_analytics.fields import FIELDS
from mot_analytics.documents import document_sections,business_description_text
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dist';OUT.mkdir(exist_ok=True)
(OUT/'downloads').mkdir(exist_ok=True)

def dataset(name):
    path=DATA/'processed'/f'{name}.csv'
    frame,manifest=read_dataset(path)
    shutil.copyfile(path,OUT/'downloads'/path.name)
    return frame,manifest

def variant(result,frame=None):
    item={'labels':result.labels.tolist(),'coordinates':result.coordinates.tolist(),'keywords':result.keywords,'variance':result.explained_variance,'silhouette':result.silhouette}
    if frame is not None:
        item['shares']=period_shares(frame,result.labels,list(dict.fromkeys(frame.period))).to_dict('records')
        item['representatives']={int(label):representatives(result,int(label)) for label in set(result.labels)}
    return item

def guide_html():
    lines=(ROOT/'reports/project_guide.md').read_text(encoding='utf-8').splitlines()
    result=[]
    for line in lines:
        if not line.strip():continue
        safe=html.escape(line)
        if line.startswith('## '):result.append('<h2>'+safe[3:]+'</h2>')
        elif line.startswith('# '):result.append('<h1>'+safe[2:]+'</h1>')
        else:
            safe=re.sub(r'https://[^\s<]+',lambda m:'<a href="'+m.group()+'" target="_blank" rel="noopener">'+m.group()+'</a>',safe)
            result.append('<p>'+safe+'</p>')
    return ''.join(result)

companies,company_manifest=dataset('companies');financials,finance_manifest=dataset('financials')
doc_path=DATA/'processed/company_documents.json'
doc_manifest=json.loads(doc_path.with_suffix('.manifest.json').read_text(encoding='utf-8'))
assert hashlib.sha256(doc_path.read_bytes()).hexdigest()==doc_manifest['sha256']
documents={r['report_id']:r for r in json.loads(doc_path.read_text(encoding='utf-8'))}
records=[]
for row in companies.to_dict('records'):
    assert str(row['is_example']).lower()=='false'
    record=documents[row['report_id']];assert record['source_url']==row['source_url']
    paragraphs=business_description_text(record['blocks']).splitlines()
    own=[text for text in paragraphs if re.search(r'당사|연결회사|연결실체|회사는|회사가',text)]
    records.append({**{k:v for k,v in row.items() if k!='text'},'preview':(own or paragraphs)[:2],'sections':document_sections(record['blocks'])})
sectors=list(dict.fromkeys(companies.sector));comparisons={}
for sector in sectors:
    frame=companies[companies.sector==sector].reset_index(drop=True)
    variants={};base=None
    for k in range(2,min(6,len(frame)-1)+1):
        result=analyze(tuple(frame.text),k,'ko');variants[k]=variant(result)
        if base is None:base=result
    pairs={}
    for i in range(len(frame)):
        for j in range(len(frame)):
            if i==j:continue
            common,a,b=comparison_terms(base,i,j)
            pairs[f'{i}:{j}']={'common':common,'left':a,'right':b,'left_evidence':evidence(frame.iloc[i].text,common+a),'right_evidence':evidence(frame.iloc[j].text,common+b)}
    comparisons[sector]={'companies':frame.company.tolist(),'similarity':base.similarity.tolist(),'variants':variants,'pairs':pairs}
    print('Exported company field:',sector,flush=True)
matrix,vectorizer=tfidf_features(tuple(companies.text),'ko')
names=vectorizer.get_feature_names_out();single=[i for i,n in enumerate(names) if ' ' not in n]
profiles=np.vstack([np.asarray(matrix[np.flatnonzero((companies.sector==sector).to_numpy())].mean(axis=0)).ravel() for sector in sectors])
selected=set()
for profile in profiles:selected.update(sorted(single,key=lambda i:profile[i],reverse=True)[:5])
terms=sorted(selected,key=lambda i:float(profiles[:,i].max()),reverse=True)
overview={'sectors':sectors,'counts':[int((companies.sector==s).sum()) for s in sectors],'terms':names[terms].tolist(),'profiles':profiles[:,terms].tolist()}
papers={}
for field,(name,query,hardware) in FIELDS.items():
    frame,manifest=dataset(name);assert len(frame)==120
    texts=(frame.title+' '+frame.abstract).tolist();variants={};base=None
    for k in range(2,9):
        result=analyze(texts,k,'en');variants[k]=variant(result,frame)
        if base is None:base=result
    names=base.vectorizer.get_feature_names_out();indices=[i for i,n in enumerate(names) if ' ' not in n]
    periods=list(dict.fromkeys(frame.period));rates=[]
    for period in periods:
        rows=np.flatnonzero((frame.period==period).to_numpy());rates.append(np.asarray((base.matrix[rows]>0).mean(axis=0)).ravel())
    a,b=rates;indices=[i for i in indices if (a[i]+b[i])*60>=4]
    ranked=sorted(indices,key=lambda i:(abs(b[i]-a[i]),a[i]+b[i]),reverse=True)[:40]
    changes=[{'term':str(names[i]),'previous':float(a[i]),'recent':float(b[i]),'change':float((b[i]-a[i])*100),'previous_n':int(round(a[i]*60)),'recent_n':int(round(b[i]*60))} for i in ranked]
    papers[field]={'dataset':name,'records':frame.to_dict('records'),'manifest':manifest,'variants':variants,'changes':changes,'edges':cooccurrences(base).head(45).to_dict('records')}
    print('Exported paper field:',field,flush=True)
data={'companies':records,'company_manifest':company_manifest,'financials':financials.to_dict('records'),'finance_manifest':finance_manifest,'overview':overview,'comparisons':comparisons,'papers':papers,'guide':guide_html(),'collected_date':'2026-09-13'}
(OUT/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n',encoding='utf-8',newline='\n')
(OUT/'plotly.min.js').write_text(get_plotlyjs(),encoding='utf-8',newline='\n')
for name in ['index.html','app.js','styles.css']:
    shutil.copyfile(ROOT/'web'/name,OUT/name)
print('Public export:',len(records),'companies,',sum(len(v['records']) for v in papers.values()),'field-paper samples,',len(financials),'financial values',flush=True)
