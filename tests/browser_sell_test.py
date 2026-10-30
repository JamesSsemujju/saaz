"""The seller journey (23 Oct 2026): the public seller page, its preview card, sign-up straight into the listing form,
the form's guidance and preview, keeping unsaved work, and clearing it on save and sign-out. Run after tests/stack/reset.sh."""
import os, sys, re
from PIL import Image
from playwright.sync_api import sync_playwright
D = os.path.dirname(os.path.abspath(__file__))
SITE = "http://localhost:8777/saaz/"
W = int(sys.argv[1]) if len(sys.argv) > 1 else 390
photos = []
for i, c in enumerate([(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]):
    p = os.path.join(D, f"s{i}.jpg"); Image.new("RGB", (1600, 1200), c).save(p); photos.append(p)
ok = bad = 0
def check(name, cond, extra=""):
    global ok, bad
    if cond: ok += 1; print("PASS", name)
    else: bad += 1; print("FAIL", name, extra)

with sync_playwright() as pw:
    br = pw.chromium.launch(); errors = []
    c = br.new_context(viewport={"width": W, "height": 860}); pg = c.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "favicon" not in m.text and "cdnjs" not in m.text and "Failed to load resource" not in m.text else None)
    def go(h): pg.goto(SITE + h); pg.wait_for_timeout(900)
    def overflow(label):
        r = pg.evaluate("""()=>{const w=innerWidth;const bad=[...document.querySelectorAll('body *')].filter(e=>{const b=e.getBoundingClientRect();return b.width&&b.right>w+1&&!e.closest('.tablewrap,.appnav')}).map(e=>e.tagName+'.'+e.className).slice(0,4);return {sw:document.documentElement.scrollWidth>w,bad}}""")
        check(f"no sideways scroll: {label}", not r["sw"] and not r["bad"], r)
    def text(sel="#view"): return pg.inner_text(sel)
    def shot(name): pg.screenshot(path=os.path.join(D, f"sell_{name}_{W}.png"), full_page=True)

    # 1. The page, signed out
    go("#/sell")
    check("slate palette: dark bands are #06141B, body ink #253745",
          pg.evaluate("getComputedStyle(document.querySelector('.sellhero')).backgroundColor") == "rgb(6, 20, 27)" and pg.evaluate("getComputedStyle(document.body).color") == "rgb(37, 55, 69)",
          (pg.evaluate("getComputedStyle(document.querySelector('.sellhero')).backgroundColor"), pg.evaluate("getComputedStyle(document.body).color")))
    check("header Sell goes to the seller page when signed out", pg.get_attribute("[data-ref=sell-btn]", "href").endswith("#/sell"))
    check("hero headline and one main action", "Your car deserves the right buyer." in text() and pg.locator(".sellhero a.btn[data-start]").count() == 1)
    pg.wait_for_timeout(600)
    checks = pg.locator("#checks li").all_inner_texts()
    check("the 12 checks come from inspection_scopes", len(checks) == 12 and "Test drive" in checks and "VIN or chassis number" in checks, checks)
    check("extra checks named from the database", "Engine and gearbox" in text("#extras"), text("#extras"))
    check("valid days and lowest price read from settings", "60 days" in text("#limits") and "UGX 1,000,000" in text("#pricerule"))
    check("sample report is labelled", pg.locator(".samplereport .sample").inner_text().lower() == "sample")  # small capitals since 29 Oct 2026
    t = text()
    check("no invented fee, no enquiries, inspection required", "100,000" not in t and "enquir" not in t.lower() and "Required before your car goes live" in t)
    check("no sales yet: market says so, no invented prices", "as cars sell on Saaz" in text("#market"))
    check("preview card: no demand line, no link", pg.locator("#tpv .car.preview").count() == 1 and pg.locator("#tpv .demand").count() == 0 and pg.locator("#tpv a.car").count() == 0)
    overflow("seller page"); shot("page_empty")

    # 2. The preview card follows what is typed, and is kept for the form
    pg.fill("#tf input[name=make]", "Toyota"); pg.fill("#tf input[name=model]", "Harrier"); pg.fill("#tf input[name=year]", "2015")
    pg.fill("#tf input[name=mileage]", "78000"); pg.fill("#tf input[name=price]", "72000000")
    card = text("#tpv")
    check("card shows the car as typed", "2015 Toyota Harrier" in card and "78,000 km" in card and "UGX 72,000,000" in card, card)
    check("card never shows undefined or NaN", "undefined" not in card and "NaN" not in card)
    check("typed values kept on this phone", pg.evaluate("JSON.parse(localStorage.getItem('saaz-sellstart')).model") == "Harrier")
    shot("page_typed")
    pg.click("#tohow"); pg.wait_for_timeout(900)
    check("How it works scrolls to the steps", pg.evaluate("document.querySelector('#how').getBoundingClientRect().top < innerHeight"))

    # 3. Old address forwards
    pg.goto(SITE + "sell/"); pg.wait_for_timeout(1200)
    check("/sell/ forwards to the seller page", pg.url.endswith("#/sell") and "Your car deserves" in text())

    # 4. Start selling: sign-up with Seller ticked, then straight into the form
    pg.click(".sellhero a.btn[data-start]"); pg.wait_for_timeout(700)
    check("start goes to sign-up with Sell a car ticked", pg.url.endswith("#/signup") and pg.is_checked("input[name=as][value=seller]"))
    pg.fill("input[name=name]", "Sue Seller"); pg.fill("input[name=email]", f"sue{W}@x.test"); pg.fill("input[name=mobile]", "+256 700 111 222")
    pg.fill("input[name=password]", "demo1234"); pg.click("form button"); pg.wait_for_timeout(1500)
    check("after sign-up the listing form opens", "#/sell/new" in pg.url, pg.url)
    check("header Sell goes straight to the form when signed in", pg.get_attribute("[data-ref=sell-btn]", "href").endswith("#/sell/new"))

    # 5. The form: what was typed on the seller page fills the empty fields
    pg.fill("#vin", "JTEBU3FJ10K123456"); pg.click("#vf button"); pg.wait_for_timeout(1200)
    check("model, mileage and price carried from the seller page",
          pg.input_value("input[name=model]") == "Harrier" and pg.input_value("input[name=mileage]") == "78000" and pg.input_value("input[name=price]") == "72000000")
    check("decoded make kept", pg.input_value("input[name=make]") == "Toyota")
    check("buyer card beside the form", "Toyota Harrier" in text("#pv") and pg.locator("#pv .demand").count() == 0)
    check("mileage guidance shown", "odometer" in text("label:has(input[name=mileage])"))
    pg.fill("input[name=price]", "500000"); pg.wait_for_timeout(200)
    check("price below the floor: told the lowest price", "UGX 1,000,000" in text("#h-price"), text("#h-price"))
    pg.fill("input[name=price]", "72000000"); pg.wait_for_timeout(200)
    check("price hint without sales data stays factual", text("#h-price") == "You can change the price until a deal is agreed.", text("#h-price"))
    check("photo count guidance", "0 of at least 4" in text("#h-photos"))
    pg.fill("input[name=colour]", "Pearl white"); pg.fill("textarea[name=description]", "Short")
    check("description length guidance", "5 of at least 30" in text("#h-desc"), text("#h-desc"))
    pg.set_input_files("#files", photos); pg.wait_for_timeout(150)
    check("upload progress shows in the photo control", pg.is_visible("#upbar") and "of 4" in text("#uptext"), text("#uptext") if pg.locator("#uptext").count() else None)
    pg.wait_for_timeout(1200)
    check("upload progress ends with the count", text("#uptext") == "Uploaded 4 of 4" or pg.is_hidden("#upbar"), text("#uptext"))
    pg.wait_for_timeout(1800)
    check("progress bar tidies away when done", pg.is_hidden("#upbar"))
    check("4 photos uploaded, guidance updated", pg.locator("#thumbs img").count() == 4 and "4 photos added" in text("#h-photos"), text("#h-photos"))
    check("first photo shows on the buyer card", pg.locator("#pv .car-photo img").count() == 1)
    overflow("listing form"); shot("form")

    # 6. Reload: unsaved work comes back
    pg.reload(); pg.wait_for_timeout(2500)
    check("after a reload the form is restored", pg.locator("#restored").count() == 1 and pg.input_value("input[name=colour]") == "Pearl white" and pg.locator("#thumbs img").count() == 4,
          (pg.locator("#restored").count(), pg.input_value("input[name=colour]") if pg.locator("input[name=colour]").count() else None))

    # 7. Save the draft: local copy cleared, car page shows the next step and the buyer view
    pg.select_option("#reg", "Kampala"); pg.fill("input[name=plate]", "UBA 123X")
    pg.fill("textarea[name=description]", "Clean Harrier, one owner in Uganda, full service history at the dealer.")
    pg.check("input[name=logbook_name_matches]")
    pg.route("**/rpc/save_listing", lambda r: (pg.wait_for_timeout(700), r.continue_()))
    pg.click("button[value=save]"); pg.wait_for_timeout(200)
    check("saving shows a busy toast with a spinner", "busy" in pg.get_attribute("#toast", "class") and "Saving your draft" in text("#toast"), pg.get_attribute("#toast", "class"))
    pg.wait_for_timeout(2000); pg.unroute("**/rpc/save_listing")
    check("draft saved, car page opens", "#/my/cars/" in pg.url, pg.url)
    check("local copy cleared after saving", pg.evaluate("Object.keys(localStorage).filter(k=>/^saaz-sell/.test(k)).length") == 0)
    check("next step shown on the car page", "Next: submit it for a Saaz inspection" in text())
    check("See it as buyers will", pg.locator("a:has-text('See it as buyers will')").count() == 1)
    pg.click("a:has-text('See it as buyers will')"); pg.wait_for_timeout(1500)
    check("buyer view of the draft opens with the preview notice", "Preview: not on the marketplace" in text())
    overflow("car page preview")

    # 8. Sign-out clears any local seller copy
    pg.evaluate("localStorage.setItem('saaz-selldraft-x','{}'); localStorage.setItem('saaz-sellstart','{}')")
    pg.evaluate("Saaz.signOut()"); pg.wait_for_timeout(1800)
    check("sign-out lands on the listings", re.sub(r"#.*$", "", pg.url) == SITE, pg.url)
    check("sign-out clears the seller copies", pg.evaluate("Object.keys(localStorage).filter(k=>/^saaz-sell/.test(k)).length") == 0)

    check("no script errors", not errors, errors[:5])
    br.close()
print(f"\n{ok} passed, {bad} failed")
sys.exit(1 if bad else 0)
