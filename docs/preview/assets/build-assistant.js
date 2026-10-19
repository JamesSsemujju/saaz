/* build-assistant.js: the private Build Assistant (part 18). Loaded only after the database says this person may use it
   and it is switched on (build_status). Hiding it is not the protection: every read and write goes through build_* functions
   that check the admin session, the developer list and the switch on the server.
   Lives outside #app, so moving between pages never closes the editor or loses a draft. */
(function () {
  var S = window.Saaz, esc = S.esc;
  if (!S || S._buildLoaded) return; S._buildLoaded = true;
  var uid = (S.me() || {}).id || "anon", DRAFT = "saaz-build-draft:" + uid, MODE = "saaz-build-mode";
  var STATUS = { queued: "Queued: waiting for the agent", acknowledged: "Acknowledged by the agent", in_progress: "In progress", needs_clarification: "Needs your answer",
    blocked: "Blocked", implemented: "Implemented, not yet verified", verifying: "Verifying", verified: "Verified", failed: "Failed", cancelled: "Cancelled" };
  var REF_RE = /(^|[^\/\w:])\/\/([a-z0-9]+(?:-[a-z0-9]+)*)/g;
  var st = { mode: false, editor: false, tab: "comment", busy: false, picked: null, status: null };
  function uuid() { return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  function save(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function ago(iso) {
    if (!iso) return "never"; var m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 1 ? "just now" : m < 60 ? m + " min ago" : m < 1440 ? Math.round(m / 60) + " h ago" : Math.round(m / 1440) + " days ago";
  }
  function routeNow() {
    var path = (location.hash.replace(/^#/, "") || "/").split("?")[0];
    for (var i = 0; i < S.routes.length; i++) if (S.routes[i].re.test(path)) return S.routes[i].re.source.replace(/^\^|\$$/g, "");
    return path;
  }

  // ---------- the parts on the page ----------
  var root = document.createElement("div"); root.id = "ba-root"; root.className = "ba";
  root.innerHTML =
    "<div class='ba-modebar' hidden><b>Annotating</b><span class='ba-hint'></span><span class='ba-pick'></span><button type='button' class='btn text small' data-act='mode-off'>Stop</button></div>" +
    "<div class='ba-outline' hidden></div>" +
    "<button type='button' class='ba-launch' aria-expanded='false' aria-controls='ba-panel'>Build</button>" +
    "<section id='ba-panel' class='ba-panel' hidden aria-label='Build Assistant'>" +
      "<header class='ba-head'><b>Build Assistant</b><span class='ba-agent'></span><button type='button' class='btn text small' data-act='close'>Hide</button></header>" +
      "<nav class='ba-tabs' role='tablist'><button type='button' role='tab' data-tab='comment'>Comment</button><button type='button' role='tab' data-tab='chat'>Chat</button><button type='button' role='tab' data-tab='tasks'>Tasks</button></nav>" +
      "<div class='ba-body'></div>" +
    "</section>";
  document.body.appendChild(root);
  var panel = root.querySelector(".ba-panel"), body = root.querySelector(".ba-body"), bar = root.querySelector(".ba-modebar"), outline = root.querySelector(".ba-outline");
  var launch = root.querySelector(".ba-launch");

  // ---------- which element was pointed at, and how it is named ----------
  // Components carry data-ref="name" in the templates (the stable identity). Anything inside one is named by its component
  // plus its own visible label ("anchored"). With no component around it, the reference is marked "unstable" and the page says so.
  var PICKABLE = "a,button,input,select,textarea,label,img,h1,h2,h3,h4,p,li,dt,dd,th,td,figure,svg,summary,section,nav,form,[role]";
  function chainOf(el) { var c = []; for (var x = el; x && x !== document.body; x = x.parentElement) if (x.dataset && x.dataset.ref) c.unshift(x.dataset.ref); return c; }
  function labelOf(el) {
    var t = el.getAttribute("aria-label") || el.getAttribute("name") || el.getAttribute("placeholder") || el.getAttribute("alt") || el.getAttribute("title") || el.textContent || "";
    return t.replace(/\s+/g, " ").trim().slice(0, 40);
  }
  function slug(t) { return String(t).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").split("-").slice(0, 4).join("-"); }
  function targetOf(node) {
    if (!node || !node.closest || node.closest("#ba-root")) return null;
    var ref = node.closest("[data-ref]"), pick = node.closest(PICKABLE);
    // prefer the smallest of: the component itself, or a labelled thing inside it
    if (pick && ref && ref.contains(pick) && pick !== ref && labelOf(pick)) {
      // a component's only content, or a child that nearly fills it (a logo's image), is the component itself
      var a = pick.getBoundingClientRect(), b = ref.getBoundingClientRect();
      if (a.width * a.height < 0.6 * b.width * b.height && ref.querySelectorAll(PICKABLE).length > 1) return pick;
    }
    return ref || pick || null;
  }
  function describe(el) {
    var chain = chainOf(el), own = el.dataset && el.dataset.ref, label = own ? "" : labelOf(el);
    var key = el.closest("[data-ref-key]"); key = key ? key.dataset.refKey : null;
    if (own) return { anchor_path: chain.join(">"), descriptor: { tag: el.tagName.toLowerCase(), role: "", label: "" }, stability: "stable", base_name: own, item_key: key };
    if (chain.length && label) return { anchor_path: chain.join(">"), descriptor: { tag: el.tagName.toLowerCase(), role: el.getAttribute("role") || "", label: label },
      stability: "anchored", base_name: slug(chain[chain.length - 1] + " " + label), item_key: key };
    return { anchor_path: (chain.join(">") || "page") + "?" + el.tagName.toLowerCase(), descriptor: { tag: el.tagName.toLowerCase(), role: el.getAttribute("role") || "", label: label },
      stability: "unstable", base_name: slug(label || el.tagName.toLowerCase()) || "element", item_key: key };
  }
  function register(el) {
    var d = describe(el);
    return S.rpc("build_element", { p: { anchor_path: d.anchor_path, descriptor: d.descriptor, stability: d.stability, route: routeNow(), base_name: d.base_name } })
      .then(function (r) { r.item_key = d.item_key; return r; });
  }
  function showOutline(el, tagged) {
    if (!el) { outline.hidden = true; return; }
    var r = el.getBoundingClientRect(); outline.hidden = false;
    outline.style.top = r.top + "px"; outline.style.left = r.left + "px"; outline.style.width = r.width + "px"; outline.style.height = r.height + "px";
    outline.className = "ba-outline" + (tagged ? " tagged" : "");
  }

  // ---------- the editor: one comment, many tagged elements ----------
  // The draft is kept on every change (this browser, this account) so nothing is lost on a page change, a re-render or a reload.
  var ed, edState = null, lastRange = null;
  function draft() { return load(DRAFT); }
  function chipHtml(r) {
    return "<span class='ba-chip' contenteditable='false' data-el='" + esc(r.id) + "' data-name='" + esc(r.ref_name) + "' data-key='" + esc(r.item_key || "") + "' data-stab='" + esc(r.stability) + "'" +
      " title='" + (r.stability === "unstable" ? "No stable reference: the agent will check it before acting" : r.stability === "anchored" ? "Found by its component and label" : "Stable reference") + "'>//" + esc(r.ref_name) +
      "<button type='button' tabindex='-1' aria-label='Remove //" + esc(r.ref_name) + "' data-act='unchip'>×</button></span>";
  }
  function serialize() {   // the text with //names, and the elements in the order they first appear
    var out = "", refs = [], seen = {};
    (function walk(n) {
      n.childNodes.forEach(function (c) {
        if (c.nodeType === 3) out += c.nodeValue;
        else if (c.classList && c.classList.contains("ba-chip")) {
          out += "//" + c.dataset.name;
          if (!seen[c.dataset.el]) { seen[c.dataset.el] = 1; refs.push({ element_id: c.dataset.el, ref_name: c.dataset.name, item_key: c.dataset.key || null, stability: c.dataset.stab }); }
        } else if (c.nodeName === "BR") out += "\n";
        else { if (c.nodeName === "DIV" && out && !/\n$/.test(out)) out += "\n"; walk(c); }
      });
    })(ed);
    return { body: out.replace(/\u00a0/g, " ").replace(/ {2,}/g, " ").trim(), refs: refs };
  }
  function keep() { if (!ed || !edState) return; edState.html = ed.innerHTML; save(DRAFT, edState); renderChipsBar(); }
  function openEditor(firstRef) {
    if (!edState) edState = draft() || { key: uuid(), html: "", route: routeNow(), started: new Date().toISOString() };
    st.editor = true; st.tab = "comment"; showPanel(true); renderTab();
    if (firstRef && !ed.querySelector("[data-el='" + firstRef.id + "']")) { ed.innerHTML = chipHtml(firstRef) + "&nbsp;" + ed.innerHTML; placeCaretEnd(); keep(); }
    ed.focus(); placeCaretEnd();
  }
  function placeCaretEnd() { var r = document.createRange(); r.selectNodeContents(ed); r.collapse(false); var s = getSelection(); s.removeAllRanges(); s.addRange(r); lastRange = r.cloneRange(); }
  document.addEventListener("selectionchange", function () {
    if (!ed) return; var s = getSelection(); if (s.rangeCount && ed.contains(s.anchorNode)) lastRange = s.getRangeAt(0).cloneRange();
  });
  function insertChip(r, force) {
    var existing = ed.querySelector("[data-el='" + r.id + "']");
    if (existing && !force) {   // already in this comment: show it, and offer to add it again on purpose
      existing.classList.add("flash"); setTimeout(function () { existing.classList.remove("flash"); }, 900);
      note("//" + r.ref_name + " is already in this comment. <button type='button' class='btn text small' data-act='again'>Insert it again</button>", r);
      ed.focus(); restoreRange(); return;
    }
    var holder = document.createElement("span"); holder.innerHTML = chipHtml(r); var chip = holder.firstChild, space = document.createTextNode("\u00a0");
    var range = lastRange && ed.contains(lastRange.startContainer) ? lastRange : null;
    if (range) {
      // never inside another tag: put it just after that tag
      var inChip = range.startContainer.nodeType === 1 ? range.startContainer.closest && range.startContainer.closest(".ba-chip") : range.startContainer.parentElement && range.startContainer.parentElement.closest(".ba-chip");
      if (inChip) { range = document.createRange(); range.setStartAfter(inChip); range.collapse(true); }
      range.deleteContents();
      // a space before the tag when it would touch the word before it
      var before = range.startContainer.nodeType === 3 ? range.startContainer.nodeValue.slice(0, range.startOffset) : "";
      range.insertNode(space); range.insertNode(chip);
      if (before && !/[\s\u00a0]$/.test(before)) chip.parentNode.insertBefore(document.createTextNode(" "), chip);
    } else { ed.appendChild(chip); ed.appendChild(space); }
    var after = document.createRange(); after.setStartAfter(space); after.collapse(true);
    ed.focus(); var s = getSelection(); s.removeAllRanges(); s.addRange(after); lastRange = after.cloneRange();
    note(""); keep();
  }
  function restoreRange() { if (lastRange) { var s = getSelection(); s.removeAllRanges(); s.addRange(lastRange); } }
  function note(html, r) {
    var n = root.querySelector(".ba-note"); if (!n) return; n.innerHTML = html;
    var again = n.querySelector("[data-act='again']"); if (again) again.onclick = function () { insertChip(r, true); };
  }
  function renderChipsBar() {   // the elements this comment is about, shown apart from the text
    var b = root.querySelector(".ba-tagged"); if (!b || !ed) return;
    var refs = serialize().refs;
    b.innerHTML = refs.length ? "About: " + refs.map(function (r) { return "<span class='badge'>//" + esc(r.ref_name) + (r.stability === "unstable" ? " (unstable)" : "") + "</span>"; }).join(" ") : "No element tagged yet.";
  }
  function discardDraft() { edState = null; save(DRAFT, null); st.editor = false; if (ed) ed.innerHTML = ""; renderTab(); }
  function submitComment(btn) {
    var sr = serialize(), err = root.querySelector(".ba-err"); err.textContent = "";
    if (!sr.body) { err.textContent = "Write the comment first."; return; }
    if (!sr.refs.length) { err.textContent = "Tag at least one element: click it on the page."; return; }
    // a //name typed by hand must be a known element; it is turned into a tag, or the comment is not sent
    var typed = []; sr.body.replace(REF_RE, function (m, pre, name) { if (!sr.refs.some(function (r) { return r.ref_name === name; })) typed.push(name); return m; });
    btn.disabled = true;
    Promise.all(typed.map(function (n) { return S.rpc("build_find_ref", { p_name: n }).then(function (f) { return { name: n, f: f }; }); })).then(function (found) {
      var unknown = found.filter(function (x) { return !x.f.found; });
      if (unknown.length) { btn.disabled = false; err.textContent = "Unknown reference: //" + unknown[0].name + ". Tag the element on the page, or remove that text."; return; }
      found.forEach(function (x) { sr.refs.push({ element_id: x.f.id, ref_name: x.f.ref_name, stability: x.f.stability }); });
      return S.rpc("build_submit", { p: { kind: "annotation", message_kind: "instruction", body: sr.body, refs: sr.refs, route: edState.route || routeNow(), client_key: edState.key, build_version: (window.SAAZ || {}).build || null } })
        .then(function (r) { discardDraft(); S.toast("Saved. " + (r.task ? r.task.ref + " is queued for the agent." : "")); st.tab = "tasks"; renderTab(); });
    }).catch(function (e) { btn.disabled = false; err.textContent = S.friendly(e); });
  }

  // ---------- page events while annotating (capture phase, so the site's own handlers don't run) ----------
  var touch = false;
  function inUi(e) { return e.target.closest && e.target.closest("#ba-root"); }
  function setMode(on) {
    st.mode = on; save(MODE, on ? 1 : null); bar.hidden = !on; document.documentElement.classList.toggle("ba-annotating", on);
    root.querySelector(".ba-hint").textContent = touch ? "Tap an element to select it." : st.editor ? "Click elements to tag them in your comment." : "Double-click an element to comment on it.";
    setPick(""); if (!on) showOutline(null); renderTab();
  }
  // the "selected: X  Comment" choice after a tap; shown in the floating bar and, when the panel is open, inside the panel
  function setPick(html) { st.pickHtml = html; root.querySelectorAll(".ba-pick").forEach(function (x) { x.innerHTML = html; }); }
  document.addEventListener("pointermove", function (e) { if (!st.mode || inUi(e) || e.pointerType === "touch") return; showOutline(targetOf(e.target)); }, true);
  // Mouse: pressing on the page keeps the editor's focus and cursor, and keeps the page from reacting.
  // Touch: the press is left alone so the page still scrolls; the tap itself is stopped below.
  document.addEventListener("pointerdown", function (e) {
    if (!st.mode || inUi(e)) return;
    if (e.pointerType === "touch" || e.pointerType === "pen") { if (!touch) { touch = true; setMode(true); } return; }
    e.preventDefault();
  }, true);
  document.addEventListener("mousedown", function (e) { if (st.mode && !inUi(e) && !touch) e.preventDefault(); }, true);
  document.addEventListener("click", function (e) {
    if (!st.mode || inUi(e)) return;
    e.preventDefault(); e.stopPropagation();   // a click while annotating selects; it never follows a link or presses a button
    var el = targetOf(e.target); if (!el) return;
    showOutline(el, true);
    if (st.editor) {
      if (st.tab !== "comment" || !ed || !document.body.contains(ed)) { st.tab = "comment"; showPanel(true); renderTab(); }
      register(el).then(function (r) { insertChip(r); }).catch(function (x) { S.toast(S.friendly(x), true); }); return; }
    if (touch) {   // phones and tablets: tap to select, then choose
      st.picked = el; var d = describe(el);
      setPick("<span class='badge'>" + esc(d.base_name) + "</span> <button type='button' class='btn small' data-act='comment-picked'>Comment</button>");
    }
  }, true);
  document.addEventListener("dblclick", function (e) {
    if (!st.mode || inUi(e)) return; e.preventDefault(); e.stopPropagation();
    var el = targetOf(e.target); if (!el || st.editor) return;
    register(el).then(function (r) { openEditor(r); }).catch(function (x) { S.toast(S.friendly(x), true); });
  }, true);
  document.addEventListener("submit", function (e) { if (st.mode && !inUi(e)) { e.preventDefault(); e.stopPropagation(); } }, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && st.mode && !st.editor && !inUi(e)) setMode(false); }, true);

  // ---------- panel ----------
  // the floating bar steps aside only while the Comment tab, which has its own switch, is on screen
  function barPlace() { root.classList.toggle("ba-panel-open", !panel.hidden && st.tab === "comment"); root.classList.toggle("ba-sheet-up", !panel.hidden); }
  function showPanel(on) { panel.hidden = !on; barPlace(); launch.setAttribute("aria-expanded", String(on)); if (on) refreshStatus(); }
  function refreshStatus() {
    S.rpc("build_status").then(function (s) {
      st.status = s; root.querySelector(".ba-agent").textContent = s.enabled ? "Agent last checked in " + ago(s.agent_last_seen) : "Switched off";
    }).catch(function () {});
  }
  function renderTab() { barPlace();
    refreshStatus();
    root.querySelectorAll(".ba-tabs [data-tab]").forEach(function (b) { b.setAttribute("aria-selected", String(b.dataset.tab === st.tab)); });
    if (st.tab === "comment") renderComment(); else if (st.tab === "chat") renderChat(); else renderTasks();
  }
  function renderComment() {
    var wasHtml = edState ? edState.html : (draft() || {}).html;
    if (!edState && draft()) edState = draft();
    body.innerHTML = "<label class='inline ba-switch'><input type='checkbox' data-act='mode'" + (st.mode ? " checked" : "") + "> Select elements on the page</label>" +
      "<p class='ba-pick'>" + (st.pickHtml || "") + "</p>" +
      (edState ? "<p class='note'>" + (wasHtml && !st.editor ? "Your draft is kept. " : "") + (touch ? "Tap" : "Click") + " elements on the page to tag them where your cursor is. The page doesn't react while selecting.</p>" +
        "<div class='ba-editor' contenteditable='true' role='textbox' aria-multiline='true' aria-label='Comment'></div>" +
        "<p class='ba-tagged note'></p><p class='ba-note note'></p><p class='err ba-err' role='alert'></p>" +
        "<div class='ba-confirm' hidden><span>Discard this comment?</span><button type='button' class='btn small' data-act='discard'>Discard</button><button type='button' class='btn ghost small' data-act='keep'>Keep writing</button></div>" +
        "<div class='row'><button type='button' class='btn' data-act='save'>Save comment</button><button type='button' class='btn ghost' data-act='cancel'>Cancel</button></div>"
      : "<p class='note'>Turn on selecting, then " + (touch ? "tap an element and choose Comment." : "double-click an element to start a comment.") + " Use Chat for anything not about one element.</p>");
    ed = body.querySelector(".ba-editor");
    if (ed) {
      st.editor = true; ed.innerHTML = edState.html || ""; renderChipsBar();
      ed.addEventListener("input", keep);
      ed.addEventListener("click", function (e) { if (e.target.dataset.act === "unchip") { var c = e.target.closest(".ba-chip"); c.remove(); keep(); ed.focus(); } });
      ed.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitComment(body.querySelector("[data-act='save']")); } });
    }
  }
  function renderChat() {
    body.innerHTML = "<form class='stack ba-chat'><label>Message<textarea name='body' rows='4' maxlength='8000' required placeholder='An instruction, question or feedback about the site'></textarea></label>" +
      "<div class='grid2'><label>About<select name='scope'><option value='project'>The whole project</option><option value='page'>This page (" + esc(routeNow()) + ")</option></select></label>" +
      "<label>Kind<select name='message_kind'><option value='instruction'>Instruction: make a task</option><option value='note'>Note: keep for the record</option></select></label></div>" +
      "<p class='err' role='alert'></p><button class='btn'>Send</button></form><div class='ba-list'><p class='loading'>Loading…</p></div>";
    var f = body.querySelector("form"), key = uuid();
    f.onsubmit = function (e) {
      e.preventDefault(); var o = S.form(f), b = f.querySelector("button"); b.disabled = true; f.querySelector(".err").textContent = "";
      S.rpc("build_submit", { p: { kind: "chat", message_kind: o.message_kind, scope: o.scope, route: routeNow(), body: o.body, refs: [], client_key: key, build_version: (window.SAAZ || {}).build || null } })
        .then(function (r) { S.toast("Saved." + (r.task ? " " + r.task.ref + " is queued for the agent." : " Kept as a note.")); renderChat(); })
        .catch(function (x) { b.disabled = false; f.querySelector(".err").textContent = S.friendly(x); });
    };
    loadHistory("chat");
  }
  function renderTasks() { body.innerHTML = "<div class='ba-list'><p class='loading'>Loading…</p></div>"; loadHistory(null); }
  function loadHistory(kind) {
    S.rpc("build_history", { p_limit: 50, p_task: null }).then(function (threads) {
      var list = body.querySelector(".ba-list"); if (!list) return;
      threads = threads.filter(function (t) { return !kind || t.kind === kind; });
      if (!threads.length) { list.innerHTML = "<p class='note'>Nothing yet.</p>"; return; }
      list.innerHTML = threads.map(function (t) {
        return "<article class='ba-thread'><p class='note'>" + (t.kind === "annotation" ? "Comment" : "Chat") + " · " + esc(t.scope === "project" ? "whole project" : t.scope === "page" ? "page " + (t.route || "") : t.scope) + "</p>" +
          t.messages.filter(function (m) { return !m.task_id; }).map(function (m) {
            return "<div class='ba-msg " + m.author_kind + "'><p>" + esc(m.body).replace(REF_RE, function (all, pre, name) { return pre + "<span class='badge'>//" + name + "</span>"; }) + "</p><small>" + esc(m.author || "") + " · " + S.day(m.created_at) + (m.edited_at ? " · edited" : "") + "</small></div>";
          }).join("") +
          (t.tasks || []).map(function (k) {
            var msgs = t.messages.filter(function (m) { return m.task_id === k.id; });
            return "<details class='ba-task'><summary><span class='chip s-" + (k.status === "verified" ? "issued" : k.status === "failed" || k.status === "blocked" ? "fail" : k.status === "needs_clarification" ? "flag" : k.status === "cancelled" ? "cancelled" : "in_play") + "'>" + esc(STATUS[k.status] || k.status) + "</span> " + esc(k.ref) + "</summary>" +
              "<ol class='timeline'>" + (k.events || []).map(function (ev) { return "<li><b>" + esc(ev.to ? (STATUS[ev.to] || ev.to) : "") + "</b> " + esc(ev.note || "") + " <small>" + esc(ev.actor_kind) + " · " + S.day(ev.at) + " " + new Date(ev.at).toLocaleTimeString("en-GB", { timeZone: "Africa/Kampala", hour: "2-digit", minute: "2-digit" }) + "</small>" +
                (ev.detail && (ev.detail.files || ev.detail.checks) ? "<small>" + esc((ev.detail.files || []).join(", ")) + (ev.detail.checks ? " · checks: " + esc(ev.detail.checks.map(function (c) { return c.name + " " + c.result; }).join(", ")) : "") + "</small>" : "") + "</li>"; }).join("") + "</ol>" +
              msgs.map(function (m) { return "<div class='ba-msg " + m.author_kind + "'><p>" + esc(m.body) + "</p><small>" + (m.author_kind === "agent" ? "Agent" : "You") + " · " + S.day(m.created_at) + "</small></div>"; }).join("") +
              (["verified", "cancelled"].indexOf(k.status) < 0 ? "<form class='inlineform ba-reply' data-task='" + k.id + "'><label>" + (k.status === "needs_clarification" ? "Your answer" : "Add a note") + "<input name='body' required maxlength='8000'></label><button class='btn small'>Send</button></form>" +
                "<div class='row'>" + (["failed", "blocked"].indexOf(k.status) >= 0 ? "<button type='button' class='btn ghost small' data-act='retry' data-task='" + k.id + "'>Retry</button>" : "") +
                "<button type='button' class='btn ghost small' data-act='cancel-task' data-task='" + k.id + "'>Cancel task</button></div>" : "") + "</details>";
          }).join("") + "</article>";
      }).join("");
      list.querySelectorAll(".ba-reply").forEach(function (f) {
        var key = uuid();
        f.onsubmit = function (e) { e.preventDefault(); S.rpc("build_reply", { p_task: f.dataset.task, p_body: S.form(f).body, p_client_key: key }).then(function () { S.toast("Sent."); renderTab(); }).catch(function (x) { S.toast(S.friendly(x), true); }); };
      });
    }).catch(function (e) { var list = body.querySelector(".ba-list"); if (list) list.innerHTML = "<p class='err'>" + esc(S.friendly(e)) + "</p>"; });
  }

  // ---------- buttons ----------
  root.addEventListener("click", function (e) {
    var a = e.target.closest("[data-act],[data-tab]"); if (!a) return;
    if (a.dataset.tab) { st.tab = a.dataset.tab; renderTab(); return; }
    var act = a.dataset.act;
    if (act === "close") showPanel(false);
    if (act === "mode-off") setMode(false);
    if (act === "save") submitComment(a);
    if (act === "cancel") { var sr = serialize(); if (sr.body.length > 3) { root.querySelector(".ba-confirm").hidden = false; } else discardDraft(); }
    if (act === "discard") discardDraft();
    if (act === "keep") { root.querySelector(".ba-confirm").hidden = true; ed.focus(); restoreRange(); }
    if (act === "comment-picked" && st.picked) register(st.picked).then(function (r) { openEditor(r); setPick(""); });
    if (act === "retry" || act === "cancel-task") S.rpc("build_task_action", { p_task: a.dataset.task, p_action: act === "retry" ? "retry" : "cancel", p_reason: null }).then(function () { renderTab(); }).catch(function (x) { S.toast(S.friendly(x), true); });
  });
  root.addEventListener("change", function (e) { if (e.target.dataset.act === "mode") setMode(e.target.checked); });
  launch.onclick = function () { showPanel(panel.hidden); if (!panel.hidden) renderTab(); };
  window.addEventListener("pagehide", keep);

  // a draft left from before (another page, a reload): open it again
  if (draft()) { edState = draft(); st.tab = "comment"; showPanel(true); renderTab(); }
  if (load(MODE)) setMode(true);
  S.buildAssistant = { setMode: setMode, open: function () { showPanel(true); renderTab(); }, state: st, serialize: function () { return ed ? serialize() : null; } };
})();
