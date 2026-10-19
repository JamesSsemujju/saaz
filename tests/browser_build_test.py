"""Browser test for the Build Assistant (part 18) on the local stack.
Usage: python3 tests/browser_build_test.py <site url> <width>   (run on a fresh database; it adds its own people and cars)
Covers: who sees it, the admin switch, annotation mode, the persistent editor with many tags, cursor and focus, outside clicks,
duplicates, removing a tag, typed references, drafts across pages and reloads, Cancel, chat, the task conversation with the
agent (driven here through the agent's database functions), touch selection, switching off, and privacy of the API."""
import sys, os, json, time, base64, hashlib, hmac, struct, urllib.request, psycopg2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import admin_session
from playwright.sync_api import sync_playwright
SITE, W = sys.argv[1], int(sys.argv[2]); API = "http://127.0.0.1:54321"
db = psycopg2.connect(host="/var/tmp/saazpg", port=5433, user="postgres", dbname="sb"); db.autocommit = True; cur = db.cursor()
def sql(q, a=()): cur.execute(q, a or None); return cur.fetchall() if cur.description else None
def user(e, n): return sql("insert into auth.users (email, raw_user_meta_data) values (%s,%s) returning id", (e, json.dumps({"name": n, "country": "UG"})))[0][0]
A = user("admin@saaz.test", "Ann Admin"); sql("insert into admins (user_id, name, role) values (%s,'Ann Admin','admin')", (A,))
SEL = user("seller@x.test", "Sam Seller"); STF = user("staff@saaz.test", "Stan Staff"); sql("insert into admins (user_id, name, role) values (%s,'Stan Staff','staff')", (STF,))
SECRET = "JBSWY3DPEHPK3PXP"
for u in (A, STF): admin_session.claims(cur, u)
cur.execute("reset role"); sql("update auth.mfa_factors set secret=%s", (SECRET,))
for i, (mk, md, pr) in enumerate([("Toyota", "Premio", 30000000), ("Subaru", "Forester", 60000000), ("Honda", "Fit", 25000000)]):
    vid = sql("insert into vehicles (vin, make, model) values (%s,%s,%s) returning id", ("JTBUILD%010d" % i, mk, md))[0][0]
    sql("""insert into listings (vehicle_id, seller_id, country, region, status, make, model, year, fuel, gearbox, body, colour, engine, mileage, plate, currency, price,
           description, photos, logbook_name_matches, owner_authorised, live_at) values (%s,%s,'UG','Kampala','live',%s,%s,2015,'Petrol','Automatic','Sedan','White','1.5',80000,%s,'UGX',%s,'Clean car',%s,true,true,now())""",
        (vid, SEL, mk, md, "UBT %03dT" % i, pr, ["a.webp"]))
