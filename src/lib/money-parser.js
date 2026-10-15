/* ---------- Saaz natural language search (client side v1; swap for the LLM endpoint later, same output shape) ---------- */
const COLOURS={blue:'blue',red:'red',black:'black',white:'white',pearl:'white',silver:'silver',grey:'grey',gray:'grey',wine:'wine',maroon:'wine',beige:'beige',gold:'beige',cream:'beige'};
const BODIES=[['suv','SUV'],['4x4','SUV'],['jeep','SUV'],['sedan','Sedan'],['saloon','Sedan'],['hatchback','Hatchback'],['hatch','Hatchback'],['small car','Hatchback'],['mini van','Mini Van'],['minivan','Mini Van'],['mpv','Mini Van'],['family car','Mini Van'],['van','Van'],['pickup','Pick up'],['pick up','Pick up'],['pick-up','Pick up'],['double cabin','Pick up'],['double cab','Pick up'],['truck','Truck'],['lorry','Truck'],['bus','Bus'],['wagon','Wagon'],['estate','Wagon'],['coupe','Coupe'],['convertible','Convertible']];
const NUMWORDS={one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,ten:10};
function parseMoney(t){
  const cur=$('cur').value; let out={};
  const toUSD=(n,unit,c)=>{let v=n*(unit==='m'?1e6:unit==='k'?1e3:1);let ccy=c||(v>=100000?'UGX':(cur==='USD'?'USD':cur));return {usd:v/FX[ccy],ccy,v}};
  const amt='(ugx|ush|shs?|kes|ksh|usd|\\$|dollars?)?\\s*([\\d][\\d,\\.]*)\\s*(m|million|mil|k|thousand)?\\s*(ugx|ush|shs?|shillings?|kes|ksh|usd|dollars?)?';
  const ccyOf=x=>!x?null:/usd|\$|dollar/.test(x)?'USD':/kes|ksh/.test(x)?'KES':'UGX';
  let m;
  let re=new RegExp('(between|from)\\s*'+amt+'\\s*(?:and|to|-)\\s*'+amt,'i');
  if((m=t.match(re))){const a=toUSD(parseFloat(m[3].replace(/,/g,'')),(m[4]||'')[0],ccyOf(m[2]||m[5]));const b=toUSD(parseFloat(m[7].replace(/,/g,'')),(m[8]||'')[0],ccyOf(m[6]||m[9]));out.min=a.usd;out.max=b.usd;out.label=`${m[3]}${m[4]||''} to ${m[7]}${m[8]||''} ${b.ccy}`;return out}
  re=new RegExp('(under|below|less than|max(?:imum)?|up to|not more than|budget(?: of| is)?|around|about|within|at most|cheaper than)\\s*'+amt,'i');
  if((m=t.match(re))){const a=toUSD(parseFloat(m[3].replace(/,/g,'')),(m[4]||'')[0],ccyOf(m[2]||m[5]));out.max=a.usd*(/around|about/.test(m[1])?1.1:1);out.label=`under ${m[3]}${m[4]||''} ${a.ccy}`;return out}
  re=new RegExp('(over|above|more than|at least|minimum)\\s*'+amt,'i');
  if((m=t.match(re))){const a=toUSD(parseFloat(m[3].replace(/,/g,'')),(m[4]||'')[0],ccyOf(m[2]||m[5]));if(a.v>1000){out.min=a.usd;out.label=`over ${m[3]}${m[4]||''} ${a.ccy}`;return out}}
  re=new RegExp('(?:\\$|usd\\s*)([\\d][\\d,]*)|([\\d][\\d,\\.]*)\\s*(m|million|mil)\\b','i');
  if((m=t.match(re))){if(m[1]){out.max=parseFloat(m[1].replace(/,/g,''));out.label='under $'+m[1]}else{const a=toUSD(parseFloat(m[2]),'m',null);out.max=a.usd;out.label=`under ${m[2]}m ${a.ccy}`}return out}
  return out;
}
function parseNL(q){
  const t=' '+q.toLowerCase().replace(/[’']/g,'').replace(/,(?!\d)/g,' ').replace(/[;!?]/g,' ').replace(/\.(?!\d)/g,' ')+' ';const f=EMPTY();const got=[];const miss=[];
  BODIES.forEach(([k,v])=>{if(t.includes(' '+k+' ')||t.includes(' '+k+'s ')){if(!f.bodies.includes(v))f.bodies.push(v)}});
  if(f.bodies.length)got.push(['bodies',f.bodies.join(' or ')]);
  DATA.makes.forEach(([mk])=>{const k=mk.toLowerCase().replace('-',' ');let hit=t.includes(' '+k+' ');if(mk==='MERCEDES-BENZ'&&/ mercedes | benz /.test(t))hit=true;if(mk==='VOLKSWAGEN'&&t.includes(' vw '))hit=true;if(mk==='LAND ROVER'&&/ landrover | range rover /.test(t))hit=true;if(hit&&!f.makes.includes(mk))f.makes.push(mk)});
  Object.entries(DATA.models).forEach(([mk,ms])=>ms.forEach(md=>{const k=md.toLowerCase();if(t.includes(' '+k+' ')){f.model=md;if(!f.makes.includes(mk))f.makes.push(mk)}}));
  if(f.makes.length)got.push(['makes',f.makes.map(x=>x[0]+x.slice(1).toLowerCase()).join(' or ')+(f.model?' '+f.model:'')]);
  Object.entries(COLOURS).forEach(([k,v])=>{if(t.includes(' '+k+' ')){if(!f.colours.includes(v))f.colours.push(v)}});
  if(f.colours.length)got.push(['colours',f.colours.join(' or ')]);
  const mo=parseMoney(t);if(mo.max){f.price=Math.round(mo.max)}if(mo.min){f.pmin=Math.round(mo.min)}if(mo.label)got.push(['price',mo.label]);
  if(/cheap|affordable|budget car|low cost/.test(t)&&!f.price){f.price=5000;got.push(['price','cheap (under $5,000)'])}
  let m;
  if((m=t.match(/(20\d\d)\s*(?:and|or)\s*(?:above|newer|later|up)|(?:from|after|newer than|since)\s*(20\d\d)|(20\d\d)\s*\+|(20\d\d)\s*(?:model|or newer)/))){f.year=m[1]||m[2]||m[3]||m[4];got.push(['year',f.year+' or newer'])}
  else if((m=t.match(/\b(20\d\d)\b/))){f.year=m[1];got.push(['year',m[1]+' or newer'])}
  if(/diesel/.test(t)){f.fuel='Diesel';got.push(['fuel','Diesel'])}else if(/hybrid/.test(t)){f.fuel='Hybrid';got.push(['fuel','Hybrid'])}else if(/petrol|gasoline/.test(t)){f.fuel='Petrol';got.push(['fuel','Petrol'])}
  if(/4wd|4x4|awd|four wheel|all wheel/.test(t)){f.drive='4WD';got.push(['drive','4WD'])}
  if(/manual|stick/.test(t)){f.trans='MT';got.push(['trans','Manual'])}else if(/automatic| auto /.test(t)){f.trans='AT';got.push(['trans','Automatic'])}
  if((m=t.match(/(\d+|seven|eight|five|six)\s*[- ]?seat/))){f.seats=NUMWORDS[m[1]]||+m[1];got.push(['seats',f.seats+'+ seats'])}
  else if(/family/.test(t)){f.seats=7;got.push(['seats','7+ seats (family)'])}
  if(/left hand|lhd/.test(t)){f.steer='LHD';got.push(['steer','Left hand drive'])}
  if(/low mileage|low km|few km|not driven much/.test(t)){f.kmmax=80000;got.push(['kmmax','under 80,000 km'])}
  else if((m=t.match(/(?:under|below|less than|max)\s*([\d,\.]+)\s*(k|thousand)?\s*(?:km|kilomet|miles)/))){f.kmmax=parseFloat(m[1].replace(/,/g,''))*(m[2]?1000:1);got.push(['kmmax','under '+f.kmmax.toLocaleString()+' km'])}
  if(/service record|service history|full history|maintenance record|full records|serviced|logbook/.test(t)){f.records=true;got.push(['records','Full service records'])}
  if(/discount|offer|sale|deal/.test(t)){f.disc=1;got.push(['disc','On discount'])}
  if(/accident|crash/.test(t))miss.push('accident history (coming with Saaz Check)');
  if(/sunroof|leather|camera|navigation|alloy/.test(t))miss.push('features like sunroof or leather (not yet in listing data)');
  if(/ new /.test(t)&&!/newer/.test(t))miss.push('brand new cars (we list used stock)');
  return {f,got,miss};
}
const LBL={bodies:'Body',makes:'Make',colours:'Colour',price:'Price',year:'Year',fuel:'Fuel',drive:'Drive',trans:'Gearbox',seats:'Seats',steer:'Steering',kmmax:'Mileage',records:'Records',disc:'Deals'};
function askSaaz(e){if(e)e.preventDefault();const q=$('askq').value.trim();if(!q)return toast('Type what you want');
  const {f,got,miss}=parseNL(q);F=f;F.kw='';
  const u=$('understood');
  if(!got.length){u.innerHTML='<b>Saaz could not read that yet.</b> Try a body type, budget, colour, make or year. Showing a keyword match instead.';F=EMPTY();F.kw=q}
  else{u.innerHTML='<b>Saaz understood:</b>'+got.map(([k,v])=>`<span class="chip">${LBL[k]}: ${v}<i title="Remove" onclick="dropChip('${k}')">×</i></span>`).join('')+miss.map(x=>`<span class="chip miss">Not yet: ${x}</span>`).join('')}
  u.style.display='flex';render();$('cards').scrollIntoView({behavior:'smooth',block:'start'});return false}
function dropChip(k){const m={bodies:()=>F.bodies=[],makes:()=>{F.makes=[];F.model=''},colours:()=>F.colours=[],price:()=>{F.price='';F.pmin=''},year:()=>F.year='',fuel:()=>F.fuel='',drive:()=>F.drive='',trans:()=>F.trans='',seats:()=>F.seats='',steer:()=>F.steer='',kmmax:()=>F.kmmax='',records:()=>F.records=false,disc:()=>F.disc=0};m[k]&&m[k]();
  const u=$('understood');[...u.querySelectorAll('.chip')].forEach(c=>{if(c.innerHTML.includes(`dropChip('${k}')`))c.remove()});render()}
function askEx(a){$('askq').value=a.textContent;askSaaz()}
