import sys,json,hashlib,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mot_analytics.storage import DATA,read_dataset
from mot_analytics.fields import FIELDS
root=Path(__file__).resolve().parents[1];out=root/'dist'
payload=json.loads((out/'data.json').read_text(encoding='utf-8'))
companies,_=read_dataset(DATA/'processed/companies.csv')
assert len(payload['companies'])==22
assert payload['overview']['counts']==[10,4,4,4]
assert {r['company'] for r in payload['companies']}==set(companies.company)
for sector,comparison in payload['comparisons'].items():
    allowed=companies[companies.sector==sector].reset_index(drop=True)
    assert comparison['companies']==allowed.company.tolist()
    assert len(comparison['similarity'])==len(allowed)
    assert all(len(row)==len(allowed) for row in comparison['similarity'])
    assert all(abs(comparison['similarity'][i][i]-1)<1e-10 for i in range(len(allowed)))
    assert len(comparison['pairs'])==len(allowed)*(len(allowed)-1)
    for v in comparison['variants'].values():assert len(v['labels'])==len(allowed)
for row in payload['companies']:
    source=companies[companies.company==row['company']].iloc[0]
    assert row['source_url']==source.source_url
    assert row['sections'],row['company']
financials,_=read_dataset(DATA/'processed/financials.csv')
assert payload['financials']==financials.to_dict('records')
assert len(payload['financials'])==130
names=['companies','financials']
for field,(name,*_) in FIELDS.items():
    original,_=read_dataset(DATA/'processed'/f'{name}.csv')
    sample=payload['papers'][field]
    assert sample['records']==original.to_dict('records')
    assert len(sample['records'])==120
    assert original.period.value_counts().tolist()==[60,60]
    assert len(sample['variants'])==7
    names.append(name)
for name in names:
    original=DATA/'processed'/f'{name}.csv';copied=out/'downloads'/original.name
    assert original.read_bytes()==copied.read_bytes(),name
for file in ['index.html','styles.css','app.js','plotly.min.js']:
    assert (out/file).is_file()
assert '<script src="plotly.min.js"' in (out/'index.html').read_text(encoding='utf-8')
assert not list(out.rglob('.env*'))
print('Public data verified: 22 firms, 130 actual financial values, 4 x 120 paper samples, industry-only comparisons and identical source downloads.')
