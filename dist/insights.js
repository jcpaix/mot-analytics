(function(root){
'use strict';
const finite=n=>n!==null&&n!==undefined&&Number.isFinite(Number(n));
function median(values){const a=values.filter(finite).map(Number).sort((a,b)=>a-b);if(!a.length)return null;const i=Math.floor(a.length/2);return a.length%2?a[i]:(a[i-1]+a[i])/2;}
function companyFacts(data,name){
 const company=data.companies.find(c=>c.company===name);if(!company)return null;
 const rows=data.financials.filter(r=>r.company===name);
 function year(y){const revenue=rows.find(r=>Number(r.year)===y&&r.metric==='매출액'),profit=rows.find(r=>Number(r.year)===y&&r.metric==='영업이익');const rv=revenue?Number(revenue.value_krw):null,pv=profit?Number(profit.value_krw):null;
 return {year:y,revenue:rv,profit:pv,basis:revenue?.basis||profit?.basis||null,margin:rv>0&&pv!==null?pv/rv*100:null,audit:[...new Set([revenue?.audit_note,profit?.audit_note].filter(Boolean))].join(' · '),source:revenue?.source_url||profit?.source_url||company.source_url};}
 const latest=year(2025),previous=year(2024);const consistent=latest.basis!==null&&latest.basis===previous.basis;
 let profitChange='판단 자료 부족';
 if(consistent&&latest.profit!==null&&previous.profit!==null){const a=previous.profit,b=latest.profit;profitChange=a<0&&b>0?'흑자 전환':a>0&&b<0?'적자 전환':a<0&&b<0?(b>a?'적자 축소':b<a?'적자 확대':'적자 유지'):b>a?'영업이익 증가':b<a?'영업이익 감소':'영업이익 유지';}
 return {company,latest,previous,history:[year(2023),previous,latest],growth:consistent&&previous.revenue>0&&latest.revenue!==null?(latest.revenue/previous.revenue-1)*100:null,profitDelta:consistent&&latest.profit!==null&&previous.profit!==null?latest.profit-previous.profit:null,marginDelta:consistent&&latest.margin!==null&&previous.margin!==null?latest.margin-previous.margin:null,profitChange};
}
function benchmark(data,name){const own=companyFacts(data,name);if(!own)return null;const inSector=data.companies.filter(c=>c.sector===own.company.sector&&c.company!==name).map(c=>companyFacts(data,c.company));const included=inSector.filter(f=>f.latest.basis===own.latest.basis&&!f.latest.audit);return {own,peers:included,excluded:inSector.filter(f=>!included.includes(f)).map(f=>({company:f.company.company,reason:f.latest.audit?'감사 관련 주의 사항':f.latest.basis!==own.latest.basis?'연결·별도 기준 다름':'자료 부족'})),growthMedian:median(included.map(f=>f.growth)),marginMedian:median(included.map(f=>f.latest.margin)),growthN:included.filter(f=>f.growth!==null).length,marginN:included.filter(f=>f.latest.margin!==null).length};}
const concepts={
 '반도체·AI 하드웨어':[
 ['대규모 언어모델','llm(s)?|large language models?','언어모델을 칩에서 실행할 때 필요한 처리량과 메모리 요구를 다룹니다.','목표 모델 크기와 토큰 처리속도, 메모리 용량을 함께 확인하세요.'],
 ['추론 실행','inference','학습된 모델로 새 입력의 결과를 계산하는 단계입니다.','서버용인지 기기 내부 실행인지, 지연시간·비용·정확도의 조건을 확인하세요.'],
 ['양자화·저정밀 연산','quantiz\\w*|low[- ]precision|mixed[- ]precision','숫자의 표현 정밀도를 줄여 메모리와 계산 부담을 낮추는 기술입니다.','정확도 손실과 속도·전력 개선을 같은 모델에서 비교했는지 확인하세요.'],
 ['메모리 병목','memory bandwidth|memory[- ]bound|memory bottleneck|dram|sram|hbm','연산기에 데이터를 공급하는 속도와 저장 공간을 다룹니다.','메모리 종류·용량·대역폭과 실제 모델 실행 결과를 확인하세요.'],
 ['메모리 내 연산','in[- ]memory computing|processing[- ]in[- ]memory|compute[- ]in[- ]memory','데이터를 멀리 이동시키는 부담을 줄이도록 메모리 가까이에서 계산합니다.','지원 연산, 공정 조건, 주변 회로까지 포함한 전력을 확인하세요.'],
 ['전력·에너지 효율','energy[- ]efficien\\w*|power consumption|energy consumption|low[- ]power','같은 계산을 수행할 때 사용하는 에너지와 전력을 다룹니다.','정확도와 작업량을 같게 맞춘 효율인지 확인하세요.'],
 ['FPGA','fpga(s)?','개발 후에도 회로 구성을 바꿀 수 있는 반도체를 사용합니다.','시제품 결과인지 실제 제품 배치인지, 사용 자원과 주파수를 확인하세요.'],
 ['뉴로모픽','neuromorphic|spiking neural','신경계의 동작에서 영감을 얻은 연산 구조와 스파이킹 모델입니다.','일반 신경망과 비교한 데이터·정확도·하드웨어 조건을 확인하세요.']],
 'AI·소프트웨어':[
 ['추론 실행','inference','학습된 모델을 실제 요청에 사용하는 과정입니다.','성능 개선이 응답시간·비용·정확도 중 어디에 있는지 확인하세요.'],
 ['검색 증강 생성','retrieval[- ]augmented|rag','외부 문서를 찾아 답변 생성에 사용하는 방식입니다.','검색 정확도와 답변 근거의 일치 여부를 확인하세요.'],
 ['AI 에이전트','agents?|agentic','목표에 따라 도구를 호출하거나 여러 단계를 수행하는 시스템입니다.','작업 성공률, 도구 오류, 비용, 사람이 개입한 조건을 확인하세요.'],
 ['추론·문제 해결','reasoning|chain[- ]of[- ]thought','여러 단계가 필요한 문제를 푸는 모델의 능력과 방법을 다룹니다.','성능 향상이 추가 연산량이나 평가 데이터 노출 때문인지 확인하세요.'],
 ['멀티모달','multimodal|multi[- ]modal|vision[- ]language','텍스트·이미지·음성 등 여러 종류의 입력을 함께 사용합니다.','어떤 입력 조합과 실제 작업에서 개선되었는지 확인하세요.'],
 ['미세조정','fine[- ]tun\\w*|finetun\\w*','이미 학습된 모델을 특정 과제나 데이터에 맞게 조정합니다.','학습 데이터 규모와 일반 과제 성능 저하 여부를 확인하세요.'],
 ['안전·신뢰성','hallucination(s)?|jailbreak(s)?|adversarial|alignment','잘못된 생성이나 공격, 의도와 다른 동작을 다룹니다.','평가 사례의 범위와 실패가 남는 조건을 확인하세요.']],
 '자동차·자율주행':[
 ['센서 융합','sensor fusion|multi[- ]sensor|camera[- ]lidar','카메라·라이다 등 서로 다른 센서의 정보를 결합합니다.','비·야간·센서 고장에서도 결과가 유지되는지 확인하세요.'],
 ['라이다','lidar','레이저로 주변의 거리와 형태를 측정한 자료를 사용합니다.','센서의 수·가격·거리 조건과 인식 성능을 함께 확인하세요.'],
 ['경로·행동 계획','motion planning|path planning|trajectory planning|behavior planning','차량이 어디로 어떻게 움직일지 결정하는 문제입니다.','안전 제약과 실제 도로 평가 여부를 확인하세요.'],
 ['객체 인식','object detection|3d detection|object recognition','차량·보행자·장애물의 위치와 종류를 찾습니다.','거리별 오류와 놓친 객체, 평가 데이터 환경을 확인하세요.'],
 ['종단간 주행','end[- ]to[- ]end','센서 입력에서 주행 판단까지 여러 단계를 함께 학습합니다.','실제 주행 개입 횟수와 실패 원인 설명이 가능한지 확인하세요.'],
 ['시뮬레이션','simulation|simulator|sim[- ]to[- ]real','가상 환경으로 학습하거나 검증하고 실제 환경에 옮깁니다.','가상 환경 성능이 실제 도로에서도 검증되었는지 확인하세요.'],
 ['주행 안전','collision avoidance|safety|risk assessment','충돌 회피와 위험 판단을 다룹니다.','드문 위험 상황과 사람 개입을 포함한 평가 조건을 확인하세요.']],
 '바이오·의료 AI':[
 ['의료영상 분할','segmentation','영상에서 장기나 병변의 영역을 구분합니다.','외부 병원 데이터와 작은 병변에서 성능을 확인하세요.'],
 ['신약·분자 설계','drug discovery|molecular design|drug design','후보 약물이나 분자의 탐색·설계를 다룹니다.','계산 결과 뒤에 실험 검증이 있는지 확인하세요.'],
 ['단백질','protein(s)?','단백질의 구조·기능·상호작용과 관련한 연구입니다.','예측 성능과 실제 생물학적 검증을 구분해서 읽으세요.'],
 ['설명 가능성','explainab\\w*|interpretability|interpretable','모델의 판단 근거를 이해하는 방법을 다룹니다.','설명이 임상적으로 타당한지 별도로 검증했는지 확인하세요.'],
 ['외부 검증','external validation|multi[- ]center|multicenter','학습 환경과 다른 기관이나 데이터에서 검증합니다.','병원·장비·환자군별 성능 차이를 확인하세요.'],
 ['생성 모델','diffusion models?|generative models?|generative ai','새로운 영상·분자 등 데이터를 생성하는 모델입니다.','생성물의 품질뿐 아니라 실제 용도에서의 유효성을 확인하세요.'],
 ['프라이버시·연합학습','federated learning|privacy[- ]preserv\\w*|differential privacy','민감한 데이터를 직접 모으는 부담을 줄이는 학습 방식입니다.','데이터 유출 가정과 기관별 분포 차이를 확인하세요.']]
};
function conceptTrends(field,records){const periods=[...new Set(records.map(r=>r.period))].sort();if(periods.length!==2)return [];
 return (concepts[field]||[]).map(([label,pattern,meaning,question])=>{const rx=new RegExp('\\b(?:'+pattern+')\\b','i');const found=records.filter(r=>rx.test(r.title+' '+r.abstract));const counts=periods.map(p=>found.filter(r=>r.period===p).length),totals=periods.map(p=>records.filter(r=>r.period===p).length),rates=counts.map((n,i)=>totals[i]?n/totals[i]*100:0);return {label,pattern,meaning,question,periods,counts,totals,rates,change:rates[1]-rates[0],records:found};}).sort((a,b)=>Math.abs(b.change)-Math.abs(a.change));
}
const api={companyFacts,benchmark,median,conceptTrends,concepts};root.MotInsights=api;if(typeof module!=='undefined')module.exports=api;
})(typeof globalThis!=='undefined'?globalThis:this);
