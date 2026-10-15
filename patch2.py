import json,random
random.seed(9)
D=json.load(open('data.json'))
for c in D['cars']:
  c.setdefault('records',random.random()<0.55)
  c.setdefault('grade',random.choice(['4','4','4.5','3.5','5','R']))
json.dump(D,open('data.json','w'))
s=open('build.py').read()
if 'askSaaz' in s: raise SystemExit('already patched')
s=s.replace("/* check teaser */","""/* ask saaz */
.ask{background:#fff;border-radius:10px;padding:14px;margin-bottom:12px;box-shadow:0 8px 24px rgba(0,0,0,.18)}
.ask .row{display:flex;gap:8px}
.ask input{flex:1;border:2px solid var(--navy);border-radius:8px;padding:12px 14px;font-size:15px;outline:none}
.ask input:focus{border-color:var(--orange)}
.ask button{background:var(--navy);color:#fff;border:0;border-radius:8px;padding:0 20px;font-weight:800;cursor:pointer;white-space:nowrap}
.ask .ex{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.ask .ex a{font-size:12px;color:var(--navy);background:var(--bg);border:1px solid var(--line);padding:4px 10px;border-radius:14px;cursor:pointer}
.ask .ex a:hover{border-color:var(--orange);color:var(--orange2)}
.ask .ai{font-size:11px;color:var(--mut);margin-top:6px}
.understood{display:none;background:#F0F7FF;border:1px solid #BFD8F5;border-radius:8px;padding:8px 12px;margin-top:10px;font-size:13px;color:var(--navy);align-items:center;gap:8px;flex-wrap:wrap}
.understood b{margin-right:4px}
.understood .chip{background:#fff;border:1px solid #BFD8F5;border-radius:14px;padding:3px 8px 3px 10px;display:inline-flex;gap:6px;align-items:center}
.understood .chip i{font-style:normal;cursor:pointer;color:var(--mut);font-weight:700}
.understood .chip i:hover{color:var(--red)}
.understood .miss{color:#8A5A00;background:#FFF4E5;border-color:#F5D7B0}
.refine{color:#D6E4F5;font-size:12px;margin:10px 0 6px;cursor:pointer}
.card .rec{position:absolute;left:8px;bottom:8px;background:var(--green);color:#fff;font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700}
/* check teaser */""")
s=s.replace("""    <h1>Find your next car from Japan</h1>
    <p>Inspected stock, clear FOB and CIF Mombasa pricing, pay by mobile money or card.</p>
    <div class="tabs">""","""    <h1>Tell Saaz what you want</h1>
    <p>Describe the car in your own words. Saaz reads it and finds the match.</p>
    <div class="ask">
      <form class="row" onsubmit="return askSaaz(event)"><input id="askq" placeholder="I want an SUV below 40m, blue or red, with full service records" autocomplete="off"><button>Ask Saaz</button></form>
      <div class="ex">
        <a onclick="askEx(this)">I want an SUV below 40m especially blue or red, with full service records</a>
        <a onclick="askEx(this)">Toyota 7 seater, diesel, 4WD, 2015 or newer, under $12,000</a>
        <a onclick="askEx(this)">cheap hatchback for a first car, low mileage, automatic</a>
        <a onclick="askEx(this)">Mercedes or BMW sedan, black, below 60 million shillings</a>
      </div>
      <div class="understood" id="understood"></div>
      <div class="ai">Saaz AI search. Prices in UGX are converted at today's rate. Service records come from the Saaz ledger and seller inspection sheets.</div>
    </div>
    <div class="refine" onclick="toggleRefine()">&#9656; Refine with filters</div>
    <div id="refineBox" style="display:none">
    <div class="tabs">""")
s=s.replace("""    <div class="quick"><a onclick="quick('price',3000)">""","""    </div>
    <div class="quick"><a onclick="quick('price',3000)">""")
