const fs=require('node:fs');const path=require('node:path');
const root=path.resolve(__dirname,'..');
const out=path.join(root,'dist');
for(const file of ['index.html','app.js','styles.css','insights.js','insights-ui.js','workspace-ui.js'])fs.copyFileSync(path.join(root,'web',file),path.join(out,file));
const data=JSON.parse(fs.readFileSync(path.join(out,'data.json'),'utf8'));
const escape=text=>text.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
data.guide=fs.readFileSync(path.join(root,'reports','project_guide.md'),'utf8').split(/\r?\n/).filter(line=>line.trim()).map(line=>line.startsWith('## ')?'<h2>'+escape(line.slice(3))+'</h2>':line.startsWith('# ')?'<h1>'+escape(line.slice(2))+'</h1>':'<p>'+escape(line)+'</p>').join('');
fs.writeFileSync(path.join(out,'data.json'),JSON.stringify(data)+'\n');
console.log('Prepared Vercel app with '+data.companies.length+' actual companies and Python collection/upload API.');
