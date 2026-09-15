from pathlib import Path
import json
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from server import app
from mot_analytics.storage import DATA,read_dataset
from mot_analytics import web_api

client=TestClient(app)

def uploaded_frame():
    frame,_=read_dataset(DATA/'processed/companies.csv')
    return frame[frame.sector.isin(['자동차·부품','바이오·제약'])].copy()

def test_actual_uploads_are_compared_within_each_industry():
    before=(DATA/'processed/companies.csv').read_bytes()
    response=client.post('/api/companies/analyze',json={'csv_text':uploaded_frame().to_csv(index=False),'clusters':3})
    assert response.status_code==200,response.text
    result=response.json();assert result['rows']==8 and result['stored'] is False
    for group in result['groups']:
        assert group['count']==4
        assert len(group['similarity'])==4
        assert all(r['sector']==group['sector'] for r in group['records'])
        assert len(group['coordinates'])==4
    assert (DATA/'processed/companies.csv').read_bytes()==before

def test_upload_rejects_script_links_and_missing_industry():
    f=uploaded_frame();f.iloc[0,f.columns.get_loc('source_url')]='javascript:alert(1)'
    assert client.post('/api/companies/analyze',json={'csv_text':f.to_csv(index=False)}).status_code==422
    f=uploaded_frame().drop(columns=['sector'])
    assert client.post('/api/companies/analyze',json={'csv_text':f.to_csv(index=False)}).status_code==422

def test_too_small_sector_keeps_original_without_cross_sector_fill():
    f=uploaded_frame().iloc[:5]
    result=client.post('/api/companies/analyze',json={'csv_text':f.to_csv(index=False)}).json()
    assert len(result['groups'])==2
    small=next(g for g in result['groups'] if g['count']==1)
    assert 'error' in small and 'similarity' not in small

def test_invalid_collection_does_not_make_requests(monkeypatch):
    def prohibited(*args,**kwargs):raise AssertionError('Network must not be called for overlapping periods')
    import requests
    monkeypatch.setattr(requests,'get',prohibited)
    body={'field':'반도체·AI 하드웨어','query':'neural network','start_a':'2025-01-01','end_a':'2025-08-31','start_b':'2025-06-01','end_b':'2025-12-31','per_period':2}
    response=client.post('/api/papers/collect',json=body)
    assert response.status_code==422,response.text

def test_actual_stored_api_response_transforms_without_shared_writes(monkeypatch,tmp_path):
    # Replay recorded provider responses, not fabricated papers.
    dataset,manifest=read_dataset(DATA/'processed/papers_semiconductor.csv')
    records=manifest['periods'];calls=[]
    class Response:
        def __init__(self,record):
            import hashlib
            self.url=record['request_url'];self.status_code=200
            self.content=next(p.read_bytes() for p in (DATA/'raw/openalex').glob('*.json') if hashlib.sha256(p.read_bytes()).hexdigest()==record['raw_sha256'])
        def raise_for_status(self):pass
        def json(self):return json.loads(self.content)
    def request(url,params,timeout):calls.append(params);return Response(records[len(calls)-1])
    import requests
    monkeypatch.setattr(requests,'get',request)
    before=(DATA/'processed/papers_semiconductor.csv').read_bytes()
    body={'field':'반도체·AI 하드웨어','query':manifest['query'],'start_a':'2025-01-01','end_a':'2025-08-31','start_b':'2026-01-01','end_b':'2026-08-31','per_period':2}
    response=client.post('/api/papers/collect',json=body)
    assert response.status_code==200,response.text
    payload=response.json();assert len(payload['records'])==4 and len(calls)==2
    assert payload['stored'] is False
    assert all(r['source_url'].startswith('https://arxiv.org/abs/') for r in payload['records'])
    assert [p['retained'] for p in payload['manifest']['periods']]==[2,2]
    assert (DATA/'processed/papers_semiconductor.csv').read_bytes()==before

def test_web_and_api_entrypoints():
    assert client.get('/api/health').json()['status']=='ok'
    page=client.get('/');assert page.status_code==200
    assert 'insights-ui.js' in page.text and 'workspace-ui.js' in page.text
    assert client.get('/insights.js').status_code==200
