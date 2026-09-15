const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const M=require('../web/insights.js');const data=JSON.parse(fs.readFileSync('dist/data.json','utf8'));
test('actual loss-to-profit and profit-to-loss transitions retain signs',()=>{
 const h=M.companyFacts(data,'SK하이닉스');assert.equal(h.history[0].profit,-7730313000000);assert.ok(Math.abs(h.growth-46.7628475)<.001);assert.ok(Math.abs(h.latest.margin-48.5928)<.01);
 assert.equal(M.companyFacts(data,'선바이오').profitChange,'흑자 전환');assert.equal(M.companyFacts(data,'카카오게임즈').profitChange,'적자 전환');
});
test('benchmark excludes self, other industries, other accounting bases and qualified audit',()=>{
 const b=M.benchmark(data,'네오오토');assert.ok(b.peers.every(p=>p.company.sector===b.own.company.sector&&p.latest.basis===b.own.latest.basis));assert.ok(!b.peers.some(p=>p.company.company==='네오오토'));assert.ok(b.excluded.some(p=>p.company==='코다코'));
 const h=M.benchmark(data,'SK하이닉스');assert.ok(h.peers.every(p=>p.company.sector==='반도체'));assert.ok(h.excluded.some(p=>p.company==='넥스트칩'));
});
test('missing and zero prior revenue do not become zero growth',()=>{
 const d=structuredClone(data);d.financials=d.financials.filter(r=>!(r.company==='DB하이텍'&&r.year==='2024'));assert.equal(M.companyFacts(d,'DB하이텍').growth,null);
 const z=structuredClone(data);z.financials.find(r=>r.company==='DB하이텍'&&r.year==='2024'&&r.metric==='매출액').value_krw='0';assert.equal(M.companyFacts(z,'DB하이텍').growth,null);assert.equal(M.median([null,undefined]),null);
});
test('concept prevalence counts documents once and uses each actual denominator',()=>{
 const rows=[{title:'Inference inference',abstract:'quantization',period:'기간 A'},{title:'No term',abstract:'nothing',period:'기간 A'},{title:'Inference',abstract:'inference',period:'기간 B'}];
 const t=M.conceptTrends('반도체·AI 하드웨어',rows).find(t=>t.label==='추론 실행');assert.deepEqual(t.counts,[1,1]);assert.deepEqual(t.totals,[2,1]);assert.equal(t.change,50);
 const q=M.conceptTrends('반도체·AI 하드웨어',rows).find(t=>t.label==='양자화·저정밀 연산');assert.equal(q.counts[0],1);
});
test('all technology fields show original evidence and actual counts',()=>{
 for(const [name,field] of Object.entries(data.papers)){const trends=M.conceptTrends(name,field.records);assert.ok(trends.length>=6);assert.ok(trends.some(t=>t.records.length>0));for(const t of trends){assert.deepEqual(t.totals,[60,60]);assert.equal(t.records.length,t.counts[0]+t.counts[1]);assert.ok(t.records.every(r=>r.source_url.startsWith('https://arxiv.org/abs/')));}}
});
