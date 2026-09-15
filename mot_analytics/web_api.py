"""Request-scoped analysis; uploads and API responses are not shared between visitors."""
import csv
import io
import re
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router=APIRouter(prefix='/api')

class UploadRequest(BaseModel):
    csv_text: str=Field(min_length=1,max_length=2_000_000)
    clusters: int=Field(default=3,ge=2,le=6)

class PaperRequest(BaseModel):
    field: str
    query: str=Field(min_length=2,max_length=400)
    start_a: date
    end_a: date
    start_b: date
    end_b: date
    per_period: int=Field(default=30,ge=2,le=60)
    route: str='openalex'

@router.get('/health')
def health():return {'status':'ok','analysis':'TF-IDF / cosine / KMeans / SVD','uploads':'request-scoped'}

def safe_link(value):
    parsed=urlparse(str(value))
    return parsed.scheme in {'https','http'} and bool(parsed.hostname) and not parsed.username

@router.post('/companies/analyze')
def analyze_upload(body:UploadRequest):
    import pandas as pd
    import numpy as np
    from threadpoolctl import threadpool_limits
    from mot_analytics.analysis import analyze, comparison_terms, evidence
    from mot_analytics.dart import validate_companies
    try:
        frame=pd.read_csv(io.StringIO(body.csv_text.lstrip('\ufeff')),dtype=str,keep_default_na=False)
        if len(frame)>60:raise ValueError('기업 CSV는 최대 60개 기업까지 분석합니다.')
        frame=validate_companies(frame)
        if 'is_example' in frame and frame.is_example.str.lower().isin(['true','1','yes']).any():raise ValueError('가상 예시로 표시된 자료는 분석하지 않습니다.')
        if not frame.source_url.map(safe_link).all():raise ValueError('출처는 올바른 http 또는 https 원문 주소여야 합니다.')
        if frame.text.str.len().max()>150_000:raise ValueError('기업별 원문은 150,000자 이하로 입력하세요.')
        if 'sector' not in frame:raise ValueError('같은 분야끼리 비교하려면 sector(산업 분야) 열이 필요합니다.')
        if frame.sector.str.strip().eq('').any():raise ValueError('산업 분야를 모두 입력하세요.')
        groups=[]
        for sector,part in frame.groupby('sector',sort=False):
            part=part.reset_index(drop=True)
            if len(part)<4:
                groups.append({'sector':sector,'count':len(part),'error':'같은 분야에 서로 다른 기업 원문이 최소 4개 필요합니다.','records':part.to_dict('records')});continue
            with threadpool_limits(limits=1):result=analyze(part.text,body.clusters,'ko')
            pairs={}
            for i in range(len(part)):
                order=np.argsort(-result.similarity[i],kind='stable')
                for j in [int(j) for j in order if j!=i][:3]:
                    common,a,b=comparison_terms(result,i,j)
                    pairs[f'{i}:{j}']={'common':common,'left':a,'right':b,'left_evidence':evidence(part.iloc[i].text,common+a),'right_evidence':evidence(part.iloc[j].text,common+b)}
            groups.append({'sector':sector,'count':len(part),'records':part.to_dict('records'),'companies':part.company.tolist(),'similarity':result.similarity.tolist(),'labels':result.labels.tolist(),'coordinates':result.coordinates.tolist(),'keywords':result.keywords,'variance':result.explained_variance,'pairs':pairs})
        return {'groups':groups,'rows':len(frame),'source':'사용자 업로드; 출처의 진위와 추출 범위는 자동 검증하지 않았습니다.','stored':False}
    except (ValueError,pd.errors.ParserError,UnicodeDecodeError) as error:raise HTTPException(422,str(error)) from error

@router.post('/papers/collect')
def collect_papers(body:PaperRequest):
    from mot_analytics.fields import FIELDS
    from mot_analytics.public_data import collect_openalex
    from mot_analytics.arxiv import collect
    if body.field not in FIELDS:raise HTTPException(422,'지원하는 기술 분야를 선택하세요.')
    if body.route not in {'openalex','arxiv'}:raise HTTPException(422,'수집 경로를 확인하세요.')
    periods=[('기간 A',body.start_a.isoformat(),body.end_a.isoformat()),('기간 B',body.start_b.isoformat(),body.end_b.isoformat())]
    try:
        with TemporaryDirectory(prefix='mot-analysis-') as directory:
            if body.route=='arxiv':
                frame,manifest=collect(body.query,periods,body.per_period,cache_dir=directory)
                frame['field']=body.field
            else:
                frame,manifest=collect_openalex(body.per_period,body.query,periods,FIELDS[body.field][2],FIELDS[body.field][0],body.field,data_dir=Path(directory),save=False)
        return {'records':frame.to_dict('records'),'manifest':manifest,'field':body.field,'stored':False}
    except (ValueError,RuntimeError) as error:raise HTTPException(422,str(error)) from error
    except Exception as error:
        import requests
        if isinstance(error,requests.RequestException):
            status=getattr(error.response,'status_code',None)
            message='자료 제공처가 수집 요청을 처리하지 못했습니다.'
            if status in (401,403):message+=' 제공처의 인증 또는 접근 권한이 필요합니다.'
            elif status==429:message+=' 요청 한도에 도달했으므로 잠시 후 다시 시도하세요.'
            raise HTTPException(502,message+' 저장된 수집본은 계속 볼 수 있습니다.') from error
        raise
