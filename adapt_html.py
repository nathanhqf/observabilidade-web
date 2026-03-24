"""
Transforms painel_observabilidade_callcenter.html into static/index.html
by replacing PBI markers with fetch() API calls.
"""
import re

SRC = r"C:\Users\natferreir\OneDrive - Brasilseg Companhia de Seguros\Documentos\Projetos\painel_observabilidade_callcenter.html"
DST = r"C:\Users\natferreir\OneDrive - Brasilseg Companhia de Seguros\Documentos\Projetos\observabilidade_web\static\index.html"

with open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Remove the PBI marker lines
html = html.replace("window._PBI_VOLUME    = [];", "")
html = html.replace("window._PBI_MOTIVOS   = [];", "")
html = html.replace("window._PBI_MUNICIPIOS = {};", "")

# 2. Replace the old init() function with an async version that fetches from API
old_init_start = "function init(){"
old_init_body_end = "startClock();"

# Find the init function
init_idx = html.index(old_init_start)
# Find where init body ends (after startClock(); and the event listener line)
startclock_idx = html.index("startClock();", init_idx)
# Find the end of the line containing startClock()
newline_after_startclock = html.index("\n", startclock_idx)

# The init function content from "function init(){" to end of startClock() line
old_init = html[init_idx:newline_after_startclock]

new_init = """function init(){
fetch('/api/volume').then(r=>r.json()).then(volumeData=>{
fetch('/api/motivos').then(r=>r.json()).then(motivos=>{
fetch('/api/municipios').then(r=>r.json()).then(muniData=>{
DATA = {};
volumeData.forEach(d => { DATA[d.ddd] = d; });
DDD_MAP = {};
volumeData.forEach(d => {
    DDD_MAP[d.ddd] = { micro: d.micro, uf: d.uf, regiao: d.regiao };
});
REGIAO_DDDS = {};
REGIOES.forEach(r => REGIAO_DDDS[r] = []);
Object.entries(DDD_MAP).forEach(([d, info]) => REGIAO_DDDS[info.regiao].push(parseInt(d)));
MUNI_BY_DDD = muniData || {};
const _clsColors = ['#ef5350','#ff9800','#ffd54f','#66bb6a','#4fc3f7','#ab47bc','#ec407a','#26a69a','#7e57c2','#78909c','#8d6e63','#d4e157'];
CLS = {};
motivos.forEach((m, i) => {
    CLS[m.classe] = { g: {}, w: m.qtd, c: _clsColors[i % _clsColors.length], tma: m.tma };
});
const totalMotivos = motivos.reduce((a, m) => a + m.qtd, 0);
Object.values(DATA).forEach(d => {
    d.motDist = {};
    d.motTma = {};
    motivos.forEach(m => {
        d.motDist[m.classe] = Math.round((m.qtd / Math.max(totalMotivos, 1)) * d.totalToday);
        d.motTma[m.classe] = m.tma;
    });
    if (!d.topMotivo && motivos.length > 0) d.topMotivo = motivos[0].classe;
});

filteredDDDs = Object.keys(DATA).map(Number);
popFilters(); renderKPIs(); renderMaps(); renderCharts();
renderTable(); renderHeatmap(); renderMotivos(); renderAlerts();
startClock();"""

html = html.replace(old_init, new_init)

# 3. Find the document.addEventListener('click' line that closes init and add closing braces for the 3 fetch blocks
# The line after startClock() has document.addEventListener('click'...)
click_line_start = "document.addEventListener('click',function(e)"
click_idx = html.index(click_line_start)
# Find the newline before it to insert closing braces
prev_newline = html.rindex("\n", 0, click_idx)

# Insert the closing of the 3 fetch().then() blocks before the click listener
close_fetches = """
document.getElementById('loading').classList.add('hidden');
}).catch(e=>{console.error('Erro municipios:',e);document.getElementById('loading').classList.add('hidden');});
}).catch(e=>{console.error('Erro motivos:',e);document.getElementById('loading').classList.add('hidden');});
}).catch(e=>{console.error('Erro volume:',e);document.getElementById('loading').classList.add('hidden');});
"""
html = html[:prev_newline] + close_fetches + html[prev_newline:]

# 4. Replace the DOMContentLoaded listener to also set up auto-refresh
old_dom = "document.addEventListener('DOMContentLoaded',init);"
new_dom = """document.addEventListener('DOMContentLoaded',function(){
init();
setInterval(function(){
fetch('/api/volume').then(r=>r.json()).then(volumeData=>{
fetch('/api/motivos').then(r=>r.json()).then(motivos=>{
fetch('/api/municipios').then(r=>r.json()).then(muniData=>{
DATA={};volumeData.forEach(d=>{DATA[d.ddd]=d;});
DDD_MAP={};volumeData.forEach(d=>{DDD_MAP[d.ddd]={micro:d.micro,uf:d.uf,regiao:d.regiao};});
REGIAO_DDDS={};REGIOES.forEach(r=>REGIAO_DDDS[r]=[]);Object.entries(DDD_MAP).forEach(([d,info])=>REGIAO_DDDS[info.regiao].push(parseInt(d)));
MUNI_BY_DDD=muniData||{};
const _clsColors=['#ef5350','#ff9800','#ffd54f','#66bb6a','#4fc3f7','#ab47bc','#ec407a','#26a69a','#7e57c2','#78909c','#8d6e63','#d4e157'];
CLS={};motivos.forEach((m,i)=>{CLS[m.classe]={g:{},w:m.qtd,c:_clsColors[i%_clsColors.length],tma:m.tma};});
const totalMotivos=motivos.reduce((a,m)=>a+m.qtd,0);
Object.values(DATA).forEach(d=>{d.motDist={};d.motTma={};motivos.forEach(m=>{d.motDist[m.classe]=Math.round((m.qtd/Math.max(totalMotivos,1))*d.totalToday);d.motTma[m.classe]=m.tma;});if(!d.topMotivo&&motivos.length>0)d.topMotivo=motivos[0].classe;});
filteredDDDs=Object.keys(DATA).map(Number);
renderKPIs();renderMaps();renderCharts();renderTable();renderHeatmap();renderMotivos();renderAlerts();
}).catch(e=>console.error('Refresh error:',e));}).catch(e=>console.error('Refresh error:',e));}).catch(e=>console.error('Refresh error:',e));
},300000);
});"""

html = html.replace(old_dom, new_dom)

# 5. Update the page title
html = html.replace(
    "<title>Painel de Observabilidade - Call Center Brasilseg</title>",
    "<title>Painel de Observabilidade - Call Center Brasilseg</title>"
)

with open(DST, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Done! Output: {DST}")
print(f"Size: {len(html):,} bytes")