def totp(secret):
    k = base64.b32decode(secret); h = hmac.new(k, struct.pack(">Q", int(time.time()) // 30), hashlib.sha1).digest(); o = h[-1] & 15
    return "%06d" % ((struct.unpack(">I", h[o:o + 4])[0] & 0x7fffffff) % 1000000)
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("PASS", f"{n} @{W}")
    else: bad += 1; print("FAIL", f"{n} @{W}", str(x)[:400])
errors = []
EXPECT = ("//vehicle-card The spacing here is inconsistent with //header and should align with the navigation. Also compare it with //filter-panel "
          "because both components should follow the same spacing system.")
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(touch=False):
        ctx = br.new_context(viewport={"width": W, "height": 800 if W >= 768 else 760}, has_touch=touch, is_mobile=touch and W < 768)
        pg = ctx.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); return pg
    def shot(pg, name):   # optional review screenshots: set SHOTS to a folder
        if os.environ.get("SHOTS"): pg.screenshot(path=os.path.join(os.environ["SHOTS"], f"Build_{name}_{W}.png"))
    def go(pg, h): pg.goto("about:blank"); pg.goto(SITE + h); pg.wait_for_timeout(1300)
    def signin(pg, email):
        go(pg, "#/signin"); pg.check("input[name=as][value=seller]"); pg.fill("input[name=email]", email); pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    def elevate(pg):
        go(pg, "#/admin/verify"); pg.fill("input[name=password]", "demo1234"); pg.click("#pf button"); pg.wait_for_timeout(1200)
        pg.fill("input[name=code]", totp(SECRET)); pg.click("#cf button"); pg.wait_for_timeout(1800)
    def text(pg): return pg.evaluate("() => Saaz.buildAssistant.serialize().body")
    def refs(pg): return [r["ref_name"] for r in pg.evaluate("() => Saaz.buildAssistant.serialize().refs")]
    def focused(pg): return pg.evaluate("() => document.activeElement && document.activeElement.classList.contains('ba-editor')")
    def blank_point(pg, sel):   # a visible point inside the element where the element itself (not a child) is under the pointer
        pg.evaluate("(sel) => { const el = document.querySelector(sel); if (!el) return; const sheet = document.querySelector('.ba-panel:not([hidden])'), floor = sheet ? sheet.getBoundingClientRect().top : innerHeight, r = el.getBoundingClientRect(); if (r.top < 0 || r.top > floor - 60) el.scrollIntoView({block: 'start'}); }", sel)
        pg.wait_for_timeout(300)   # scrolling the page the way a person would before tapping something off-screen
        return pg.evaluate("""(sel) => { const el = document.querySelector(sel); if (!el) return null; const r = el.getBoundingClientRect();
          const sheet = document.querySelector('.ba-panel:not([hidden])'), floor = sheet ? Math.min(innerHeight, sheet.getBoundingClientRect().top) : innerHeight;
          const top = Math.max(r.top, 0) + 2, bottom = Math.min(r.bottom, floor) - 2, left = Math.max(r.left, 0) + 2, right = Math.min(r.right, innerWidth) - 2;
          for (let y = top; y < bottom; y += 3) for (let x = left; x < right; x += 3) if (document.elementFromPoint(x, y) === el) return [x, y]; return null; }""", sel)

    # ---------- who sees it ----------
    pub = page(); go(pub, "#/browse")
    check("visitors: no Build button and no assistant script", pub.locator(".ba-launch").count() == 0 and pub.locator("script[src*='build-assistant']").count() == 0)
    sel = page(); signin(sel, "seller@x.test"); go(sel, "#/browse")
    check("sellers: no Build button and no assistant script", sel.locator(".ba-launch").count() == 0 and sel.locator("script[src*='build-assistant']").count() == 0)
    tok = sel.evaluate("() => Saaz.state.session.access_token")
    def api(path, body, token, profile=None):
        req = urllib.request.Request(API + path, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json", "apikey": "LOCALANON", "Authorization": "Bearer " + token, **({"Content-Profile": profile, "Accept-Profile": profile} if profile else {})})
        try: return urllib.request.urlopen(req).read().decode()
        except urllib.error.HTTPError as e: return "HTTP %d %s" % (e.code, e.read().decode()[:200])
    check("a seller calling the history function directly gets nothing", api("/rest/v1/rpc/build_history", {"p_limit": 10, "p_task": None}, tok).startswith("HTTP 4"))
    check("the build tables can't be reached through the API at all", api("/rest/v1/messages?select=*", {}, tok, profile="build").startswith("HTTP 4"))
    adm = page(); signin(adm, "admin@saaz.test"); go(adm, "#/browse")
    check("an admin without the admin session: no Build button", adm.locator(".ba-launch").count() == 0)
    elevate(adm); go(adm, "#/browse")
    check("an admin in an admin session, assistant off: no Build button", adm.locator(".ba-launch").count() == 0)
    go(adm, "#/admin/build")
    check("the switch is in Admin, System, Build Assistant", "Build Assistant" in adm.inner_text("#view") and "Off" in adm.inner_text(".pagehead"))
    adm.fill("#bsw input[name=reason]", "Start the redesign"); adm.click("#bsw button"); adm.wait_for_timeout(2500)
    check("switched on by the admin, with the reason in the history", "On" in adm.inner_text(".pagehead") and "Start the redesign" in adm.inner_text("#view"))
    go(adm, "#/browse")
    check("on: the Build button appears", adm.locator(".ba-launch").count() == 1)
    stf = page(); signin(stf, "staff@saaz.test"); elevate(stf); go(stf, "#/browse")
    check("staff who aren't developers still don't get it", stf.locator(".ba-launch").count() == 0)

    # ---------- annotating ----------
    adm.click(".ba-launch"); adm.check(".ba-switch input"); adm.wait_for_timeout(300)
    check("with the panel open, the floating bar steps aside so the header stays clear", adm.locator(".ba-modebar").is_hidden() and adm.locator(".ba-switch input").is_checked())
    adm.click(".ba-head [data-act=close]"); adm.wait_for_timeout(300)
    check("annotation mode is shown clearly when the panel is closed", adm.locator(".ba-modebar").is_visible() and "Annotating" in adm.inner_text(".ba-modebar"))
    hb, bb = adm.locator(".apphead").bounding_box(), adm.locator(".ba-modebar").bounding_box()
    check("the bar doesn't cover the header", bb["y"] >= hb["y"] + hb["height"], (hb, bb))
    adm.click(".ba-launch"); adm.wait_for_timeout(300)
    url0 = adm.url; adm.locator(".car").first.click(); adm.wait_for_timeout(600)
    check("while selecting, clicking a car link doesn't open it", adm.url == url0)
    adm.locator(".car").first.dblclick(); adm.wait_for_timeout(1200)
    check("double-clicking a car card opens the editor with it as the first reference", adm.locator(".ba-editor").count() == 1 and refs(adm) == ["vehicle-card"], refs(adm))
    check("focus is in the editor", focused(adm))
    adm.keyboard.type("The spacing here is inconsistent with")
    hp = blank_point(adm, ".apphead .wrap") or blank_point(adm, ".apphead")
    adm.mouse.click(hp[0], hp[1]); adm.wait_for_timeout(1000)
    check("clicking the header tags it into the same comment", refs(adm) == ["vehicle-card", "header"], refs(adm))
    check("focus came back to the editor", focused(adm))
    adm.keyboard.type("and should align with the navigation. Also compare it with")
    pt = blank_point(adm, "#flt")
    adm.mouse.click(pt[0], pt[1]); adm.wait_for_timeout(1000)
    adm.keyboard.type("because both components should follow the same spacing system.")
    check("one comment, three tagged elements, text exactly as typed", text(adm) == EXPECT, text(adm))
    shot(adm, "1-comment-with-three-tags")
    main_pt = blank_point(adm, "main")
    if main_pt: adm.mouse.click(main_pt[0], main_pt[1]); adm.wait_for_timeout(500)
    check("clicking empty page space doesn't close the editor or change the comment", adm.locator(".ba-editor").count() == 1 and text(adm) == EXPECT)
    hp = blank_point(adm, ".apphead .wrap") or blank_point(adm, ".apphead"); adm.mouse.click(hp[0], hp[1]); adm.wait_for_timeout(1000)
    check("tagging the header again doesn't add it twice", text(adm) == EXPECT and "already in this comment" in adm.inner_text(".ba-note"))
    adm.click(".ba-note [data-act=again]"); adm.wait_for_timeout(400)
    check("but it can be inserted again on purpose", text(adm).count("//header") == 2)
    adm.locator(".ba-editor .ba-chip[data-name=header] button").last.click(); adm.wait_for_timeout(300)
    check("removing a tag leaves the rest of the text intact", text(adm) == EXPECT, text(adm))
    # the cursor decides where a tag goes: put it at the very start, then tag the logo
    adm.evaluate("() => { const e = document.querySelector('.ba-editor'); const r = document.createRange(); r.setStart(e, 0); r.collapse(true); getSelection().removeAllRanges(); getSelection().addRange(r); }")
    adm.locator(".apphead .logo").scroll_into_view_if_needed(); adm.click(".apphead .logo"); adm.wait_for_timeout(1000)
    check("a tag goes where the cursor is, not at the end", text(adm).startswith("//logo") and text(adm).endswith("spacing system."), text(adm))
    adm.locator(".ba-editor .ba-chip[data-name=logo] button").click(); adm.wait_for_timeout(300)
    check("and removing it restores the comment", text(adm) == EXPECT, text(adm))
    # drafts survive moving to another page and a reload
    adm.uncheck(".ba-switch input"); adm.wait_for_timeout(300)
    car_ref = adm.locator(".car").first.get_attribute("data-ref-key")
    adm.locator(".car").first.click(); adm.wait_for_timeout(1500)
    check("with selecting off, the site works normally (as admin the car opens its admin page, BA-0003)", "#/admin/car/" in adm.url, adm.url)
    check("the draft is still there on the next page", text(adm) == EXPECT)
    adm.evaluate("(r) => { location.hash = '#/car/' + r; }", car_ref); adm.wait_for_timeout(1500)   # the buyer's page of the same car
    check("and on the page after that", text(adm) == EXPECT)
    adm.check(".ba-switch input"); pt = blank_point(adm, ".buybox"); adm.mouse.click(pt[0], pt[1]); adm.wait_for_timeout(1000)
    check("an element on another page joins the same comment", refs(adm) == ["vehicle-card", "header", "filter-panel", "price-panel"], refs(adm))
    adm.reload(); adm.wait_for_timeout(2500)
    check("after a reload the draft comes back with every tag", adm.locator(".ba-editor").count() == 1 and refs(adm) == ["vehicle-card", "header", "filter-panel", "price-panel"], refs(adm))
    full = text(adm)
    adm.click("[data-act=cancel]"); adm.wait_for_timeout(300)
    check("Cancel asks before throwing away written text", adm.locator(".ba-confirm").is_visible() and adm.locator(".ba-editor").count() == 1)
    adm.click("[data-act=keep]"); adm.wait_for_timeout(300)
    check("Keep writing returns to the same draft", text(adm) == full and adm.locator(".ba-confirm").is_hidden())
    adm.evaluate("() => { const e = document.querySelector('.ba-editor'); e.append(' Also see //nosuch.'); e.dispatchEvent(new Event('input')); }")
    adm.click("[data-act=save]"); adm.wait_for_timeout(1200)
    check("a typed reference that doesn't exist is refused, not guessed", "Unknown reference: //nosuch" in adm.inner_text(".ba-err") and sql("select count(*) from build.messages")[0][0] == 0)
    adm.evaluate("() => { const e = document.querySelector('.ba-editor'); e.lastChild.remove(); e.dispatchEvent(new Event('input')); }")
    adm.click("[data-act=save]"); adm.wait_for_timeout(1500)
    m = sql("select id, body from build.messages")
    check("saved: one comment, exactly the text, four element links", len(m) == 1 and m[0][1] == full and
          [x[0] for x in sql("select ref_name from build.message_refs where message_id=%s order by ordinal", (m[0][0],))] == ["vehicle-card", "header", "filter-panel", "price-panel"], m)
    check("saved means saved and queued, nothing more", sql("select status from build.tasks")[0][0] == "queued" and "Queued: waiting for the agent" in adm.inner_text(".ba-body"))
    shot(adm, "2-saved-and-queued")
    check("the draft is cleared after saving", adm.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('saaz-build-draft')).length") == 0)

    # ---------- chat ----------
    adm.uncheck(".ba-switch input") if adm.locator(".ba-switch input").count() else None
    adm.click("[data-tab=chat]"); adm.fill(".ba-chat textarea", "Review the seller registration workflow before proposing changes.")
    adm.click(".ba-chat button"); adm.wait_for_timeout(1500)
    check("a chat instruction is saved as its own project-wide task", sql("select count(*) from build.tasks where scope='project'")[0][0] == 1)
    adm.fill(".ba-chat textarea", "Note: launch is next month."); adm.select_option(".ba-chat select[name=message_kind]", "note"); adm.click(".ba-chat button"); adm.wait_for_timeout(1500)
    check("a chat note is kept without a task", sql("select count(*) from build.messages where kind='note'")[0][0] == 1 and sql("select count(*) from build.tasks")[0][0] == 2)

    # ---------- the agent's side, then the conversation in the page ----------
    sql("select build_agent_checkin('claude', 'test')")
    ctx = sql("select build_agent_claim('claude', 60)")[0][0]; tid = ctx["task"]["id"]
    sql("select build_agent_update('claude', %s, 'acknowledged', 'Received', %s::jsonb)", (tid, json.dumps({"understanding": "Align card, header, filters and price panel spacing.", "report": "I understood: one spacing system for four components."})))
    sql("select build_agent_update('claude', %s, 'needs_clarification', 'Which spacing?', %s::jsonb)", (tid, json.dumps({"question": "Should the card follow the header's 24 px or the filters' 16 px?"})))
    adm.click("[data-tab=tasks]"); adm.wait_for_timeout(1500)
    adm.locator(".ba-task", has_text=ctx["task"]["ref"]).locator("summary").click(); adm.wait_for_timeout(300)
    t = adm.locator(".ba-task", has_text=ctx["task"]["ref"]).inner_text()
    check("the page shows the agent's acknowledgement, what it understood, and its question", "Acknowledged by the agent" in t and "one spacing system" in t and "Needs your answer" in t and "24 px" in t, t[:600])
    check("the agent's last check-in is shown", "just now" in adm.inner_text(".ba-agent") or "min ago" in adm.inner_text(".ba-agent"))
    box = adm.locator(".ba-task", has_text=ctx["task"]["ref"]); box.locator(".ba-reply input").fill("The header's 24 px."); box.locator(".ba-reply button").click(); adm.wait_for_timeout(1500)
    check("answering puts the task back in the queue", sql("select status from build.tasks where id=%s", (tid,))[0][0] == "queued")

    # ---------- touch ----------
    if W < 768:
        tp = page(touch=True); signin(tp, "admin@saaz.test"); elevate(tp); go(tp, "#/browse")
        tp.tap(".ba-launch"); tp.locator(".ba-switch input").tap(); tp.wait_for_timeout(300)
        tp.locator(".car").first.tap(); tp.wait_for_timeout(500)
        check("touch: a tap selects and offers Comment (no hover or double tap needed)", tp.locator(".ba-panel .ba-pick [data-act=comment-picked]").is_visible() and "#/car/" not in tp.url)
        tp.locator(".ba-panel .ba-pick [data-act=comment-picked]").tap(); tp.wait_for_timeout(1200)
        check("touch: the editor opens with the tapped element", refs(tp) == ["vehicle-card"])
        tp.locator(".apphead .logo").tap(); tp.wait_for_timeout(1000)
        check("touch: tapping another element tags it", refs(tp) == ["vehicle-card", "logo"], refs(tp))
        shot(tp, "4-touch-tagging")
        check("touch: no sideways scroll with the panel open", not tp.evaluate("() => document.documentElement.scrollWidth > innerWidth + 1"))

    # ---------- the empty "No cars" box can be tagged, and pages are saved as /browse ----------
    check("pages are saved by their plain address (/browse, not \\/browse)", sql("select count(*) from build.messages where route like '%%\\%%'")[0][0] == 0 and sql("select count(*) from build.messages where route = '/browse'")[0][0] >= 1)
    go(adm, "#/browse?make=Nomake")
    if not adm.locator(".ba-panel").is_visible(): adm.click(".ba-launch"); adm.wait_for_timeout(300)
    adm.click("[data-tab=comment]"); adm.wait_for_timeout(300)
    if not adm.locator(".ba-switch input").is_checked(): adm.check(".ba-switch input"); adm.wait_for_timeout(300)
    ep = blank_point(adm, ".empty"); adm.mouse.dblclick(ep[0], ep[1]); adm.wait_for_timeout(1200)
    check("the dashed box shown when no cars match can be tagged as //no-cars", refs(adm)[:1] == ["no-cars"], refs(adm))
    adm.click("[data-act=cancel]"); adm.wait_for_timeout(300)
    if adm.locator("[data-act=discard]").is_visible(): adm.click("[data-act=discard]"); adm.wait_for_timeout(300)

    # ---------- switched off ----------
    if adm.locator(".ba-switch input").count() and adm.locator(".ba-switch input").is_checked(): adm.uncheck(".ba-switch input")   # stop selecting to use Admin normally
    elif adm.locator(".ba-modebar").is_visible(): adm.click(".ba-modebar [data-act=mode-off]")
    go(adm, "#/admin/build"); shot(adm, "3-admin-switch-and-history"); adm.fill("#bsw input[name=reason]", "Ready to ship"); adm.click("#bsw button"); adm.wait_for_timeout(2500)
    go(adm, "#/browse")
    check("off: the Build button is gone", adm.locator(".ba-launch").count() == 0)
    atok = adm.evaluate("() => Saaz.state.session.access_token")
    r = api("/rest/v1/rpc/build_submit", {"p": {"kind": "chat", "body": "sneaky", "client_key": "zz", "refs": []}}, atok)
    check("off: calling the API directly is refused", "switched off" in r, r)
    check("off: the marketplace works as before", adm.locator(".car").count() == 3)
    check("off: nothing was removed or marked done", sql("select count(*) from build.messages")[0][0] >= 3 and sql("select count(*) from build.tasks where status in ('verified')")[0][0] == 0)
    check("no script errors", not errors, errors[:3])
    br.close()
print(f"\n{ok} passed, {bad} failed")