s=s.replace("""<span class="fav" onclick="toast('Saved to favourites')">♥</span></div>""","""${x.records?'<span class="rec">&#10004; Service records</span>':''}<span class="fav" onclick="toast('Saved to favourites')">♥</span></div>""")
s=s.replace("""<div class="ref">Ref No. ${x.ref} · ${x.body} · ${x.colour}</div>""","""<div class="ref">Ref No. ${x.ref} · ${x.body} · ${x.colour} · Grade ${x.grade}</div>""")
s=s.replace("let F={make:'',model:'',year:'',price:'',body:'',kw:'',misc:'',disc:0};","const EMPTY=()=>({make:'',makes:[],model:'',year:'',price:'',pmin:'',body:'',bodies:[],kw:'',misc:'',disc:0,colours:[],records:false,kmmax:'',fuel:'',drive:'',trans:'',seats:'',steer:''});\nlet F=EMPTY();")
s=s.replace("let list=DATA.cars.filter(x=>(!F.make||x.make===F.make)&&(!F.model||x.model===F.model)&&(!F.year||x.year>=+F.year)&&(!F.price||x.price<=+F.price)&&(!F.body||x.body===F.body)&&(!F.disc||x.disc>0)",
"let list=DATA.cars.filter(x=>(!F.make||x.make===F.make)&&(!(F.makes||[]).length||F.makes.includes(x.make))&&(!F.model||x.model===F.model)&&(!F.year||x.year>=+F.year)&&(!F.price||x.price<=+F.price)&&(!F.pmin||x.price>=+F.pmin)&&(!F.body||x.body===F.body)&&(!(F.bodies||[]).length||F.bodies.includes(x.body))&&(!F.disc||x.disc>0)&&(!(F.colours||[]).length||F.colours.some(c=>x.colour.toLowerCase().includes(c)))&&(!F.records||x.records)&&(!F.kmmax||x.km<=+F.kmmax)&&(!F.fuel||x.fuel===F.fuel)&&(!F.drive||x.drive===F.drive)&&(!F.trans||x.trans===F.trans)&&(!F.seats||x.seats>=+F.seats)&&(!F.steer||x.steer===F.steer)")
s=s.replace("$('resHd').textContent=(Object.values(F).some(v=>v)?list.length+' cars found':'Featured cars');","$('resHd').textContent=(Object.values(F).some(v=>Array.isArray(v)?v.length:v)?list.length+' cars found':'Featured cars');")
s=s.replace("if(e.target.classList.contains('hsearch')){F={make:'',model:'',year:'',price:'',body:'',kw:$('hq').value,misc:'',disc:0}}else{F={make:$('fMake').value,model:$('fModel').value,year:$('fYear').value,price:$('fPrice').value,body:$('fBody').value,kw:$('fKw').value,misc:'',disc:0}}render();",
"if(e.target.classList.contains('hsearch')){$('askq').value=$('hq').value;return askSaaz(e)}else{F=EMPTY();Object.assign(F,{make:$('fMake').value,model:$('fModel').value,year:$('fYear').value,price:$('fPrice').value,body:$('fBody').value,kw:$('fKw').value})}hideUnderstood();render();")
s=s.replace("function quick(k,v){F={make:'',model:'',year:'',price:'',body:'',kw:'',misc:'',disc:0};F[k]=v;render();","function quick(k,v){F=EMPTY();F[k]=v;hideUnderstood();render();")
s=s.replace("function resetAll(){F={make:'',model:'',year:'',price:'',body:'',kw:'',misc:'',disc:0};['fMake','fModel','fYear','fPrice','fBody','fKw','hq'].forEach(i=>$(i).value='');render();return false}",
"function resetAll(){F=EMPTY();['fMake','fModel','fYear','fPrice','fBody','fKw','hq','askq'].forEach(i=>$(i).value='');hideUnderstood();render();return false}\nfunction toggleRefine(){const b=$('refineBox');b.style.display=b.style.display==='none'?'block':'none'}\nfunction hideUnderstood(){$('understood').style.display='none'}")
s=s.replace("(function init(){","__NLJS__\n(function init(){")
s=s.replace("open('index.html','w').write(html.replace('__DATA__',json.dumps(D)))","open('index.html','w').write(html.replace('__DATA__',json.dumps(D)).replace('__NLJS__',open('nl.js').read()))")
open('build.py','w').write(s)
print('patched')
