import json
D=json.load(open('data.json'))
html=r'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Saaz Motors: Japanese Used Cars for Uganda and East Africa</title>
<style>
:root{--navy:#0B2545;--navy2:#13315C;--orange:#F26B1D;--orange2:#D9570F;--bg:#F3F5F8;--line:#DDE3EA;--txt:#1B2430;--mut:#6B7785;--green:#1F9D55;--red:#D7263D}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:var(--txt);background:var(--bg);font-size:14px;line-height:1.45}
a{color:inherit;text-decoration:none}
button,select,input{font:inherit}
.wrap{max-width:1240px;margin:0 auto;padding:0 16px}
/* top bar */
.topbar{background:var(--navy);color:#CFD8E3;font-size:12px}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:34px;gap:16px;flex-wrap:wrap}
.topbar b{color:#fff}
.topbar .sel{display:flex;gap:14px;align-items:center}
.topbar select{background:transparent;color:#fff;border:0;border-bottom:1px solid #456;padding:2px 0;cursor:pointer}
.topbar select option{color:#000}
/* header */
header{background:#fff;border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;gap:22px;height:72px}
.logo{display:flex;align-items:center;gap:10px;font-weight:800;font-size:24px;letter-spacing:.5px;color:var(--navy)}
.logo .mark{width:40px;height:40px;border-radius:10px;background:linear-gradient(135deg,var(--orange),var(--orange2));display:grid;place-items:center;color:#fff;font-size:20px}
.logo small{display:block;font-size:10px;font-weight:600;color:var(--mut);letter-spacing:2px}
.hsearch{flex:1;display:flex;max-width:560px;border:2px solid var(--navy);border-radius:8px;overflow:hidden}
.hsearch select{border:0;border-right:1px solid var(--line);padding:0 10px;background:#F7F9FB;color:var(--navy);font-weight:600}
.hsearch input{flex:1;border:0;padding:10px 12px;outline:none}
.hsearch button{border:0;background:var(--navy);color:#fff;padding:0 18px;font-weight:700;cursor:pointer}
.hright{margin-left:auto;display:flex;gap:18px;align-items:center;font-size:13px}
.hright .acct{display:flex;flex-direction:column;line-height:1.2}
.hright .acct span{color:var(--mut);font-size:11px}
.btn{display:inline-block;background:var(--orange);color:#fff;font-weight:700;padding:9px 16px;border-radius:7px;border:0;cursor:pointer}
.btn:hover{background:var(--orange2)}
.btn.ghost{background:#fff;color:var(--navy);border:2px solid var(--navy)}
.btn.navy{background:var(--navy)}
/* nav */
nav{background:#fff;border-bottom:3px solid var(--orange)}
nav ul{list-style:none;display:flex;gap:4px}
nav li{padding:12px 16px;font-weight:700;color:var(--navy);cursor:pointer;position:relative;white-space:nowrap}
nav li:hover{background:var(--bg)}
nav li.check{margin-left:auto;color:var(--orange)}
nav li .tag{background:var(--red);color:#fff;font-size:10px;padding:1px 6px;border-radius:10px;margin-left:6px;vertical-align:middle}
/* notice */
.notice{background:#FFF4E5;border-bottom:1px solid #F5D7B0;font-size:12px;color:#7A4A05}
.notice .wrap{display:flex;gap:18px;height:32px;align-items:center;overflow:hidden;white-space:nowrap}
/* layout */
.main{display:grid;grid-template-columns:250px 1fr;gap:20px;padding:20px 0}
aside .box{background:#fff;border:1px solid var(--line);border-radius:8px;margin-bottom:14px;overflow:hidden}
aside h3{background:var(--navy);color:#fff;font-size:13px;padding:9px 12px;letter-spacing:.3px}
aside ul{list-style:none;max-height:380px;overflow:auto}
aside li{display:flex;justify-content:space-between;padding:6px 12px;border-top:1px solid #F0F2F5;font-size:13px;cursor:pointer}
aside li:hover{background:#FFF7F0;color:var(--orange2)}
aside li span{color:var(--mut);font-size:12px}
.banner{background:linear-gradient(135deg,var(--navy),var(--navy2));color:#fff;border-radius:8px;padding:16px;margin-bottom:14px}
.banner b{font-size:18px;display:block;color:#FFD166}
/* hero */
.hero{background:linear-gradient(120deg,#0B2545 0%,#1C4A8A 60%,#2B6CB0 100%);border-radius:12px;color:#fff;padding:26px 26px 22px;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;right:-60px;top:-60px;width:300px;height:300px;border-radius:50%;background:rgba(255,255,255,.06)}
.hero h1{font-size:26px;margin-bottom:4px}
.hero p{color:#D6E4F5;margin-bottom:16px}
.tabs{display:flex;gap:6px;margin-bottom:12px}
.tabs button{background:rgba(255,255,255,.15);color:#fff;border:0;padding:8px 14px;border-radius:6px 6px 0 0;font-weight:700;cursor:pointer}
.tabs button.on{background:#fff;color:var(--navy)}
.sgrid{background:#fff;border-radius:0 8px 8px 8px;padding:14px;display:grid;grid-template-columns:repeat(6,1fr) auto;gap:10px;align-items:end}
.sgrid label{display:block;font-size:11px;color:var(--mut);font-weight:700;margin-bottom:4px;text-transform:uppercase;letter-spacing:.4px}
.sgrid select,.sgrid input{width:100%;border:1px solid var(--line);border-radius:6px;padding:9px 10px;background:#fff;color:var(--txt)}
.sgrid .go{background:var(--orange);color:#fff;border:0;border-radius:6px;padding:10px 22px;font-weight:800;cursor:pointer;white-space:nowrap}
.quick{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.quick a{background:rgba(255,255,255,.15);padding:5px 11px;border-radius:20px;font-size:12px}
.quick a:hover{background:#fff;color:var(--navy)}
/* ask saaz */
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
/* check teaser */
.check{margin-top:16px;background:#fff;border:1px solid var(--line);border-left:5px solid var(--orange);border-radius:8px;padding:14px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.check h4{font-size:15px;color:var(--navy)}
.check p{color:var(--mut);font-size:13px}
.check form{display:flex;gap:8px;margin-left:auto}
.check input{border:1px solid var(--line);border-radius:6px;padding:9px 12px;width:220px}
/* sections */
.sec{margin-top:22px}
.sec .hd{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:10px}
.sec h2{font-size:18px;color:var(--navy)}
.sec .hd a{color:var(--orange2);font-weight:700;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
.tile{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 8px;text-align:center;cursor:pointer;font-weight:700;font-size:13px;color:var(--navy)}
.tile:hover{border-color:var(--orange);box-shadow:0 2px 10px rgba(0,0,0,.06)}
.tile .ico{font-size:26px;display:block;margin-bottom:4px}
.tile span{display:block;color:var(--mut);font-weight:500;font-size:11px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;overflow:hidden;position:relative;transition:.15s}
.card:hover{box-shadow:0 6px 18px rgba(11,37,69,.12);transform:translateY(-2px)}
.card .img{aspect-ratio:4/3;background:#E9EEF4;display:grid;place-items:center;position:relative}
.card .img svg{width:80%;height:auto}
.card .img .loc{position:absolute;left:8px;top:8px;background:rgba(11,37,69,.85);color:#fff;font-size:10px;padding:2px 7px;border-radius:4px;font-weight:700}
.card .img .off{position:absolute;right:8px;top:8px;background:var(--red);color:#fff;font-size:11px;padding:2px 7px;border-radius:4px;font-weight:800}
.card .fav{position:absolute;right:8px;bottom:8px;background:#fff;border-radius:50%;width:28px;height:28px;display:grid;place-items:center;cursor:pointer;color:#B0B8C4}
.card .fav:hover{color:var(--red)}
.card .body{padding:10px 12px 12px}
.card .ttl{font-weight:800;color:var(--navy);font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .ref{color:var(--mut);font-size:11px;margin-bottom:6px}
.card .specs{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:12px;color:#3B4654;margin-bottom:8px}
.card .specs b{color:var(--mut);font-weight:600}
.card .price{display:flex;align-items:baseline;gap:8px}
.card .price strong{font-size:18px;color:var(--orange2)}
.card .price s{color:var(--mut);font-size:12px}
.card .price small{color:var(--mut);font-size:11px;margin-left:auto}
.card .cta{display:flex;gap:6px;margin-top:8px}
.card .cta a{flex:1;text-align:center;padding:7px 0;border-radius:6px;font-size:12px;font-weight:700;border:1px solid var(--navy);color:var(--navy)}
.card .cta a.p{background:var(--navy);color:#fff}
/* trust */
.trust{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.trust .t{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px;display:flex;gap:12px}
.trust .t .i{width:42px;height:42px;border-radius:10px;background:#FFF1E6;color:var(--orange2);display:grid;place-items:center;font-size:20px;flex:none}
.trust .t b{display:block;color:var(--navy);margin-bottom:2px}
.trust .t p{color:var(--mut);font-size:12px}
.stats{display:flex;gap:20px;background:var(--navy);color:#fff;border-radius:10px;padding:18px 24px;justify-content:space-around;text-align:center;flex-wrap:wrap}
.stats b{display:block;font-size:26px;color:#FFD166}
.stats span{font-size:12px;color:#CFD8E3}
.pay{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.pay span{border:1px solid var(--line);background:#fff;border-radius:6px;padding:6px 12px;font-weight:700;font-size:12px}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.steps .s{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px;position:relative}
.steps .s .n{width:30px;height:30px;border-radius:50%;background:var(--orange);color:#fff;display:grid;place-items:center;font-weight:800;margin-bottom:8px}
.steps .s b{display:block;color:var(--navy)}
.steps .s p{color:var(--mut);font-size:12px;margin-top:2px}
/* footer */
footer{background:var(--navy);color:#B9C6D6;margin-top:30px;padding:30px 0 16px;font-size:13px}
footer .cols{display:grid;grid-template-columns:2fr 1fr 1fr 1fr 1fr;gap:20px}
footer h5{color:#fff;font-size:13px;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px}
footer li{list-style:none;margin:5px 0}
footer li:hover{color:#fff}
footer .bot{border-top:1px solid #234;margin-top:22px;padding-top:12px;display:flex;justify-content:space-between;font-size:12px;flex-wrap:wrap;gap:8px}
.wa{position:fixed;right:18px;bottom:18px;background:#25D366;color:#fff;border-radius:30px;padding:10px 16px;font-weight:700;box-shadow:0 6px 16px rgba(0,0,0,.2);display:flex;gap:8px;align-items:center;z-index:9}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--navy);color:#fff;padding:10px 16px;border-radius:8px;display:none;z-index:10}
@media(max-width:1000px){.main{grid-template-columns:1fr}aside{order:2}.sgrid{grid-template-columns:repeat(3,1fr)}.sgrid .go{grid-column:1/-1}.cards{grid-template-columns:repeat(2,1fr)}.tiles{grid-template-columns:repeat(3,1fr)}.trust,.steps{grid-template-columns:repeat(2,1fr)}footer .cols{grid-template-columns:1fr 1fr}.hsearch{display:none}nav li.check{margin-left:0}}
@media(max-width:760px){.topbar .sel{display:none}.topbar .wrap{height:auto;padding:6px 16px}header .wrap{height:auto;padding:10px 16px;gap:12px;flex-wrap:wrap}.logo{font-size:18px}.logo .mark{width:34px;height:34px;font-size:16px}.hright{margin-left:auto;gap:12px}.hright .acct{display:none}nav ul{overflow:auto}nav li{padding:12px 12px}.hero{padding:18px}.hero h1{font-size:22px}}
@media(max-width:600px){.cards{grid-template-columns:1fr}.sgrid{grid-template-columns:1fr 1fr}.check form{margin-left:0;width:100%}.check input{flex:1;width:auto}}
</style></head><body>

<div class="topbar"><div class="wrap">
  <div>Total Cars In Stock: <b id="stockTotal">0</b> &nbsp;|&nbsp; Cars Added Today: <b>1,286</b> &nbsp;|&nbsp; Japan Time: <b id="jtime"></b></div>
  <div class="sel">
    <label>Language: <select><option>English</option><option>Kiswahili</option><option>Luganda</option><option>Français</option></select></label>
    <label>Currency: <select id="cur"><option value="USD">USD</option><option value="UGX">UGX</option><option value="KES">KES</option><option value="JPY">JPY</option></select></label>
    <label>Country: <select><option>Uganda</option><option>Kenya</option><option>Tanzania</option><option>Rwanda</option><option>South Sudan</option><option>DR Congo</option></select></label>
  </div>
</div></div>

<header><div class="wrap">
  <a class="logo" href="#"><span class="mark">S</span><span>SAAZ MOTORS<small>JAPANESE USED CARS</small></span></a>
  <form class="hsearch" onsubmit="return doSearch(event)"><select id="hmode"><option>By Keyword</option><option>By Ref No.</option></select><input id="hq" placeholder="e.g. Toyota Harrier 2015, or SZ123456"><button>Search</button></form>
  <div class="hright">
    <div class="acct"><span>Hello, Guest</span><a href="#" onclick="toast('Login coming soon')"><b>Login</b> / Register</a></div>
    <a href="#" onclick="toast('Favourites saved on this device')">♡ Favorites</a>
    <a class="btn" href="#check">Saaz Check</a>
  </div>
</div></header>

<nav><div class="wrap"><ul>
  <li>Used Cars</li><li>Trucks &amp; Buses</li><li>Auto Parts</li><li>How to Buy</li><li>Shipping &amp; Clearing</li><li>Reviews</li><li>Help</li>
  <li class="check">Saaz Check <span class="tag">NEW</span></li>
</ul></div></nav>

<div class="notice"><div class="wrap"><span>⚠ NOTICE: Beware of fake Saaz Motors agents. We never ask for payment to a personal mobile money number.</span><span>Sales inquiries: WhatsApp +256 700 000 000</span></div></div>

<div class="wrap main">
<aside>
  <div class="banner"><b>Happy October Sale</b>Up to 25% off selected Japan stock. Ends 31 Oct.</div>
  <div class="box"><h3>Shop By Make</h3><ul id="makeList"></ul></div>
  <div class="box"><h3>Shop By Price</h3><ul id="priceList"></ul></div>
  <div class="box"><h3>Shop By Type</h3><ul id="typeList"></ul></div>
  <div class="box"><h3>Other Categories</h3><ul>
    <li onclick="filterMisc('LHD')">Left Hand Drive<span>1,568</span></li><li onclick="filterMisc('Hybrid')">Hybrid<span>1,778</span></li><li onclick="filterMisc('Diesel')">Diesel<span>2,261</span></li><li onclick="filterMisc('MT')">Manual<span>1,411</span></li><li onclick="filterMisc('4WD')">4WD<span>2,109</span></li></ul></div>
  <div class="box"><h3>Vehicles In Stock</h3><ul><li>Japan<span>32,399</span></li><li>Korea<span>15,157</span></li><li>UAE<span>4,002</span></li><li>United Kingdom<span>6,502</span></li><li>Thailand<span>818</span></li></ul></div>
</aside>

<section>
  <div class="hero">
    <h1>Tell Saaz what you want</h1>
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
    <div class="tabs"><button class="on" onclick="tab(this,'cars')">Cars</button><button onclick="tab(this,'trucks')">Trucks &amp; Buses</button><button onclick="tab(this,'parts')">Auto Parts</button></div>
    <form class="sgrid" onsubmit="return doSearch(event)">
      <div><label>Make</label><select id="fMake" onchange="fillModels()"><option value="">Any</option></select></div>
      <div><label>Model</label><select id="fModel"><option value="">Any</option></select></div>
      <div><label>Year from</label><select id="fYear"><option value="">Any</option></select></div>
      <div><label>Price to</label><select id="fPrice"><option value="">Any</option><option value="3000">$3,000</option><option value="5000">$5,000</option><option value="8000">$8,000</option><option value="12000">$12,000</option><option value="20000">$20,000</option><option value="999999">Over $20,000</option></select></div>
      <div><label>Body type</label><select id="fBody"><option value="">Any</option></select></div>
      <div><label>Keyword</label><input id="fKw" placeholder="e.g. 4WD, 7 seater"></div>
      <button class="go">SEARCH CARS</button>
    </form>
    </div>
    <div class="quick"><a onclick="quick('price',3000)">Under $3,000</a><a onclick="quick('price',5000)">Under $5,000</a><a onclick="quick('body','SUV')">SUV</a><a onclick="quick('make','TOYOTA')">Toyota</a><a onclick="quick('misc','Hybrid')">Hybrid</a><a onclick="quick('misc','4WD')">4WD</a><a onclick="quick('misc','7seat')">7 Seater</a><a onclick="quick('disc',1)">Discounted</a></div>
  </div>

  <div class="check" id="check">
    <div><h4>Saaz Check: verify any car in Uganda before you pay</h4><p>Enter a number plate or VIN. Make, model and year are free. Tax clearance, registration status and history are a paid check.</p></div>
    <form onsubmit="return checkDemo(event)"><input id="plate" placeholder="UBK 123A or VIN"><button class="btn navy">Check</button></form>
  </div>

  <div class="sec"><div class="hd"><h2>Shop by body type</h2><a href="#" onclick="return resetAll()">View all stock</a></div><div class="tiles" id="typeTiles"></div></div>

  <div class="sec"><div class="hd"><h2 id="resHd">Featured cars</h2><a href="#" onclick="return resetAll()">Clear filters</a></div><div class="cards" id="cards"></div></div>

  <div class="sec"><div class="hd"><h2>How to buy</h2></div><div class="steps">
    <div class="s"><div class="n">1</div><b>Find your car</b><p>Search by make, price or body type. Every car has 20+ photos and an inspection sheet.</p></div>
    <div class="s"><div class="n">2</div><b>Reserve and get an invoice</b><p>Price shown is FOB. Get a CIF Mombasa or Dar quote with shipping included.</p></div>
    <div class="s"><div class="n">3</div><b>Pay</b><p>MTN MoMo, Airtel Money, Visa or Mastercard, or bank transfer. Proof of payment uploads to your account.</p></div>
    <div class="s"><div class="n">4</div><b>Ship and clear</b><p>Track your vessel. Our clearing partners in Mombasa and Kampala handle URA tax and registration.</p></div>
  </div></div>

  <div class="sec"><div class="hd"><h2>Why Saaz Motors</h2></div><div class="trust">
    <div class="t"><div class="i">✔</div><div><b>Inspected before listing</b><p>Independent inspection sheet with every car. No surprises at the port.</p></div></div>
    <div class="t"><div class="i">₵</div><div><b>Pay the way you already do</b><p>Mobile money prompt to your phone, or card. No wire transfer fees for small payments.</p></div></div>
    <div class="t"><div class="i">⚓</div><div><b>Door to Kampala</b><p>Sea freight, port clearing, URA taxes and number plates handled by one team.</p></div></div>
    <div class="t"><div class="i">☎</div><div><b>A person who answers</b><p>WhatsApp support in English and Luganda, 8am to 8pm EAT, seven days.</p></div></div>
  </div></div>

  <div class="sec stats"><div><b>58,000+</b><span>cars in stock</span></div><div><b>12</b><span>countries served</span></div><div><b>4.8 / 5</b><span>customer rating</span></div><div><b>80%</b><span>repeat buyers</span></div></div>

  <div class="sec"><div class="hd"><h2>Accepted payments</h2></div><div class="pay"><span>MTN MoMo</span><span>Airtel Money</span><span>M-PESA</span><span>VISA</span><span>Mastercard</span><span>Bank transfer (USD)</span></div></div>
</section>
</div>

<footer><div class="wrap">
  <div class="cols">
    <div><div class="logo" style="color:#fff"><span class="mark">S</span><span>SAAZ MOTORS<small style="color:#B9C6D6">JAPANESE USED CARS</small></span></div><p style="margin-top:10px;max-width:320px">Japanese and Korean used cars exported to Uganda and East Africa, with inspection, shipping and clearing in one place.</p></div>
    <div><h5>Buy</h5><ul><li>Used Cars</li><li>Trucks &amp; Buses</li><li>Auto Parts</li><li>Today's Deals</li><li>Brand New Cars</li></ul></div>
    <div><h5>Help</h5><ul><li>How to Buy</li><li>How to Pay</li><li>Shipping Schedule</li><li>Clearing &amp; Taxes (URA)</li><li>FAQs</li></ul></div>
    <div><h5>Saaz Check</h5><ul><li>Check a number plate</li><li>Check a VIN</li><li>Pricing</li><li>For dealers (API)</li></ul></div>
    <div><h5>Company</h5><ul><li>About Us</li><li>Reviews</li><li>Agents in Uganda</li><li>Contact Us</li><li>Careers</li></ul></div>
  </div>
  <div class="bot"><span>© 2026 Saaz Technologies Ltd. Kampala, Uganda.</span><span>Terms · Privacy · Anti-fraud notice</span></div>
</div></footer>

<a class="wa" href="#" onclick="toast('WhatsApp line to be added')">💬 WhatsApp us</a>
<div class="toast" id="toast"></div>

<script>
const DATA=__DATA__;
const FX={USD:1,UGX:3700,KES:129,JPY:150};
const SYM={USD:'$',UGX:'UGX ',KES:'KES ',JPY:'¥'};
const EMPTY=()=>({make:'',makes:[],model:'',year:'',price:'',pmin:'',body:'',bodies:[],kw:'',misc:'',disc:0,colours:[],records:false,kmmax:'',fuel:'',drive:'',trans:'',seats:'',steer:''});
let F=EMPTY();
const $=id=>document.getElementById(id);
function fmt(usd){const c=$('cur').value;const v=Math.round(usd*FX[c]);return SYM[c]+v.toLocaleString()}
function carSVG(c){const col={'Pearl White':'#E8ECF0','Silver':'#B9C2CC','Black':'#2B2F36','Grey':'#7A8591','Blue':'#2F6DB5','Red':'#C8323C','Wine':'#7A2C3A','Beige':'#CDBB9B'}[c.colour]||'#999';
 const suv=['SUV','Pick up','Van','Truck','Mini Van'].includes(c.body);const h=suv?34:26;
 return `<svg viewBox="0 0 200 110"><ellipse cx="100" cy="98" rx="80" ry="6" fill="#00000012"/><path d="M28 78 L36 ${78-h} Q40 ${72-h}48 ${72-h} L88 ${68-h} Q100 ${64-h}112 ${68-h} L150 ${72-h} Q160 ${72-h}165 ${78-h} L175 78 Q180 86 172 90 L28 90 Q20 86 28 78Z" fill="${col}"/><path d="M52 ${74-h} L88 ${70-h} L88 ${78-h+4} L50 ${78-h+4}Z M96 ${70-h} L146 ${74-h} L148 ${78-h+4} L96 ${78-h+4}Z" fill="#9FCBF0" opacity=".9"/><circle cx="60" cy="90" r="13" fill="#222"/><circle cx="60" cy="90" r="6" fill="#999"/><circle cx="142" cy="90" r="13" fill="#222"/><circle cx="142" cy="90" r="6" fill="#999"/><rect x="24" y="76" width="10" height="6" rx="2" fill="#FFD166"/><rect x="168" y="76" width="10" height="6" rx="2" fill="#D7263D"/></svg>`}
function render(){
 const c=$('cards');const q=(F.kw||'').toLowerCase();
 let list=DATA.cars.filter(x=>(!F.make||x.make===F.make)&&(!(F.makes||[]).length||F.makes.includes(x.make))&&(!F.model||x.model===F.model)&&(!F.year||x.year>=+F.year)&&(!F.price||x.price<=+F.price)&&(!F.pmin||x.price>=+F.pmin)&&(!F.body||x.body===F.body)&&(!(F.bodies||[]).length||F.bodies.includes(x.body))&&(!F.disc||x.disc>0)&&(!(F.colours||[]).length||F.colours.some(c=>x.colour.toLowerCase().includes(c)))&&(!F.records||x.records)&&(!F.kmmax||x.km<=+F.kmmax)&&(!F.fuel||x.fuel===F.fuel)&&(!F.drive||x.drive===F.drive)&&(!F.trans||x.trans===F.trans)&&(!F.seats||x.seats>=+F.seats)&&(!F.steer||x.steer===F.steer)
  &&(!F.misc||(F.misc==='LHD'?x.steer==='LHD':F.misc==='4WD'?x.drive==='4WD':F.misc==='MT'?x.trans==='MT':F.misc==='7seat'?x.seats>=7:x.fuel===F.misc))
  &&(!q||(x.make+' '+x.model+' '+x.year+' '+x.body+' '+x.drive+' '+x.ref+' '+x.fuel+' '+x.seats+' seater').toLowerCase().includes(q)));
 $('resHd').textContent=(Object.values(F).some(v=>Array.isArray(v)?v.length:v)?list.length+' cars found':'Featured cars');
 c.innerHTML=list.length?list.map(x=>`<div class="card"><div class="img">${carSVG(x)}<span class="loc">${x.loc}</span>${x.disc?`<span class="off">${x.disc}% OFF</span>`:''}${x.records?'<span class="rec">&#10004; Service records</span>':''}<span class="fav" onclick="toast('Saved to favourites')">♥</span></div>
 <div class="body"><div class="ttl">${x.year} ${x.make} ${x.model}</div><div class="ref">Ref No. ${x.ref} · ${x.body} · ${x.colour} · Grade ${x.grade}</div>
 <div class="specs"><div><b>Mileage</b> ${x.km.toLocaleString()} km</div><div><b>Engine</b> ${x.cc.toLocaleString()} cc</div><div><b>Trans</b> ${x.trans}</div><div><b>Fuel</b> ${x.fuel}</div><div><b>Drive</b> ${x.drive}</div><div><b>Steering</b> ${x.steer}</div></div>
 <div class="price"><strong>${fmt(x.price)}</strong>${x.old?`<s>${fmt(x.old)}</s>`:''}<small>FOB</small></div>
 <div class="cta"><a href="#" onclick="return toast('Inquiry form coming soon')">Inquiry</a><a class="p" href="#" onclick="return toast('Reserve and invoice coming soon')">Buy Now</a></div></div></div>`).join(''):'<p style="padding:20px;color:var(--mut)">No cars match. Clear a filter.</p>';
}
function fillModels(){F.make=$('fMake').value;const m=$('fModel');m.innerHTML='<option value="">Any</option>'+(DATA.models[F.make]||[]).map(x=>`<option>${x}</option>`).join('')}
function doSearch(e){e.preventDefault();if(e.target.classList.contains('hsearch')){$('askq').value=$('hq').value;return askSaaz(e)}else{F=EMPTY();Object.assign(F,{make:$('fMake').value,model:$('fModel').value,year:$('fYear').value,price:$('fPrice').value,body:$('fBody').value,kw:$('fKw').value})}hideUnderstood();render();$('cards').scrollIntoView({behavior:'smooth'});return false}
function quick(k,v){F=EMPTY();F[k]=v;hideUnderstood();render();$('cards').scrollIntoView({behavior:'smooth'})}
function filterMisc(v){quick('misc',v)}
function resetAll(){F=EMPTY();['fMake','fModel','fYear','fPrice','fBody','fKw','hq','askq'].forEach(i=>$(i).value='');hideUnderstood();render();return false}
function toggleRefine(){const b=$('refineBox');b.style.display=b.style.display==='none'?'block':'none'}
function hideUnderstood(){$('understood').style.display='none'}
function tab(b,t){document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');toast(t==='cars'?'Showing cars':'Section coming soon')}
function toast(m){const t=$('toast');t.textContent=m;t.style.display='block';clearTimeout(t._h);t._h=setTimeout(()=>t.style.display='none',1800);return false}
function checkDemo(e){e.preventDefault();const p=$('plate').value.trim();if(!p)return toast('Enter a plate or VIN');toast('Saaz Check: free preview and paid report come next');return false}
__NLJS__
(function init(){
 const mk=$('fMake');DATA.makes.forEach(([m,n])=>{mk.innerHTML+=`<option>${m}</option>`});
 $('makeList').innerHTML=DATA.makes.map(([m,n])=>`<li onclick="quick('make','${m}')">${m}<span>${n.toLocaleString()}</span></li>`).join('');
 $('priceList').innerHTML=[['Under $3,000',3000],['$3,000 - $5,000',5000],['$5,000 - $8,000',8000],['$8,000 - $12,000',12000],['$12,000 - $20,000',20000],['Over $20,000',999999]].map(([l,v])=>`<li onclick="quick('price',${v})">${l}<span>›</span></li>`).join('');
 $('typeList').innerHTML=DATA.types.map(([t,n])=>`<li onclick="quick('body','${t}')">${t}<span>${n.toLocaleString()}</span></li>`).join('');
 const ico={SUV:'🚙',Sedan:'🚗',Hatchback:'🚘',Truck:'🚚','Mini Van':'🚐',Van:'🚐','Pick up':'🛻',Bus:'🚌',Wagon:'🚗',Coupe:'🏎',Convertible:'🚗','Mini Bus':'🚌'};
 $('typeTiles').innerHTML=DATA.types.slice(0,12).map(([t,n])=>`<div class="tile" onclick="quick('body','${t}')"><span class="ico">${ico[t]||'🚗'}</span>${t}<span>${n.toLocaleString()} cars</span></div>`).join('');
 const by=$('fBody');[...new Set(DATA.types.map(t=>t[0]))].forEach(t=>by.innerHTML+=`<option>${t}</option>`);
 const yr=$('fYear');for(let y=2022;y>=2005;y--)yr.innerHTML+=`<option>${y}</option>`;
 $('stockTotal').textContent=DATA.makes.reduce((a,b)=>a+b[1],0).toLocaleString();
 $('cur').onchange=render;
 setInterval(()=>{$('jtime').textContent=new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit'})},1000);
 render();
})();
</script></body></html>'''
open('index.html','w').write(html.replace('__DATA__',json.dumps(D)).replace('__NLJS__',open('nl.js').read()))
print('written',len(html))
